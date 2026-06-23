"""worker.madrid_sweep.run_chunk — fast-mode delegation.

With mode='fast' on the control row, run_chunk must hand the whole chunk to
madrid_enrich.fast_mode.run_chunk (lazily imported), mirroring the domestic
dead-mode delegation. enrich_one / the network are never reached.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import worker.madrid_sweep as ms
from api.db.models import MadridSweepControl as C
from api.settings import get_settings


@pytest_asyncio.fixture(autouse=True)
async def _seed_control():
    """Seed the singleton control row (id=1) running+fast, restore to idle/normal
    on teardown so a full-suite run never leaves the shared dev DB's live sweep
    state corrupted."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="running", mode="normal", concurrency=0))
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="idle", mode="normal", concurrency=0))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_chunk_delegates_to_fast_mode_when_mode_fast(db_session, monkeypatch):
    await db_session.execute(update(C).where(C.id == 1).values(status="running", mode="fast"))
    await db_session.commit()

    called = {}

    async def _fake_fast(session, *, enqueue_next, http_session=None):
        called["fast"] = True
        return {"status": "running", "did": 0}

    # The sweep lazily imports `from madrid_enrich.fast_mode import run_chunk`,
    # so patch the name on that package.
    import madrid_enrich.fast_mode as fm

    monkeypatch.setattr(fm, "run_chunk", _fake_fast)

    out = await ms.run_chunk(db_session, enqueue_next=lambda: None)
    assert called.get("fast") is True
    assert out == {"status": "running", "did": 0}


@pytest.mark.asyncio
async def test_run_chunk_normal_mode_does_not_delegate(db_session, monkeypatch):
    # mode stays 'normal'; stub the work-list empty so the normal path does no
    # network, and make the fast runner explode if it's ever reached.
    async def _empty_irns(_s):
        return []

    monkeypatch.setattr(ms, "iter_madrid_irns", _empty_irns)
    monkeypatch.setattr(ms, "_cache_dir", lambda: _EmptyCache())

    import madrid_enrich.fast_mode as fm

    def _boom(*a, **k):
        raise AssertionError("fast runner must NOT be called in normal mode")

    monkeypatch.setattr(fm, "run_chunk", _boom)

    out = await ms.run_chunk(db_session, enqueue_next=lambda: None)
    assert out["did"] == 0


class _EmptyCache:
    """Stand-in for a Path whose .glob('*.html') yields nothing."""

    def glob(self, _pat):
        return iter(())
