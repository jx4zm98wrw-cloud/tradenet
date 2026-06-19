from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import DomesticRecord
from domestic_enrich.enrich import enrich_one

FIXTURE = Path(__file__).parent.parent / "fixtures" / "domestic" / "VN4202600774.html"


@pytest.mark.asyncio
async def test_enrich_one_fetches_parses_stores(db_session, tmp_path):
    # Pre-seed cache by VNID filename so enrich_one hits no network.
    (tmp_path / "VN4202600774.html").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    wrote = await enrich_one(db_session, "4-2026-00774", cache_dir=tmp_path)
    assert wrote is True

    row = (await db_session.execute(
        select(DomesticRecord).where(DomesticRecord.application_number == "4-2026-00774")
    )).scalar_one()
    assert row.mark_text == "VTRAVEL"
    assert row.status_code


@pytest.mark.asyncio
async def test_enrich_one_skips_unmappable_appno(db_session, tmp_path):
    wrote = await enrich_one(db_session, "garbage", cache_dir=tmp_path)
    assert wrote is False
