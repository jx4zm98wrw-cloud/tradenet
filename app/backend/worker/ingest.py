"""PDF ingest job — runs tm_extractor and bulk-inserts trademark rows."""

from __future__ import annotations

import hashlib
import logging
import re
import string
import struct
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, delete, text
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import Gazette, GazetteStatus, GazetteType, Trademark
from api.settings import get_settings
from tm_extractor import ExtractorConfig, PDFProcessor

from .mapper import infer_record_type, section_to_trademark

logger = logging.getLogger("worker.ingest")


def _gazette_lock_id(gazette_id: uuid.UUID) -> int:
    """Map a gazette UUID to a stable signed int64 for pg_advisory_lock.

    We can't use Python's `hash()` — it's randomized per process via
    PYTHONHASHSEED, so the lock id would differ between workers and
    the lock would be useless. Taking the first 8 bytes of the UUID
    and interpreting them as a big-endian signed int64 gives a stable
    bijection from gazette_id to lock_id within the int64 range that
    pg_try_advisory_lock(bigint) accepts.
    """
    return struct.unpack(">q", gazette_id.bytes[:8])[0]


def _try_advisory_lock(session: Session, gazette_id: uuid.UUID) -> bool:
    """Try to acquire a Postgres advisory lock for this gazette.

    Returns True if we got the lock, False if another worker holds it.
    The lock is session-scoped (survives commits) — released when the
    connection closes or `_release_advisory_lock` is called explicitly.

    Why advisory, not SELECT FOR UPDATE: ingest commits multiple times
    (after each batch). A row-level lock would release on each commit
    and another worker could slip in between batches. Advisory locks
    persist across commits and are exactly what "hold a logical lock
    for the whole job" needs.
    """
    lock_id = _gazette_lock_id(gazette_id)
    result = session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": lock_id}).scalar()
    return bool(result)


def _release_advisory_lock(session: Session, gazette_id: uuid.UUID) -> None:
    """Release the advisory lock. Safe to call even if we never acquired
    it (Postgres returns False instead of raising), so callers don't need
    to track lock state across error paths."""
    lock_id = _gazette_lock_id(gazette_id)
    try:
        session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": lock_id})
        session.commit()
    except Exception:
        # Best-effort unlock; we don't want a cleanup failure to mask
        # the real exception being raised from ingest. The lock will
        # also be auto-released when the session's connection closes.
        logger.exception("Failed to release advisory lock for gazette %s", gazette_id)
        session.rollback()


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    """Cache the engine + sessionmaker at module scope.

    Previously this module created a new engine per RQ job, leaking the
    connection pool (5 connections per engine, never disposed). Under
    sustained job throughput this exhausted postgres' max_connections.

    The engine itself is created lazily on first call (not at import time)
    so the API process, which imports `worker.ingest` indirectly via
    routes, doesn't open a sync DB connection it never uses.
    """
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _sync_session() -> Session:
    return _session_factory()()


