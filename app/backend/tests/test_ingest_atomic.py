"""Atomicity & idempotency tests for `worker.ingest.ingest_pdf` (audit H8).

The guarantees under test:

  1. **Idempotent retry** — re-running with the same gazette_id on a
     `failed` or stuck-`processing` gazette wipes any partial rows
     before re-ingesting. Outcome: row count matches the fresh-run
     expectation, no duplicates.

  2. **Crash-safe** — if the ingest loop raises mid-extract, the error
     handler purges any rows committed in earlier batches and flips
     the gazette to `status=failed`. DB never holds half a gazette
     while the row says it failed.

  3. **No-op on completed** — re-enqueueing a `completed` gazette is a
     fast skip, not a re-ingest (admin must purge to force a re-run).

The tests use a real Postgres (test DB), monkeypatch the heavy I/O
deps (PDFProcessor, image extractor), and assert the row-count and
status invariants directly.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from worker import ingest as ingest_mod
from worker.ingest import ingest_pdf


@pytest.fixture
def sync_session() -> Session:
    """Sync session bound to the test DB — same engine the worker uses.

    The worker's own session factory is cached at module scope, so
    constructing a fresh one here lets tests assert on the same data
    without race-with-cache surprises.
    """
    engine = create_engine(get_settings().database_url_sync, future=True)
    Session_ = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session_()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def fake_pdf(tmp_path: Path) -> Path:
    """A real on-disk file the worker can stat. The contents don't matter
    because we monkeypatch PDFProcessor.extract_records to yield fakes."""
    p = tmp_path / "fake.pdf"
    p.write_bytes(b"%PDF-1.4 fake")
    return p


def _make_gazette(
    session: Session,
    storage_path: Path,
    status: GazetteStatus = GazetteStatus.uploaded,
    row_count: int = 0,
) -> Gazette:
    """Insert a fresh Gazette row in the test DB. Returns the persisted row.

    sha256 uses the gazette's own UUID so multiple test gazettes never
    collide on the uq_gazettes_sha256 constraint.
    """
    gid = uuid.uuid4()
    g = Gazette(
        id=gid,
        filename="fake.pdf",
        # 64-char hex string from the UUID so uniqueness is guaranteed.
        sha256=gid.hex + gid.hex[:32],
        gazette_type=GazetteType.A,
        issue_year=2026,
        issue_number=99,
        storage_path=str(storage_path),
        size_bytes=42,
        status=status,
        row_count=row_count,
    )
    session.add(g)
    session.commit()
    session.refresh(g)
    return g


def _patch_extractor_to_yield(monkeypatch: pytest.MonkeyPatch, sections: list[dict[str, Any]]) -> None:
    """Replace PDFProcessor in the worker's namespace so extract_records
    yields the canned section list. Skips real PDF parsing entirely."""

    class FakeProcessor:
        def __init__(self, *a, **k):
            pass

        def extract_records(self, *a, **k):
            yield from sections

    monkeypatch.setattr(ingest_mod, "PDFProcessor", FakeProcessor)
    # Image extraction is a no-op for these tests — return None so logo_path
    # ends up NULL on every row.
    monkeypatch.setattr(ingest_mod, "_run_image_extraction", lambda *a, **k: None)


def _section(app_no: str) -> dict[str, Any]:
    """Minimal A-file section dict the mapper accepts."""
    return {
        "(210)": app_no,
        "(540)": f"MARK-{app_no}",
        "(511)": "Nhóm 9",
        "Applicant Name": "TEST INC",
    }


# ---------------------------------------------------------------------------
# Happy path baseline
# ---------------------------------------------------------------------------


def test_ingest_writes_rows_and_marks_completed(
    sync_session: Session,
    fake_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Baseline: fresh ingest writes the expected row count and flips
    status to completed. Establishes the invariant the other tests
    compare against."""
    sections = [_section("4-2026-00001"), _section("4-2026-00002"), _section("4-2026-00003")]
    _patch_extractor_to_yield(monkeypatch, sections)

    gazette = _make_gazette(sync_session, fake_pdf)
    try:
        result = ingest_pdf(str(gazette.id))
        assert result["status"] == "completed"
        assert result["row_count"] == 3

        sync_session.expire_all()
        g = sync_session.get(Gazette, gazette.id)
        assert g is not None
        assert g.status == GazetteStatus.completed
        assert g.row_count == 3

        rows = (
            sync_session.execute(select(Trademark).where(Trademark.gazette_id == gazette.id)).scalars().all()
        )
        assert len(rows) == 3
    finally:
        sync_session.execute(delete(Trademark).where(Trademark.gazette_id == gazette.id))
        sync_session.execute(delete(Gazette).where(Gazette.id == gazette.id))
        sync_session.commit()


# ---------------------------------------------------------------------------
# Atomicity: failure during loop rolls back partial rows
# ---------------------------------------------------------------------------


