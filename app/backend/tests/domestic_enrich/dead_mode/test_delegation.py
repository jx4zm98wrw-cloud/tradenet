import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import worker.domestic_sweep as ds
from api.db.models import DomesticSweepControl as C
from api.settings import get_settings


@pytest_asyncio.fixture(autouse=True)
async def _seed_control():
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
async def test_dead_mode_delegates_to_dead_runner(db_session, monkeypatch):
    await db_session.execute(update(C).where(C.id == 1).values(mode="dead"))
    await db_session.commit()

    called = {}

    async def fake_dead(session, *, enqueue_next, http_session=None):
        called["yes"] = True
        return {"status": "running", "did": 7}

    # The sweep lazily imports `from domestic_enrich.dead_mode import run_chunk`,
    # so patch the name on that package.
    import domestic_enrich.dead_mode as dm

    monkeypatch.setattr(dm, "run_chunk", fake_dead)

    res = await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert called.get("yes") is True
    assert res == {"status": "running", "did": 7}


@pytest.mark.asyncio
async def test_normal_mode_does_not_delegate(db_session, monkeypatch):
    # mode stays 'normal'; stub the normal path's work-list so it doesn't hit network.
    async def fake_iter(_s):
        return []

    monkeypatch.setattr(ds, "iter_domestic_appnos", fake_iter)

    import domestic_enrich.dead_mode as dm

    def _boom(*a, **k):
        raise AssertionError("dead runner must NOT be called in normal mode")

    monkeypatch.setattr(dm, "run_chunk", _boom)

    res = await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert res["did"] == 0  # empty work-list, normal path, no delegation
