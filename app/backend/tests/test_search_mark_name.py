"""mark_name is serialized on TrademarkOut (rides along inside /search items[].mark)."""

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

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000c1")
_MARK1 = uuid.UUID("e0000000-0000-4000-8000-0000000000c2")


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
                filename="B_TEST_mark_name.pdf",
                sha256="mark_name_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # Figurative domestic mark whose display name was resolved into mark_name.
        s.add(
            Trademark(
                id=_MARK1,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="MN-2099-1",
                mark_sample=None,
                mark_name="TRADAGUI",
                applicant_name="CÔNG TY DƯỢC PHẨM",
                publication_date_441=date(2099, 1, 1),
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
async def test_search_serializes_mark_name(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"gazette_id": str(_GZ), "mode": "text", "threshold": 0, "limit": 50},
    )
    assert r.status_code == 200
    hit = next(it for it in r.json()["items"] if it["mark"]["application_number"] == "MN-2099-1")
    assert hit["mark"]["mark_name"] == "TRADAGUI"
