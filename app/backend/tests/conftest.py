"""Pytest configuration — httpx AsyncClient against the live ASGI app.

Starlette's sync TestClient spawns a fresh event loop per request, which
crashes the async-SQLAlchemy / asyncpg pool ("another operation is in
progress"). AsyncClient + ASGITransport drives the app in the same loop
the test runs in, which is what asyncpg needs.

Tests use the dev DB by default. CI overrides TM_DATABASE_URL[_SYNC] to
point at a docker-compose-spawned Postgres dedicated to CI.
"""

from __future__ import annotations

import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("TM_DATABASE_URL", "postgresql+asyncpg://tm:tm@localhost:5435/tm")
os.environ.setdefault("TM_DATABASE_URL_SYNC", "postgresql+psycopg2://tm:tm@localhost:5435/tm")
os.environ.setdefault("TM_REDIS_URL", "redis://localhost:6380/0")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
