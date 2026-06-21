import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import domestic_enrich.dead_mode.runner as r
from api.db.models import DomesticSweepControl as C
from api.settings import get_settings
from domestic_enrich.dead_mode.controller import CEILING, Outcome


@pytest_asyncio.fixture(autouse=True)
async def _seed_dead_control():
    """Seed id=1 as running+dead before each test; restore idle/normal after, so
    the dev singleton is never left in a dead/running state."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(
            insert(C).values(id=1, status="running", mode="dead", concurrency=0, processed=0, ok=0, failed=0)
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="idle", mode="normal", concurrency=0))
        await s.commit()
    await engine.dispose()


def _stub_common(monkeypatch, tmp_path, appnos):
    async def fake_iter(_session):
        return appnos

    monkeypatch.setattr(r, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(r, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(r, "_uncached", lambda all_, _cache: list(all_))
    monkeypatch.setattr(r, "COOLDOWN_S", 0.0)


@pytest.mark.asyncio
async def test_returns_immediately_when_not_dead(db_session, tmp_path, monkeypatch):
    await db_session.execute(update(C).where(C.id == 1).values(mode="normal"))
    await db_session.commit()
    monkeypatch.setattr(r, "_cache_dir", lambda: tmp_path)
    res = await r.run_chunk(db_session, enqueue_next=lambda: None)
    assert res["did"] == 0


@pytest.mark.asyncio
async def test_processes_successes_and_ramps_concurrency(db_session, tmp_path, monkeypatch):
    appnos = [f"4-2026-{n:05d}" for n in range(60)]
    _stub_common(monkeypatch, tmp_path, appnos)

    def fake_fetch(appno, _cache, _http):
        return (appno, Outcome.SUCCESS, object())

    stored: list[str] = []

    async def fake_store(_session, appno, _result):
        stored.append(appno)

    monkeypatch.setattr(r, "_fetch_outcome", fake_fetch)
    monkeypatch.setattr(r, "_store_success", fake_store)

    res = await r.run_chunk(db_session, enqueue_next=lambda: None)

    assert res["did"] == 60
    assert len(stored) == 60
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    # 60 clean marks = 3 windows of +1 each from START=2 -> ended above START.
    assert row.concurrency > 2
    assert row.ok == 60 and row.failed == 0


@pytest.mark.asyncio
async def test_sustained_blocks_revert_to_normal_and_pause(db_session, tmp_path, monkeypatch):
    appnos = [f"4-2026-{n:05d}" for n in range(80)]
    _stub_common(monkeypatch, tmp_path, appnos)

    def fake_block(appno, _cache, _http):
        return (appno, Outcome.BLOCK, None)

    monkeypatch.setattr(r, "_fetch_outcome", fake_block)

    enq: list[int] = []
    res = await r.run_chunk(db_session, enqueue_next=lambda: enq.append(1))

    assert res["status"] == "paused"
    assert enq == []  # gave up — did NOT re-enqueue
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert row.mode == "normal"
    assert row.status == "paused"
    assert "block" in (row.last_error or "").lower()


@pytest.mark.asyncio
async def test_reenqueues_when_work_remains(db_session, tmp_path, monkeypatch):
    # 100 marks (== DEAD_CHUNK_MARKS) all succeed, but the work-list is longer,
    # so after the chunk caps out it must re-enqueue.
    appnos = [f"4-2026-{n:05d}" for n in range(200)]
    _stub_common(monkeypatch, tmp_path, appnos)
    monkeypatch.setattr(r, "_fetch_outcome", lambda a, c, h: (a, Outcome.SUCCESS, object()))

    async def fake_store(_s, _a, _r):
        return None

    monkeypatch.setattr(r, "_store_success", fake_store)

    enq: list[int] = []
    res = await r.run_chunk(db_session, enqueue_next=lambda: enq.append(1))
    # Bounded per job: the wave loop stops once `did` reaches DEAD_CHUNK_MARKS,
    # but a wave is atomic, so the final wave may overshoot by up to its width
    # (concurrency, capped at CEILING). Documented "bounded, not exact" behavior.
    assert r.DEAD_CHUNK_MARKS <= res["did"] < r.DEAD_CHUNK_MARKS + CEILING
    assert enq == [1]  # more remain -> re-enqueued
