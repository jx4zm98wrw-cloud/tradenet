"""Async SQLAlchemy engine + session."""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from typing import AsyncIterator

from ..settings import get_settings


_settings = get_settings()

engine = create_async_engine(_settings.database_url, echo=False, future=True)
async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — yields a session, ensuring teardown on response."""
    async with async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
