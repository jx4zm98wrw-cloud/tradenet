"""Async SQLAlchemy engine + session.

Pool strategy is env-gated:
  - **Test / dev** (`TM_ENV` ∈ {test, testing, ci}): `NullPool`. asyncpg
    binds connections to whichever event loop opened them, and pytest-asyncio
    runs each test in its own loop; sharing a pool across loops causes
    "Future attached to a different loop" errors. NullPool sidesteps the
    issue at the cost of a fresh connection per request (~10-50 ms latency).
  - **Everything else** (default + staging + production): `QueuePool` with
    `pool_size=20, max_overflow=10, pool_pre_ping=True`. Uvicorn workers
    own a durable loop per process, so pool reuse is safe and necessary to
    sustain real traffic (NullPool would exhaust Postgres `max_connections`
    at modest concurrency).

`pool_pre_ping=True` cheaply checks each checked-out connection with a
`SELECT 1` and reconnects if the connection has been dropped (Postgres
restart, NAT timeout, etc.) — costs ~0.2 ms per checkout in exchange for
not crashing on stale connections.

`pool_recycle=3600` proactively rotates connections older than 1 hour to
avoid hitting Postgres's `idle_in_transaction_session_timeout` or load-
balancer idle disconnect.

Per-engine `connect_args` set a 30s statement_timeout on the PostgreSQL
side, so a runaway query holds a pool slot for at most 30 seconds rather
than indefinitely.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..settings import get_settings

_settings = get_settings()

# Tests/CI use NullPool to avoid asyncpg cross-event-loop binding errors.
_USE_NULLPOOL = (_settings.env or "").lower().strip() in {"test", "testing", "ci"}

_engine_kwargs: dict = {
    "echo": False,
    "future": True,
    # 30 s server-side statement timeout — caps slowest-query damage to a
    # single pool slot rather than letting it block forever.
    "connect_args": {"server_settings": {"statement_timeout": "30000"}},
}

if _USE_NULLPOOL:
    _engine_kwargs["poolclass"] = NullPool
else:
    # Production / staging / default: durable QueuePool. asyncpg uses
    # AsyncAdaptedQueuePool internally when poolclass is omitted; pool_size
    # tunables are passed as-is.
    _engine_kwargs.update(
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

engine = create_async_engine(_settings.database_url, **_engine_kwargs)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session, ensuring teardown on response."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