def _run_image_extraction(
    pdf_path: Path,
    output_stem: str,
    year: int | None,
    gazette_type: GazetteType,
    data_dir: Path,
) -> Path | None:
    """Best-effort logo extraction. Returns the absolute path of the per-PDF
    image directory on success, None on failure. CSV ingest continues either
    way — rows just get logo_path=NULL when extraction failed.

    Logging policy (post-audit):
      - WARNING for known degrade-paths: missing config file, missing year,
        extractor module not importable.
      - ERROR (with exc_info) for unexpected failures: extractor crashed
        mid-PDF, unexpected import error. These indicate a real problem
        worth investigating; the row count of NULL logo_path values on the
        gazette is the operator's smoke signal.
    """
    if year is None:
        logger.warning("Gazette has no issue_year; skipping image extraction for %s", pdf_path.name)
        return None

    # Lazy import: pymupdf/PIL/pdfplumber are heavy and only needed during extraction,
    # not on worker boot. Keeping the import inside the function also lets
    # test_run_image_extraction.py inject a fake `image_extractor` module via
    # `monkeypatch.setitem(sys.modules, ...)` before this line runs.
    try:
        import yaml

        from image_extractor import ImageExtractor, ImagePaths
    except (ImportError, ModuleNotFoundError) as e:
        # Extractor package or yaml not installed — degrade to no-logo.
        logger.warning("Image extractor not importable: %s", e)
        return None
    except Exception:
        # Anything else (SyntaxError on a hand-edit, AttributeError on a
        # renamed symbol, third-party RuntimeError at module init) is a real
        # programming error masquerading as "extractor missing." Surface it
        # so the operator can see what broke.
        logger.exception("Unexpected error importing image extractor")
        return None

    cfg_path = data_dir / "config_image_extractor.yaml"
    if not cfg_path.exists():
        logger.warning("Missing %s; skipping image extraction", cfg_path)
        return None
    with cfg_path.open() as f:
        image_cfg = yaml.safe_load(f) or {}

    year_str = str(year)
    image_dir = data_dir / "image" / year_str / output_stem
    modified_dir = data_dir / "modified" / year_str / output_stem
    image_link_dir = data_dir / "image_link" / year_str
    for d in (image_dir, modified_dir, image_link_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ProcessingPaths wants the working_dir + per-type roots; we bypass its
    # single-PDF wrapper to keep control over output directory names (which
    # would otherwise be derived from the digest-prefixed storage filename).
    image_paths = ImagePaths(
        working_dir=data_dir,
        input_dir=pdf_path.parent,
        image_dir=data_dir / "image" / year_str,
        modified_dir=data_dir / "modified" / year_str,
        image_link_dir=image_link_dir,
    )
    extractor = ImageExtractor(image_paths, image_cfg, processing_mode="auto")
    pdf_type = "B" if gazette_type == GazetteType.B else "A"

    try:
        modified_pdf = extractor._modify_pdf(pdf_path, modified_dir, pdf_type)
        extractor._extract_images(modified_pdf, image_dir, pdf_type)
        extractor._create_image_link_csv(output_stem, image_dir, image_link_dir, year_folder=None)
    except Exception:
        # The extractor crashed mid-PDF. Partial output may already be on disk
        # (some PNGs in image_dir, modified PDF half-written). Log at ERROR with
        # exc_info so an operator can correlate it with the resulting NULL
        # logo_path rows. CSV ingest still proceeds — see ingest_pdf's caller.
        logger.exception(
            "Image extraction failed mid-PDF for %s (partial output may be in %s)",
            pdf_path.name,
            image_dir,
        )
        return None

    extracted_pngs = sum(1 for _ in image_dir.glob("*.png"))
    logger.info(
        "Image extraction completed for %s (%s, %d PNGs)",
        pdf_path.name,
        image_dir,
        extracted_pngs,
    )
    return image_dir


# Identifier values come from the PDF text layer (extracted by the parser
# from raw bytes that a third party authored). An allowlist on this value
# stops a crafted PDF from poisoning trademarks.logo_path with a
# path-traversal string. Matches the extractor's own image_name_pattern
# in config_image_extractor.yaml: alphanumerics + dash.
_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9\-]+$")


def _resolve_logo_path(section: dict, image_subdir_rel: str, image_root: Path) -> str | None:
    """Look up the extracted PNG for this section. Tries (210) (A-file
    applications), (111) (B-file domestic VN registrations), and (116)
    (B-file Madrid international registrations) in that order. Returns the
    path relative to image_root (which is mounted at /static/image/), or
    None if no logo file exists.

    The standalone extractor names PNGs after whichever section-start
    marker it found first; for B-files that's `(111)` or `(116)`, not
    `(210)`, so omitting `(111)` here drops every domestic-only B row.

    Letter-suffix fallback (e.g. 0181946 → 0181946A.png) applies ONLY to
    (116) Madrid: WIPO publishes modifications/renewals of a base Madrid
    registration with A-Z suffixes. (210)/(111) numbers have a different
    structure (4-YYYY-NNNN / 7-digit certificate) and an `A` suffix on
    one of those would be an unrelated mark, not the same registration.
    """
    for marker in ("(210)", "(111)", "(116)"):
        v = section.get(marker)
        if not v:
            continue
        ident = str(v).strip()
        if not ident or not _ID_SAFE_RE.match(ident):
            continue
        # Exact name first.
        rel = f"{image_subdir_rel}/{ident}.png"
        if (image_root / rel).is_file():
            return rel
        # Madrid-only suffix variants.
        if marker == "(116)":
            for suf in string.ascii_uppercase:
                rel = f"{image_subdir_rel}/{ident}{suf}.png"
                if (image_root / rel).is_file():
                    return rel
    return None


