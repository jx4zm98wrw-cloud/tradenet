import pytest
from sqlalchemy import select

from api.db.models import DomesticRecord
from domestic_enrich.parser import DomesticRecord as ParsedRecord
from domestic_enrich.store import upsert


@pytest.mark.asyncio
async def test_upsert_inserts_then_skips_unchanged(db_session):
    rec = ParsedRecord(
        application_number="4-2026-18514", mark_text="VTRAVEL", nice_classes=["39"], status_code="1904"
    )
    html = "<html>raw</html>"

    assert await upsert(db_session, rec, html, "http://x") is True
    assert await upsert(db_session, rec, html, "http://x") is False  # unchanged
    assert await upsert(db_session, rec, "<html>different</html>", "http://x") is True  # changed

    row = (
        await db_session.execute(
            select(DomesticRecord).where(DomesticRecord.application_number == "4-2026-18514")
        )
    ).scalar_one()
    assert row.mark_text == "VTRAVEL"
