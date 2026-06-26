"""Mark-only default search: `q` matches the mark (name/sample + IDs), not the owner.

The free-text box stops matching `applicant_name`; applicant/class/agent filtering
stays available via the sidebar facet params (`applicant`/`nice_class`/`ip_agency`).
See docs/superpowers/specs/2026-06-26-search-applicant-prefix-design.md.
"""

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

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000d1")
_MARK1 = uuid.UUID("e0000000-0000-4000-8000-0000000000d2")
_MARK2 = uuid.UUID("e0000000-0000-4000-8000-0000000000d3")


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
                filename="B_TEST_mark_only.pdf",
                sha256="mark_only_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # Mark whose name is WIDGET but whose OWNER is ACMECORP (mark_sample NULL).
        # "acmecorp" must NOT recall this by free text; "widget" must.
        s.add(
            Trademark(
                id=_MARK1,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="MO-2099-1",
                mark_sample=None,
                mark_name="WIDGET",
                applicant_name="ACMECORP",
                publication_date_441=date(2099, 1, 1),
            )
        )
        # Fresh-ingest mark: wordmark present, mark_name not yet backfilled.
        # Proves mark_sample recall is intact (augment-not-swap).
        s.add(
            Trademark(
                id=_MARK2,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="MO-2099-2",
                mark_sample="FOOBRAND",
                mark_name=None,
                applicant_name="OTHERCO",
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
async def test_applicant_not_recalled_by_default_text(client: AsyncClient) -> None:
    # Owner ACMECORP is no longer matched by the default free-text box.
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "acmecorp", "mode": "text", "threshold": 0, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_applicant_not_recalled_by_default_phonetic(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "acmecorp", "mode": "phonetic", "threshold": 0.4, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_applicant_facet_still_filters(client: AsyncClient) -> None:
    # The sidebar facet param is unchanged — the owner is still reachable via `applicant=`.
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"applicant": "acmecorp", "mode": "text", "threshold": 0, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    appnos = [it["mark"]["application_number"] for it in r.json()["items"]]
    assert "MO-2099-1" in appnos


@pytest.mark.asyncio
async def test_mark_name_still_matches(client: AsyncClient) -> None:
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "widget", "mode": "text", "threshold": 0.4, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    appnos = [it["mark"]["application_number"] for it in r.json()["items"]]
    assert "MO-2099-1" in appnos


@pytest.mark.asyncio
async def test_fresh_ingest_mark_sample_still_matches(client: AsyncClient) -> None:
    # Augment-not-swap: a fresh-ingest mark (mark_sample set, mark_name NULL) is still found.
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"q": "foobrand", "mode": "text", "threshold": 0.4, "gazette_id": str(_GZ), "limit": 50},
    )
    assert r.status_code == 200
    appnos = [it["mark"]["application_number"] for it in r.json()["items"]]
    assert "MO-2099-2" in appnos
