import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import worker.domestic_sweep as ds
from api.db.models import DomesticSweepControl as C
from api.settings import get_settings


@pytest_asyncio.fixture(autouse=True)
async def _restore_singleton():
    """Seed id=1 as idle before each test; restore on teardown so the dev DB
    is never left in a corrupt sweep state after a suite run."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="idle", chunk_size=25, processed=0, ok=0, failed=0))
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="idle", chunk_size=25, processed=0, ok=0, failed=0))
        await s.commit()
    await engine.dispose()


async def _set_running(session, **vals):
    await session.execute(update(C).where(C.id == 1).values(status="running", **vals))
    await session.commit()


@pytest.mark.asyncio
async def test_chunk_processes_uncached_and_stops_at_chunk_size(db_session, tmp_path, monkeypatch):
    await _set_running(db_session, chunk_size=2, delay=0.0, jitter=0.0)

    async def fake_iter(session):
        return ["4-2026-00001", "4-2026-00002", "4-2026-00003"]

    seen = []

    async def fake_enrich(session, appno, cache, *, http_session=None, use_cache=True):
        seen.append(appno)
        return True

    monkeypatch.setattr(ds, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(ds, "enrich_one", fake_enrich)
    monkeypatch.setattr(ds, "_cache_dir", lambda: tmp_path)

    enq = []
    res = await ds.run_chunk(db_session, enqueue_next=lambda: enq.append(1))

    assert res["did"] == 2
    assert seen == ["4-2026-00001", "4-2026-00002"]
    assert enq == [1]
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert row.processed == 2
    assert row.current_appno == "4-2026-00002"


@pytest.mark.asyncio
async def test_chunk_noop_when_not_running(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "_cache_dir", lambda: tmp_path)
    res = await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert res["did"] == 0


@pytest.mark.asyncio
async def test_uncached_filter_uses_vnid_mapping(db_session, tmp_path, monkeypatch):
    (tmp_path / "VN4202600001.html").write_text("x", encoding="utf-8")
    await _set_running(db_session, chunk_size=10, delay=0.0, jitter=0.0)

    async def fake_iter(session):
        return ["4-2026-00001", "4-2026-00002"]

    seen = []

    async def fake_enrich(session, appno, cache, *, http_session=None, use_cache=True):
        seen.append(appno)
        return True

    monkeypatch.setattr(ds, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(ds, "enrich_one", fake_enrich)
    monkeypatch.setattr(ds, "_cache_dir", lambda: tmp_path)

    await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert seen == ["4-2026-00002"]


@pytest.mark.asyncio
async def test_block_pauses_sweep_immediately(db_session, tmp_path, monkeypatch):
    # A NoipBlockedError on the first mark must pause the whole sweep at once —
    # not work through the chunk or re-enqueue — so a ban can't escalate.
    await _set_running(db_session, chunk_size=25, delay=0.0, jitter=0.0)

    async def fake_iter(session):
        return ["4-2026-00001", "4-2026-00002", "4-2026-00003"]

    seen = []

    async def fake_enrich(session, appno, cache, *, http_session=None, use_cache=True):
        seen.append(appno)
        raise ds.NoipBlockedError("VN4202600001", 429, retry_after=120.0)

    monkeypatch.setattr(ds, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(ds, "enrich_one", fake_enrich)
    monkeypatch.setattr(ds, "_cache_dir", lambda: tmp_path)

    enq = []
    await ds.run_chunk(db_session, enqueue_next=lambda: enq.append(1))

    assert seen == ["4-2026-00001"]  # stopped after the first, no further marks
    assert enq == []  # NOT re-enqueued
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert row.status == "paused"
    assert "block" in (row.last_error or "").lower()
