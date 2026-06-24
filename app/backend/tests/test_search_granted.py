"""Unified Granted filter (trademarks.vn_grant_date) on /search + /facets/granted."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000b1")
_MARK1 = uuid.UUID("e0000000-0000-4000-8000-0000000000b2")
_MARK2 = uuid.UUID("e0000000-0000-4000-8000-0000000000b3")


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="B_TEST_granted.pdf",
                sha256="granted_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # mark1: has a resolved VN grant date → counted by Granted filter.
        s.add(
            Trademark(
                id=_MARK1,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="GR-2099-1",
                vn_grant_date=date(2024, 12, 9),
                publication_date_441=date(2099, 1, 1),
            )
        )
        # mark2: no grant date → excluded.
        s.add(
            Trademark(
                id=_MARK2,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="GR-2099-2",
                vn_grant_date=None,
                publication_date_441=date(2099, 1, 2),
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_granted_filters_to_marks_with_grant_date(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"granted": "true", "gazette_id": str(_GZ), "mode": "text", "threshold": 0, "limit": 50},
    )
    assert r.status_code == 200
    ids = {item["mark"]["id"] for item in r.json()["items"]}
    assert str(_MARK1) in ids
    assert str(_MARK2) not in ids


@pytest.mark.asyncio
async def test_search_without_granted_returns_both(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"gazette_id": str(_GZ), "mode": "text", "threshold": 0, "limit": 50},
    )
    assert r.status_code == 200
    ids = {item["mark"]["id"] for item in r.json()["items"]}
    assert str(_MARK1) in ids
    assert str(_MARK2) in ids


@pytest.mark.asyncio
async def test_facet_granted_counts_only_granted(client: AsyncClient) -> None:
    r = await client.get("/api/v1/facets/granted", params={"gazette_id": str(_GZ)})
    assert r.status_code == 200
    buckets = r.json()
    granted = next(b for b in buckets if b["key"] == "granted")
    assert granted["count"] == 1
