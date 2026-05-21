"""Async SQLAlchemy engine + session.

asyncpg connections are bound to whichever event loop opened them. To stay
robust across test loops, deploy reloads, and ASGI lifespan reuse, the pool
uses `NullPool` — every request opens a fresh connection and closes it on
release. This costs latency vs a long-lived pool, but keeps correctness
unambiguous; swap to `pool_size=N, max_overflow=M` once a single durable
event loop owns the process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from ..settings import get_settings

_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    echo=False,
    future=True,
    poolclass=NullPool,
)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session, ensuring teardown on response."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
