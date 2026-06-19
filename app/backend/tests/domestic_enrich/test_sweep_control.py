"""Admin domestic-sweep control endpoints — state transitions + guards.

Enqueue is monkeypatched to a no-op so no worker/redis is needed. The control
row is reset to idle before each test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import api.routes.domestic_sweep as routes
from api.db.models import DomesticSweepControl
from api.settings import get_settings


@pytest_asyncio.fixture(autouse=True)
async def reset_and_stub(monkeypatch):
    monkeypatch.setattr(routes, "_enqueue_chunk", lambda: None)
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(
            update(DomesticSweepControl)
            .where(DomesticSweepControl.id == 1)
            .values(
                status="idle",
                cap=None,
                delay=5.0,
                jitter=2.0,
                chunk_size=25,
                processed=0,
                ok=0,
                failed=0,
                current_appno=None,
                next_appno=None,
                last_error=None,
            )
        )
        await s.commit()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_get_status(authed_client: AsyncClient):
    r = await authed_client.get("/api/v1/admin/domestic-sweep")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "idle"


@pytest.mark.asyncio
async def test_start_then_pause_resume_stop(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/admin/domestic-sweep/start", json={"cap": 100, "delay": 3.0})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "running" and d["cap"] == 100 and d["delay"] == 3.0 and d["started_at"]

    r = await authed_client.post("/api/v1/admin/domestic-sweep/pause")
    assert r.status_code == 200 and r.json()["status"] == "paused"

    r = await authed_client.post("/api/v1/admin/domestic-sweep/resume")
    assert r.status_code == 200 and r.json()["status"] == "running"

    r = await authed_client.post("/api/v1/admin/domestic-sweep/stop")
    assert r.status_code == 200 and r.json()["status"] == "idle"


@pytest.mark.asyncio
async def test_start_again_is_409(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/admin/domestic-sweep/start", json={})
    assert r.status_code == 200
    r = await authed_client.post("/api/v1/admin/domestic-sweep/start", json={})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_illegal_transitions_conflict(authed_client: AsyncClient):
    # idle → pause/resume must 409
    assert (await authed_client.post("/api/v1/admin/domestic-sweep/pause")).status_code == 409
    assert (await authed_client.post("/api/v1/admin/domestic-sweep/resume")).status_code == 409
    # idle → stop must 409
    assert (await authed_client.post("/api/v1/admin/domestic-sweep/stop")).status_code == 409


@pytest.mark.asyncio
async def test_config_updates_cadence(authed_client: AsyncClient):
    r = await authed_client.patch(
        "/api/v1/admin/domestic-sweep/config", json={"delay": 10.0, "jitter": 1.5, "chunk_size": 50}
    )
    assert r.status_code == 200
    d = r.json()
    assert d["delay"] == 10.0 and d["jitter"] == 1.5 and d["chunk_size"] == 50


@pytest.mark.asyncio
async def test_requires_admin(viewer_client: AsyncClient):
    assert (await viewer_client.get("/api/v1/admin/domestic-sweep")).status_code == 403
    assert (await viewer_client.post("/api/v1/admin/domestic-sweep/start", json={})).status_code == 403
