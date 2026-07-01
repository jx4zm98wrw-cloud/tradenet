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
from collections.abc import AsyncIterator, Iterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from api.db.models import UserRole

os.environ.setdefault("TM_DATABASE_URL", "postgresql+asyncpg://tm:tm@localhost:5435/tm")
os.environ.setdefault("TM_DATABASE_URL_SYNC", "postgresql+psycopg2://tm:tm@localhost:5435/tm")
os.environ.setdefault("TM_REDIS_URL", "redis://localhost:6380/0")
# Force NullPool in the session engine (session.py keys off this env). Tests
# create a new event loop per test (pytest-asyncio default), and asyncpg pool
# connections are bound to whichever loop opened them — a shared QueuePool
# across loops raises "Future attached to a different loop". Production code
# uses QueuePool because uvicorn workers own a durable loop per process.
os.environ.setdefault("TM_ENV", "test")


@pytest.fixture(autouse=True)
def _clear_facet_cache() -> Iterator[None]:
    """Isolate the in-process facet TTL cache between tests — otherwise one test's
    seeded counts could serve a later test with the same facet+filter signature."""
    from api.routes import facets

    facets._facet_cache.clear()
    yield
    facets._facet_cache.clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from api.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    """A plain async DB session for unit tests that hit the DB directly
    (e.g. the madrid_enrich store/enrich tests). Rolls back on teardown so
    each test sees a clean slate and leaves no rows behind."""
    from api.db.session import async_session

    async with async_session() as session:
        try:
            yield session
        finally:
            await session.rollback()


async def _make_role_client(role: UserRole) -> AsyncIterator[AsyncClient]:
    """Shared body for the role-specific fixtures below.

    Creates a fresh user with the requested role, logs them in, attaches
    the bearer token to every subsequent request, and deletes the user
    on teardown. Each test gets its own user so parallel runs and
    fixture teardown can't interfere.
    """
    import uuid

    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from api.auth import hash_password
    from api.db.models import User
    from api.main import app
    from api.settings import get_settings

    email = f"role-{role.value}-{uuid.uuid4()}@test.local"
    password = "test-password-1234567890"  # 22 chars, passes min-length

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        s.add(
            User(
                id=uuid.uuid4(),
                email=email,
                password_hash=hash_password(password),
                name=f"Test {role.value.title()}",
                role=role,
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


@pytest_asyncio.fixture
async def authed_client() -> AsyncIterator[AsyncClient]:
    """AsyncClient pre-authenticated as an admin user. Use for endpoints
    requiring auth where role doesn't matter (POST /watchlists), or for
    explicitly-admin endpoints (GET /gazettes)."""
    from api.db.models import UserRole

    async for c in _make_role_client(UserRole.admin):
        yield c


@pytest_asyncio.fixture
async def editor_client() -> AsyncIterator[AsyncClient]:
    """AsyncClient pre-authenticated as an editor. Used to test the
    admin/editor split — editors should pass role checks like
    require_role(admin, editor) but be rejected by require_admin."""
    from api.db.models import UserRole

    async for c in _make_role_client(UserRole.editor):
        yield c


@pytest_asyncio.fixture
async def viewer_client() -> AsyncIterator[AsyncClient]:
    """AsyncClient pre-authenticated as a read-only viewer. Used to assert
    403s on mutation/admin endpoints — proves the role gate fires."""
    from api.db.models import UserRole

    async for c in _make_role_client(UserRole.viewer):
        yield c
