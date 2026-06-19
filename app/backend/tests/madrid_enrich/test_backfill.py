"""Tests for the Madrid enrichment backfill loop (mocked enrich — no network)."""

from __future__ import annotations

import uuid

import pytest

import madrid_enrich.backfill as bf
from api.db.models import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from madrid_enrich.backfill import (
    BackfillResult,
    CircuitBreaker,
    iter_madrid_irns,
    run_backfill,
)


async def _async_return(value):
    return value


async def _make_gazette(session) -> Gazette:
    gid = uuid.uuid4()
    g = Gazette(
        id=gid,
        filename="fake.pdf",
        sha256=gid.hex + gid.hex[:32],
        gazette_type=GazetteType.B,
        issue_year=2026,
        issue_number=99,
        storage_path="/tmp/fake.pdf",
        size_bytes=42,
        status=GazetteStatus.completed,
        row_count=0,
    )
    session.add(g)
    await session.flush()
    return g


@pytest.mark.asyncio
async def test_iter_madrid_irns_returns_distinct_madrid_only(db_session):
    g = await _make_gazette(db_session)
    db_session.add_all(
        [
            # madrid_renewal: madrid_number only -> mark_category derives to madrid_renewal
            Trademark(gazette_id=g.id, record_type=RecordType.B_madrid, madrid_number="1266721"),
            # duplicate IRN -> must be de-duplicated
            Trademark(gazette_id=g.id, record_type=RecordType.B_madrid, madrid_number="1266721"),
            # domestic_registration: certificate + application -> excluded
            Trademark(
                gazette_id=g.id,
                record_type=RecordType.B_domestic,
                certificate_number="4-2025-1",
                application_number="4-2025-1",
            ),
        ]
    )
    await db_session.flush()

    irns = await iter_madrid_irns(db_session)

    assert "1266721" in irns
    assert irns.count("1266721") == 1
    assert "4-2025-1" not in irns


def test_circuit_breaker_trips_after_consecutive_failures():
    cb = CircuitBreaker(max_consecutive=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.tripped is False
    cb.record_failure()
    assert cb.tripped is True


def test_circuit_breaker_resets_on_success():
    cb = CircuitBreaker(max_consecutive=3)
    cb.record_failure()
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    assert cb.tripped is False


@pytest.mark.asyncio
async def test_run_backfill_respects_limit_and_counts(db_session, tmp_path, monkeypatch):
    calls = []

    async def fake_enrich(session, irn, cache_dir, **kw):
        calls.append(irn)
        return True

    monkeypatch.setattr(bf, "enrich_one", fake_enrich)
    monkeypatch.setattr(bf, "iter_madrid_irns", lambda s: _async_return(["a", "b", "c", "d", "e"]))

    res = await run_backfill(db_session, cache_dir=tmp_path, limit=3, delay=0.0)
    assert isinstance(res, BackfillResult)
    assert res.attempted == 3 and res.written == 3
    assert calls == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_run_backfill_circuit_breaks(db_session, tmp_path, monkeypatch):
    async def boom(session, irn, cache_dir, **kw):
        raise RuntimeError("WIPO 429")

    monkeypatch.setattr(bf, "enrich_one", boom)
    monkeypatch.setattr(bf, "iter_madrid_irns", lambda s: _async_return(list("abcdefghij")))

    res = await run_backfill(db_session, cache_dir=tmp_path, max_consecutive=3, delay=0.0)
    assert res.failed == 3 and res.circuit_broke is True
    assert res.attempted == 3
