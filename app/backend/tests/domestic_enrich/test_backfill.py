import pytest

import domestic_enrich.backfill as bf
from domestic_enrich.backfill import CircuitBreaker, run_backfill
from domestic_enrich.enrich import EnrichOutcome


def test_circuit_breaker_trips_after_consecutive_failures():
    cb = CircuitBreaker(max_consecutive=3)
    cb.record_failure()
    cb.record_failure()
    assert cb.tripped is False
    cb.record_failure()
    assert cb.tripped is True
    cb.record_success()
    assert cb.tripped is False


@pytest.mark.asyncio
async def test_run_backfill_counts_and_skips(db_session, tmp_path, monkeypatch):
    appnos = ["4-2026-00001", "4-2026-00002", "4-2026-00003"]

    async def fake_iter(session):
        return appnos

    calls = []

    async def fake_enrich(session, appno, *, cache_dir, use_cache):
        calls.append(appno)
        # one "skip" (unchanged), the rest written
        return EnrichOutcome.UNCHANGED if appno == "4-2026-00002" else EnrichOutcome.WROTE

    monkeypatch.setattr(bf, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(bf, "enrich_one", fake_enrich)

    res = await run_backfill(db_session, cache_dir=tmp_path, delay=0.0, jitter=0.0)
    assert res.attempted == 3
    assert res.written == 2
    assert res.skipped == 1
    assert calls == appnos


@pytest.mark.asyncio
async def test_run_backfill_counts_not_found(db_session, tmp_path, monkeypatch):
    appnos = ["4-2026-00001", "4-2026-00002"]

    async def fake_iter(session):
        return appnos

    async def fake_enrich(session, appno, *, cache_dir, use_cache):
        return EnrichOutcome.NOT_FOUND if appno == "4-2026-00002" else EnrichOutcome.WROTE

    monkeypatch.setattr(bf, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(bf, "enrich_one", fake_enrich)

    res = await run_backfill(db_session, cache_dir=tmp_path, delay=0.0, jitter=0.0)
    assert res.written == 1
    assert res.not_found == 1
    assert res.failed == 0
    assert res.circuit_broke is False  # a not_found is not a failure