def _purge_trademarks(session: Session, gazette_id: uuid.UUID) -> int:
    """Delete every Trademark row for the given gazette and commit.

    Used in two places:
      1. On ingest entry, to give the new attempt a clean slate (whether
         the prior state was `uploaded`, `failed`, or stuck `processing`).
      2. In the error handler, to roll back any rows committed in earlier
         batches before flipping the gazette to `failed` — keeps the DB
         from holding "half a gazette" while the row says it failed.

    Returns the row count purged (informational; safe-to-ignore).
    """
    result = session.execute(delete(Trademark).where(Trademark.gazette_id == gazette_id))
    # `session.execute(delete(...))` returns a CursorResult at runtime, which
    # has `.rowcount` — but newer SQLAlchemy stubs annotate the return as
    # Result[Any] which lacks the attribute. Using getattr() with a default
    # works cleanly under both stub generations without tripping
    # warn_unused_ignores or warn_redundant_casts.
    purged: int = getattr(result, "rowcount", 0) or 0
    session.commit()
    return purged


def ingest_pdf(gazette_id: str) -> dict:
    """Run extraction for an existing `gazettes` row and write `trademarks` rows.

    Intended to be called as an RQ job. `gazette_id` is the UUID string of an
    already-persisted Gazette. Updates status as it runs.

    **Atomicity & idempotency** (H8):
    Re-running with the same `gazette_id` is safe — the job is idempotent.
    Per starting status:
      - `completed` → no-op success (admin must purge first if they really
        want to re-ingest).
      - `uploaded` → normal first attempt.
      - `failed` → previous attempt errored; this one purges any partial
        rows then ingests from scratch.
      - `processing` → previous worker died mid-job (SIGKILL, OOM, job
        timeout before the except handler ran). Treated as a recoverable
        state: purge partial rows, log a warning, restart.

    On any in-loop crash, the except handler deletes any rows committed
    in earlier batches before flipping the gazette to `status=failed`.
    The DB never holds "half a gazette" while the row says it failed.

    Filesystem side: extracted PNGs use deterministic filenames
    `<id>.png` derived from (210)/(111)/(116) WIPO codes. Retries
    overwrite, so no per-attempt filesystem cleanup is needed.

    Caller contract: the RQ retry/dead-letter policy is set up in
    `app/backend/api/routes/gazettes.py` (3 attempts, then to RQ's
    failed registry for forensic retention).

    Concurrent worker safety: a Postgres advisory lock keyed on
    gazette_id ensures at-most-one worker can be in the ingest path
    for a given gazette at a time. The advisory lock survives commits
    (so it holds across the batched-commit loop) and is released
    automatically when the session's connection closes. A duplicate
    enqueue (RQ's at-least-once delivery, or an operator re-running a
    job) sees `pg_try_advisory_lock` return false and returns a
    `locked-by-another` skip result — no double-writing.
    """
    settings = get_settings()
    session = _sync_session()
    gid = uuid.UUID(gazette_id)
    # Acquire the advisory lock BEFORE doing any DB work. Released in
    # finally so abnormal exits also clean up.
    if not _try_advisory_lock(session, gid):
        logger.warning(
            "Gazette %s is being processed by another worker; skipping duplicate enqueue",
            gazette_id,
        )
        session.close()
        return {
            "gazette_id": gazette_id,
            "status": "locked-by-another",
            "skipped": True,
        }
    try:
        gazette = session.get(Gazette, gid)
        if gazette is None:
            raise ValueError(f"Gazette {gazette_id} not found")

        # Idempotent skip on already-completed gazettes. Admin must
        # explicitly delete prior trademarks before re-running.
        if gazette.status == GazetteStatus.completed:
            logger.info(
                "Gazette %s already completed (row_count=%d); skipping",
                gazette_id,
                gazette.row_count or 0,
            )
            return {
                "gazette_id": gazette_id,
                "row_count": gazette.row_count or 0,
                "status": "completed",
                "skipped": True,
            }

        # Distinguish recoverable starting states in the log so operators
        # can tell a normal first attempt from a recovery / retry.
        if gazette.status == GazetteStatus.processing:
            logger.warning(
                "Gazette %s was stuck in 'processing' (likely prior worker "
                "crash / job timeout). Purging partial rows and restarting.",
                gazette_id,
            )
        elif gazette.status == GazetteStatus.failed:
            logger.info("Gazette %s previously failed; retrying after purge", gazette_id)

        # Clean slate. Drops any rows from a prior attempt and resets
        # the gazette's bookkeeping in a single transaction so the API
        # never sees a "0 rows + processing" intermediate state.
        purged = _purge_trademarks(session, gid)
        if purged:
            logger.info("Purged %d prior trademark rows for gazette %s", purged, gazette_id)
        gazette.status = GazetteStatus.processing
        gazette.error_message = None
        gazette.row_count = 0
        gazette.processed_at = None
        session.add(gazette)
        session.commit()

        pdf_path = Path(gazette.storage_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF missing on disk: {pdf_path}")

        cfg = ExtractorConfig(
            data_dir=settings.data_dir,
            input_dir=pdf_path.parent,
            output_dir=settings.upload_dir / "csv",  # unused by extract_records, but required
            log_dir=settings.upload_dir / "log",
        )
        cfg.ensure_dirs()
        processor = PDFProcessor(cfg)

        letter = "B" if gazette.gazette_type == GazetteType.B else "A"

        # Image extraction — best-effort, runs before the CSV loop so logos
        # are on disk when the mapper looks them up per-section. The output
        # subdir uses the original (un-digested) filename stem so it stays
        # human-readable and stable across re-ingests of the same PDF.
        output_stem = Path(gazette.filename).stem
        _run_image_extraction(
            pdf_path=pdf_path,
            output_stem=output_stem,
            year=gazette.issue_year,
            gazette_type=gazette.gazette_type,
            data_dir=settings.data_dir,
        )
        image_root = settings.data_dir / "image"
        image_subdir_rel = f"{gazette.issue_year}/{output_stem}" if gazette.issue_year else None

        batch: list[Trademark] = []
        row_count = 0
        batch_size = settings.worker_batch_size
        # Pass gazette_type explicitly — the stored path is `<digest>_<orig>.pdf`,
        # so the filename's first letter is the digest, not A/B.
        for section in processor.extract_records(pdf_path, gazette_type=letter):
            rt = infer_record_type(letter, section)
            logo_path = (
                _resolve_logo_path(section, image_subdir_rel, image_root) if image_subdir_rel else None
            )
            batch.append(section_to_trademark(gazette.id, rt, section, logo_path=logo_path))
            if len(batch) >= batch_size:
                session.add_all(batch)
                session.commit()
                row_count += len(batch)
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()
            row_count += len(batch)

        gazette.status = GazetteStatus.completed
        gazette.row_count = row_count
        gazette.processed_at = datetime.now(UTC)
        gazette.error_message = None
        session.add(gazette)
        session.commit()

        logger.info("Ingested %s rows from %s", row_count, pdf_path.name)
        return {"gazette_id": gazette_id, "row_count": row_count, "status": "completed"}

    except Exception as e:
        logger.exception("Ingest failed for gazette %s", gazette_id)
        # The error handler needs a fresh session state — any SQLAlchemy
        # error leaves the prior transaction unusable. Roll back first.
        try:
            session.rollback()
            g = session.get(Gazette, uuid.UUID(gazette_id))
            if g is not None:
                # Roll back any rows committed in earlier batches so the DB
                # never holds half a gazette under status=failed.
                purged_on_fail = _purge_trademarks(session, g.id)
                if purged_on_fail:
                    logger.info(
                        "Rolled back %d partial rows after ingest failure",
                        purged_on_fail,
                    )
                g.status = GazetteStatus.failed
                g.error_message = str(e)[:4000]
                g.row_count = 0
                g.processed_at = None
                session.add(g)
                session.commit()
        except Exception:
            session.rollback()
            logger.exception(
                "Could not flip gazette to failed-state after ingest error; "
                "row may be stuck in 'processing' until manual cleanup"
            )
        raise
    finally:
        # Release advisory lock explicitly before closing the connection.
        # Closing alone would release it (lock is session-scoped), but
        # the explicit unlock keeps the lifecycle traceable in logs.
        _release_advisory_lock(session, gid)
        session.close()
