from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import MadridRecord
from madrid_enrich.enrich import enrich_one

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1266721.html"


@pytest.mark.asyncio
async def test_enrich_one_fetches_parses_stores(db_session, tmp_path):
    # Pre-seed the cache so enrich_one hits no network.
    (tmp_path / "1266721.html").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )

    wrote = await enrich_one(db_session, "1266721", cache_dir=tmp_path)
    assert wrote is True

    row = (
        await db_session.execute(select(MadridRecord).where(MadridRecord.irn == "1266721"))
    ).scalar_one()
    assert row.mark_text == "Clalen"
    assert row.vn_status == "granted"
    assert row.expiration_date.year == 2035
