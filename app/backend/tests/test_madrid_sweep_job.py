"""worker.madrid_sweep.run_chunk — chunk processing + control honoring.

enrich_one and iter_madrid_irns are monkeypatched so the test needs no live
WIPO, no worker, and no real cache writes. Synthetic IRNs (never cached) keep
the work-list deterministic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, insert, select, update

from api.db.models import MadridSweepControl
import worker.madrid_sweep as ms


async def _aslist(items):
    return items


class _EmptyCache:
    """Stand-in for a Path whose .glob('*.html') yields nothing."""

    def glob(self, _pat):
        return iter(())


async def _reset(session, **vals) -> None:
    await session.execute(delete(MadridSweepControl))
    base = dict(id=1, status="running", cap=None, delay=0.0, jitter=0.0,
                chunk_size=2, processed=0, ok=0, failed=0)
    base.update(vals)
    await session.execute(insert(MadridSweepControl).values(**base))
    await session.commit()


@pytest.mark.asyncio
async def test_run_chunk_processes_chunk_and_reenqueues(db_session, monkeypatch):
    await _reset(db_session, chunk_size=2)

    async def fake_enrich(session, irn, cache, **kw):
        return None

    monkeypatch.setattr(ms, "enrich_one", fake_enrich)
    monkeypatch.setattr(ms, "iter_madrid_irns", lambda s: _aslist(["A1", "A2", "A3"]))
    monkeypatch.setattr(ms, "_cache_dir", lambda: _EmptyCache())

    calls = []
    out = await ms.run_chunk(db_session, enqueue_next=lambda: calls.append(1))

    row = (await db_session.execute(select(MadridSweepControl).where(MadridSweepControl.id == 1))).scalar_one()
    assert out["did"] == 2
    assert row.ok == 2 and row.processed == 2
    assert calls == [1]


@pytest.mark.asyncio
async def test_run_chunk_honors_pause_midchunk(db_session, monkeypatch):
    await _reset(db_session, chunk_size=10)
    seen = {"n": 0}

    async def fake_enrich(session, irn, cache, **kw):
        seen["n"] += 1
        if seen["n"] == 1:
            await session.execute(
                update(MadridSweepControl).where(MadridSweepControl.id == 1).values(status="paused")
            )
            await session.commit()
        return None

    monkeypatch.setattr(ms, "enrich_one", fake_enrich)
    monkeypatch.setattr(ms, "iter_madrid_irns", lambda s: _aslist(["A1", "A2", "A3"]))
    monkeypatch.setattr(ms, "_cache_dir", lambda: _EmptyCache())

    calls = []
    out = await ms.run_chunk(db_session, enqueue_next=lambda: calls.append(1))
    assert out["did"] == 1
    assert calls == []


@pytest.mark.asyncio
async def test_run_chunk_circuit_breaker_pauses(db_session, monkeypatch):
    await _reset(db_session, chunk_size=20)

    async def boom(session, irn, cache, **kw):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(ms, "enrich_one", boom)
    monkeypatch.setattr(ms, "iter_madrid_irns", lambda s: _aslist([f"A{i}" for i in range(10)]))
    monkeypatch.setattr(ms, "_cache_dir", lambda: _EmptyCache())

    out = await ms.run_chunk(db_session, enqueue_next=lambda: None)
    row = (await db_session.execute(select(MadridSweepControl).where(MadridSweepControl.id == 1))).scalar_one()
    assert row.status == "paused"
    assert row.failed >= 5
    assert "circuit breaker" in (row.last_error or "")
