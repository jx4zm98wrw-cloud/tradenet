"""Mark-detail enrichment payload + Madrid search filters."""

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
from api.db.models import DomesticRecord, MadridRecord
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000a3")
_MADRID_ID = uuid.UUID("e0000000-0000-4000-8000-0000000000a4")
_DOMESTIC_ID = uuid.UUID("e0000000-0000-4000-8000-0000000000a5")
_DOMESTIC_ENRICH_ID = uuid.UUID("e0000000-0000-4000-8000-0000000000a6")
_IRN = "9000001"
_DOMESTIC_APP_NO = "4-2099-99999"


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(MadridRecord).where(MadridRecord.irn == _IRN))
        await s.execute(delete(DomesticRecord).where(DomesticRecord.application_number == _DOMESTIC_APP_NO))
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="B_TEST_enrich.pdf",
                sha256="enrich_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # Madrid row: only madrid_number is set, so the generated lineage_key
        # (COALESCE of 210/111/116) resolves to the IRN and soft-joins to the
        # madrid_records row below.
        s.add(
            Trademark(
                id=_MADRID_ID,
                gazette_id=_GZ,
                is_representative=True,  # distinct single marks — each its own dedup representative
                record_type=RecordType.B_madrid,
                madrid_number=_IRN,
                # Future pub date so this row sorts to the top of the
                # publication-date-desc list and lands inside the first
                # page (limit=50) of the filtered search results.
                publication_date_441=date(2099, 1, 1),
            )
        )
        # Domestic row: lineage_key resolves to the application_number, which
        # has no madrid_records match — enrichment must be None.
        s.add(
            Trademark(
                id=_DOMESTIC_ID,
                gazette_id=_GZ,
                is_representative=True,  # distinct single marks — each its own dedup representative
                record_type=RecordType.B_domestic,
                certificate_number="VN12345",
                application_number="4-2099-00001",
            )
        )
        # Domestic row WITH a matching DomesticRecord — enrichment must be present.
        s.add(
            Trademark(
                id=_DOMESTIC_ENRICH_ID,
                gazette_id=_GZ,
                is_representative=True,  # distinct single marks — each its own dedup representative
                record_type=RecordType.A,
                application_number=_DOMESTIC_APP_NO,
                publication_date_441=date(2099, 2, 1),
            )
        )
        s.add(
            DomesticRecord(
                application_number=_DOMESTIC_APP_NO,
                mark_text="VTRAVEL",
                nice_classes=["39"],
                goods_services={"39": "Travel"},
                status_code="1904",
            )
        )
        s.add(
            MadridRecord(
                irn=_IRN,
                holder_name="ACME GLOBAL LLC",
                mark_text="ACMEX",
                registration_date=date(2015, 6, 26),
                expiration_date=date(2035, 6, 26),
                nice_classes=["9", "42"],
                designated_countries=["VN", "SG", "JP"],
                vn_designated=True,
                vn_status="granted",
                vn_grant_date=date(2016, 8, 1),
                designation_status={"VN": {"date": "2016-08-01", "status": "granted"}},
                transaction_history=[
                    {"type": "Grant of protection, VN", "date": "2016-08-01", "parties": ["VN"]}
                ],
                source_url="https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.9000001",
            )
        )
        await s.commit()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_madrid_detail_includes_enrichment(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/marks/{_MADRID_ID}")
    assert r.status_code == 200
    enr = r.json()["enrichment"]
    assert enr is not None
    assert enr["irn"] == _IRN
    assert enr["vn_status"] == "granted"
    assert enr["vn_grant_date"] == "2016-08-01"
    assert "VN" in enr["designated_countries"]
    assert enr["holder_name"] == "ACME GLOBAL LLC"


@pytest.mark.asyncio
async def test_domestic_detail_has_null_enrichment(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/marks/{_DOMESTIC_ID}")
    assert r.status_code == 200
    assert r.json()["enrichment"] is None


@pytest.mark.asyncio
async def test_search_filter_designated_country(client: AsyncClient) -> None:
    r_sg = await client.get("/api/v1/trademarks", params={"designated_country": "SG", "limit": 50})
    ids = {row["id"] for row in r_sg.json()["items"]}
    assert str(_MADRID_ID) in ids
    r_us = await client.get("/api/v1/trademarks", params={"designated_country": "US", "limit": 50})
    assert str(_MADRID_ID) not in {row["id"] for row in r_us.json()["items"]}


@pytest.mark.asyncio
async def test_search_filter_vn_status(client: AsyncClient) -> None:
    r = await client.get("/api/v1/trademarks", params={"vn_status": "granted", "limit": 50})
    assert str(_MADRID_ID) in {row["id"] for row in r.json()["items"]}
    r2 = await client.get("/api/v1/trademarks", params={"vn_status": "refused", "limit": 50})
    assert str(_MADRID_ID) not in {row["id"] for row in r2.json()["items"]}


@pytest.mark.asyncio
async def test_facet_vn_status(client: AsyncClient) -> None:
    r = await client.get("/api/v1/facets/vn-status")
    assert r.status_code == 200
    buckets = {b["key"]: b["count"] for b in r.json()}
    assert buckets.get("granted", 0) >= 1


@pytest.mark.asyncio
async def test_domestic_detail_includes_enrichment(client: AsyncClient) -> None:
    r = await client.get(f"/api/v1/marks/{_DOMESTIC_ENRICH_ID}")
    assert r.status_code == 200
    dom = r.json()["domestic"]
    assert dom is not None
    assert dom["mark_text"] == "VTRAVEL"
    assert dom["goods_services"]["39"] == "Travel"
    assert dom["status_code"] == "1904"


@pytest.mark.asyncio
async def test_madrid_detail_has_null_domestic(client: AsyncClient) -> None:
    # Madrid marks have no application_number → domestic must be None.
    r = await client.get(f"/api/v1/marks/{_MADRID_ID}")
    assert r.status_code == 200
    assert r.json()["domestic"] is None
