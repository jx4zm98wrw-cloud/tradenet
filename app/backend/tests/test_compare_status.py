"""Compare response carries real status_label/status_tone via derive_status."""

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
from api.db.models import DomesticRecord
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000c1")
_MARK1 = uuid.UUID("e0000000-0000-4000-8000-0000000000c2")
_MARK2 = uuid.UUID("e0000000-0000-4000-8000-0000000000c3")
_APPNOS = ("CMP-STATUS-1", "CMP-STATUS-2")


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(DomesticRecord).where(DomesticRecord.application_number.in_(_APPNOS)))
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="B_TEST_compare_status.pdf",
                sha256="cmpstatus_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # mark1: granted — has VN grant date + an IP VIETNAM domestic status_code.
        s.add(
            Trademark(
                id=_MARK1,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="CMP-STATUS-1",
                vn_grant_date=date(2024, 12, 9),
            )
        )
        s.add(
            DomesticRecord(
                application_number="CMP-STATUS-1",
                status_code="Cấp bằng",
            )
        )
        # mark2: pending — no grant date, no domestic record.
        s.add(
            Trademark(
                id=_MARK2,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="CMP-STATUS-2",
                vn_grant_date=None,
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(DomesticRecord).where(DomesticRecord.application_number.in_(_APPNOS)))
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_compare_includes_real_status(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/compare",
        json={"markIds": [str(_MARK1), str(_MARK2)]},
    )
    assert r.status_code == 200, r.text
    marks = {m["id"]: m for m in r.json()["marks"]}
    granted = marks[str(_MARK1)]
    assert granted["status_label"] == "Cấp bằng"
    assert granted["status_tone"] == "ok"
    pending = marks[str(_MARK2)]
    assert pending["status_label"] == "Pending"
    assert pending["status_tone"] == "warn"