def test_ingest_failure_purges_partial_rows(
    sync_session: Session,
    fake_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the extractor blows up mid-stream after at least one batch has
    been committed, the error handler must DELETE those partial rows
    before flipping the gazette to failed. The DB then carries zero
    rows for this gazette — matching the 'failed' status."""
    # Force batch_size=2 so the first 2 sections commit, then we explode.
    settings = get_settings()
    monkeypatch.setattr(settings, "worker_batch_size", 2)

    class ExplodingProcessor:
        def __init__(self, *a, **k):
            pass

        def extract_records(self, *a, **k):
            yield _section("4-2026-00001")
            yield _section("4-2026-00002")
            # First batch (2 rows) commits here.
            yield _section("4-2026-00003")
            raise RuntimeError("fake parser crash on page 47")

    monkeypatch.setattr(ingest_mod, "PDFProcessor", ExplodingProcessor)
    monkeypatch.setattr(ingest_mod, "_run_image_extraction", lambda *a, **k: None)

    gazette = _make_gazette(sync_session, fake_pdf)
    try:
        with pytest.raises(RuntimeError, match="fake parser crash"):
            ingest_pdf(str(gazette.id))

        sync_session.expire_all()
        g = sync_session.get(Gazette, gazette.id)
        assert g is not None
        assert g.status == GazetteStatus.failed
        assert "fake parser crash" in (g.error_message or "")
        assert g.row_count == 0

        # The atomicity guarantee: zero trademarks survive the crash.
        leftover = (
            sync_session.execute(select(Trademark).where(Trademark.gazette_id == gazette.id)).scalars().all()
        )
        assert leftover == [], f"expected 0 rows after rollback, got {len(leftover)}"
    finally:
        sync_session.execute(delete(Trademark).where(Trademark.gazette_id == gazette.id))
        sync_session.execute(delete(Gazette).where(Gazette.id == gazette.id))
        sync_session.commit()


# ---------------------------------------------------------------------------
# Idempotency: retries clean prior partial rows
# ---------------------------------------------------------------------------


def test_ingest_retry_after_failed_purges_and_succeeds(
    sync_session: Session,
    fake_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gazette in `status=failed` with stale leftover trademarks (e.g.,
    from a manual fix that didn't clean up) should re-ingest cleanly:
    purge first, then write the new row set. No duplicates."""
    sections = [_section("4-2026-00001"), _section("4-2026-00002")]
    _patch_extractor_to_yield(monkeypatch, sections)

    gazette = _make_gazette(sync_session, fake_pdf, status=GazetteStatus.failed, row_count=99)
    # Plant 99 stale rows to simulate a half-rolled-back prior attempt.
    stale = [
        Trademark(gazette_id=gazette.id, record_type=RecordType.A, application_number=f"stale-{i}")
        for i in range(99)
    ]
    sync_session.add_all(stale)
    sync_session.commit()

    try:
        result = ingest_pdf(str(gazette.id))
        assert result["status"] == "completed"
        assert result["row_count"] == 2

        sync_session.expire_all()
        rows = (
            sync_session.execute(select(Trademark).where(Trademark.gazette_id == gazette.id)).scalars().all()
        )
        # 99 stale rows purged, 2 fresh rows written.
        assert len(rows) == 2
        assert {r.application_number for r in rows} == {"4-2026-00001", "4-2026-00002"}
    finally:
        sync_session.execute(delete(Trademark).where(Trademark.gazette_id == gazette.id))
        sync_session.execute(delete(Gazette).where(Gazette.id == gazette.id))
        sync_session.commit()


def test_ingest_stuck_processing_recovers(
    sync_session: Session,
    fake_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gazette stuck in `processing` (worker SIGKILL'd, job timed out
    without running the except handler) must be recoverable: a new
    ingest attempt purges the partial rows and starts over instead
    of silently no-op'ing."""
    sections = [_section("4-2026-00010")]
    _patch_extractor_to_yield(monkeypatch, sections)

    gazette = _make_gazette(sync_session, fake_pdf, status=GazetteStatus.processing, row_count=0)
    # Simulate one partial row from a prior crashed attempt.
    sync_session.add(
        Trademark(gazette_id=gazette.id, record_type=RecordType.A, application_number="partial-row")
    )
    sync_session.commit()

    try:
        result = ingest_pdf(str(gazette.id))
        assert result["status"] == "completed"
        assert result["row_count"] == 1

        rows = (
            sync_session.execute(select(Trademark).where(Trademark.gazette_id == gazette.id)).scalars().all()
        )
        # The pre-existing partial row is gone; the new fresh row is in.
        assert [r.application_number for r in rows] == ["4-2026-00010"]
    finally:
        sync_session.execute(delete(Trademark).where(Trademark.gazette_id == gazette.id))
        sync_session.execute(delete(Gazette).where(Gazette.id == gazette.id))
        sync_session.commit()


# ---------------------------------------------------------------------------
# Idempotency: completed gazettes skip
# ---------------------------------------------------------------------------


def test_ingest_completed_is_noop(
    sync_session: Session,
    fake_pdf: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-enqueueing a `completed` gazette must be a fast skip — no
    re-extraction, no row mutation. Protects against accidental
    double-clicks on a re-queue button."""
    # If we accidentally re-ran the extractor, this fake would yield 5 rows.
    # Asserting it stays at 7 (the pre-existing committed count) proves we
    # skipped the extraction step entirely.
    sections = [_section(f"4-2026-{i:05d}") for i in range(5)]
    _patch_extractor_to_yield(monkeypatch, sections)

    gazette = _make_gazette(sync_session, fake_pdf, status=GazetteStatus.completed, row_count=7)
    # Plant 7 pre-existing rows that the no-op must NOT delete.
    sync_session.add_all(
        [
            Trademark(gazette_id=gazette.id, record_type=RecordType.A, application_number=f"keep-{i}")
            for i in range(7)
        ]
    )
    sync_session.commit()

    try:
        result = ingest_pdf(str(gazette.id))
        assert result["skipped"] is True
        assert result["row_count"] == 7

        sync_session.expire_all()
        rows = (
            sync_session.execute(select(Trademark).where(Trademark.gazette_id == gazette.id)).scalars().all()
        )
        # Pre-existing rows survived; no new rows from the (would-be) extractor.
        assert len(rows) == 7
        assert all(r.application_number.startswith("keep-") for r in rows)
    finally:
        sync_session.execute(delete(Trademark).where(Trademark.gazette_id == gazette.id))
        sync_session.execute(delete(Gazette).where(Gazette.id == gazette.id))
        sync_session.commit()
