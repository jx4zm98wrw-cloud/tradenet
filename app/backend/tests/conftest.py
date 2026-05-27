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
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("TM_DATABASE_URL", "postgresql+asyncpg://tm:tm@localhost:5435/tm")
os.environ.setdefault("TM_DATABASE_URL_SYNC", "postgresql+psycopg2://tm:tm@localhost:5435/tm")
os.environ.setdefault("TM_REDIS_URL", "redis://localhost:6380/0")
# Force NullPool in the session engine (session.py keys off this env). Tests
# create a new event loop per test (pytest-asyncio default), and asyncpg pool
# connections are bound to whichever loop opened them — a shared QueuePool
# across loops raises "Future attached to a different loop". Production code
# uses QueuePool because uvicorn workers own a durable loop per process.
os.environ.setdefault("TM_ENV", "test")


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def authed_client() -> AsyncIterator[AsyncClient]:
    """Yields an AsyncClient pre-authenticated as an admin user.

    Tests that hit endpoints requiring auth (POST /watchlists, gazettes
    upload, /admin/*, etc.) should use this fixture instead of `client`.
    The user is created fresh per test, logged in, given the bearer token
    on every subsequent request, and deleted on teardown.
    """
    import uuid

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from api.auth import hash_password
    from api.db.models import User, UserRole
    from api.main import app
    from api.settings import get_settings

    email = f"authed-client-{uuid.uuid4()}@test.local"
    password = "test-password-1234567890"  # 22 chars, passes min-length

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add(
            User(
                id=uuid.uuid4(),
                email=email,
                password_hash=hash_password(password),
                name="Test Admin",
                role=UserRole.admin,
                is_active=True,
                token_version=0,
            )
        )
        await s.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        login = await c.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        token = login.json()["accessToken"]
        c.headers["Authorization"] = f"Bearer {token}"
        try:
            yield c
        finally:
            async with Session() as s:
                await s.execute(delete(User).where(User.email == email))
                await s.commit()
            await engine.dispose()
