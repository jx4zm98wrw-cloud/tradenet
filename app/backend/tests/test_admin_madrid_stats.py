"""Admin Madrid-enrichment progress endpoint.

Runs against the shared dev DB while the enrichment sweep may be writing
rows, so we assert the response's internal consistency (relationships that
hold at any instant) plus that our seeded registration IRN is counted —
never absolute counts, which move under the sweep.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.db.models import MadridRecord
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000b1")
_REG_ID = uuid.UUID("e0000000-0000-4000-8000-0000000000b2")
_IRN = "9100001"  # synthetic, above the live WIPO IRN range; no collision


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(delete(MadridRecord).where(MadridRecord.irn == _IRN))
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))

    async with Session() as s:
        await _cleanup(s)
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="B_TEST_admin_madrid.pdf",
                sha256="adminmadrid_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # certificate_number only → generated mark_category='madrid_registration',
        # lineage_key=_IRN, which soft-joins to the madrid_records row below.
        s.add(
            Trademark(
                id=_REG_ID,
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                certificate_number=_IRN,
            )
        )
        s.add(
            MadridRecord(
                irn=_IRN,
                mark_text="ADMINX",
                vn_status="granted",
                vn_designated=True,
                designated_countries=["VN"],
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_madrid_enrichment_invariants(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/admin/madrid-enrichment")
    assert r.status_code == 200
    d = r.json()
    # Relationships that hold at any snapshot, even while the sweep writes.
    assert d["remaining"] == max(d["unique_irns"] - d["validated"], 0)
    assert d["unique_irns"] >= d["validated"] >= 0
    assert d["vn_granted"] <= d["validated"]
    if d["unique_irns"]:
        assert abs(d["pct_complete"] - d["validated"] / d["unique_irns"]) < 1e-9
    # by_category covers exactly the two Madrid categories. A few lineage_keys
    # carry both a registration and a renewal row, so the per-bucket distinct
    # counts sum to >= unique_irns (which dedupes that cross-category overlap),
    # while no single bucket can exceed unique_irns.
    assert set(d["by_category"]) == {"madrid_registration", "madrid_renewal"}
    assert sum(d["by_category"].values()) >= d["unique_irns"]
    assert max(d["by_category"].values()) <= d["unique_irns"]
    # Our seeded registration IRN + its madrid_record are reflected.
    assert d["unique_irns"] >= 1
    assert d["by_category"]["madrid_registration"] >= 1
    assert d["validated"] >= 1
    assert d["vn_granted"] >= 1


@pytest.mark.asyncio
async def test_madrid_enrichment_requires_admin(viewer_client: AsyncClient) -> None:
    r = await viewer_client.get("/api/v1/admin/madrid-enrichment")
    assert r.status_code == 403
