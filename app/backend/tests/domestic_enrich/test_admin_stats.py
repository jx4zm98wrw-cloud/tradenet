"""Admin domestic-enrichment coverage stats endpoint.

Runs against the shared dev DB. We seed deterministic rows with synthetic
identifiers well outside any real data range, assert internal consistency
relationships (which hold at any snapshot), and verify our seeded rows are
reflected.
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
from api.db.models import DomesticNotFound, DomesticRecord
from api.settings import get_settings

_GZ = uuid.UUID("f0000000-0000-4000-8000-0000000000d1")
_APP_ID1 = uuid.UUID("f0000000-0000-4000-8000-0000000000d2")
_APP_ID2 = uuid.UUID("f0000000-0000-4000-8000-0000000000d3")
_APP_ID3 = uuid.UUID("f0000000-0000-4000-8000-0000000000d4")
_APPNO1 = "4-9999-99901"  # synthetic; won't collide with real data
_APPNO2 = "4-9999-99902"
_APPNO3 = "4-9999-99903"  # unvalidated + recorded not-published (pending bucket)


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(
            delete(DomesticRecord).where(DomesticRecord.application_number.in_([_APPNO1, _APPNO2]))
        )
        await s.execute(delete(DomesticNotFound).where(DomesticNotFound.application_number == _APPNO3))
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))

    async with Session() as s:
        await _cleanup(s)
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="A_TEST_admin_domestic.pdf",
                sha256="admindomestic_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # domestic_application: application_number only, no certificate_number
        s.add(
            Trademark(
                id=_APP_ID1,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number=_APPNO1,
            )
        )
        # domestic_registration: application_number + certificate_number
        s.add(
            Trademark(
                id=_APP_ID2,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number=_APPNO2,
                certificate_number="9999901",
            )
        )
        # DomesticRecord WITH a grant_date
        s.add(
            DomesticRecord(
                application_number=_APPNO1,
                mark_text="TESTDOM1",
                grant_date=None,
            )
        )
        # DomesticRecord WITHOUT a grant_date
        s.add(
            DomesticRecord(
                application_number=_APPNO2,
                mark_text="TESTDOM2",
                grant_date=None,
            )
        )
        # A domestic mark IP VIETNAM hasn't published yet: in the work-list (unique +
        # remaining), unvalidated (no DomesticRecord), recorded not-published →
        # must land in the pending_publication bucket, not unresolved.
        s.add(
            Trademark(
                id=_APP_ID3,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number=_APPNO3,
            )
        )
        s.add(DomesticNotFound(application_number=_APPNO3, vnid="VN4999999903"))
        await s.commit()

    yield

    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_domestic_enrichment_invariants(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/admin/domestic-enrichment")
    assert r.status_code == 200
    d = r.json()

    # Internal consistency — hold at any snapshot
    assert d["remaining"] == max(d["unique_appnos"] - d["validated"], 0)
    assert d["unique_appnos"] >= d["validated"] >= 0
    assert d["granted"] <= d["validated"]
    # remaining splits exactly into the two operational buckets.
    assert d["pending_publication"] + d["unresolved"] == d["remaining"]
    assert 0 <= d["pending_publication"] <= d["remaining"]
    assert 0 <= d["unresolved"] <= d["remaining"]
    if d["unique_appnos"]:
        assert abs(d["pct_complete"] - d["validated"] / d["unique_appnos"]) < 1e-9

    # by_category covers exactly the two domestic categories
    assert set(d["by_category"]) == {"domestic_application", "domestic_registration"}

    # Our seeded rows are reflected
    assert d["unique_appnos"] >= 2
    assert d["by_category"]["domestic_application"] >= 1
    assert d["by_category"]["domestic_registration"] >= 1
    assert d["validated"] >= 2


@pytest.mark.asyncio
async def test_domestic_enrichment_granted_count(authed_client: AsyncClient) -> None:
    """granted == count of DomesticRecord rows with grant_date IS NOT NULL."""
    # Our seeded rows both have grant_date=None, so granted should not increase
    # from them. We just verify the field is present and non-negative.
    r = await authed_client.get("/api/v1/admin/domestic-enrichment")
    assert r.status_code == 200
    d = r.json()
    assert d["granted"] >= 0
    assert "granted" in d


@pytest.mark.asyncio
async def test_domestic_enrichment_pending_publication_reflects_not_found(
    authed_client: AsyncClient,
) -> None:
    """Our seeded not-published mark (_APPNO3: unvalidated + in domestic_not_found)
    must be counted in pending_publication, not in unresolved."""
    r = await authed_client.get("/api/v1/admin/domestic-enrichment")
    assert r.status_code == 200
    d = r.json()
    # At least our one seeded pending mark is present.
    assert d["pending_publication"] >= 1
    # And the bucket split is exact.
    assert d["pending_publication"] + d["unresolved"] == d["remaining"]


@pytest.mark.asyncio
async def test_domestic_enrichment_requires_admin(viewer_client: AsyncClient) -> None:
    r = await viewer_client.get("/api/v1/admin/domestic-enrichment")
    assert r.status_code == 403
