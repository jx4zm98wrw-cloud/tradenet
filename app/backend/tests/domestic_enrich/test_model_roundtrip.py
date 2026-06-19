import pytest
from sqlalchemy import select

from api.db.models import DomesticRecord


@pytest.mark.asyncio
async def test_domestic_record_roundtrip(db_session):
    db_session.add(
        DomesticRecord(
            application_number="4-2026-18514",
            mark_text="VTRAVEL",
            nice_classes=["39", "43"],
            goods_services={"39": "Transport", "43": "Lodging"},
            status_code="1904",
        )
    )
    await db_session.flush()
    row = (
        await db_session.execute(
            select(DomesticRecord).where(DomesticRecord.application_number == "4-2026-18514")
        )
    ).scalar_one()
    assert row.mark_text == "VTRAVEL"
    assert row.nice_classes == ["39", "43"]
    assert row.goods_services["43"] == "Lodging"
