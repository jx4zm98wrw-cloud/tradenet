import hashlib
from pathlib import Path

import pytest
from sqlalchemy import select

from api.db.models import MadridRecord
from madrid_enrich.derive import derive_vn
from madrid_enrich.parser import parse
from madrid_enrich.store import upsert

FIXTURE = Path(__file__).parent.parent / "fixtures" / "madrid" / "1266721.html"


@pytest.mark.asyncio
async def test_upsert_inserts_then_skips_unchanged(db_session):
    html = FIXTURE.read_text(encoding="utf-8")
    rec = parse(html)
    rec.irn = "1266721"
    vn = derive_vn(rec)
    url = "https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.1266721"

    wrote = await upsert(db_session, rec, vn, html, url)
    assert wrote is True

    row = (
        await db_session.execute(select(MadridRecord).where(MadridRecord.irn == "1266721"))
    ).scalar_one()
    assert row.holder_name == "Interojo Inc."
    assert row.vn_status == "granted"
    assert "VN" in row.designated_countries
    assert row.content_hash == hashlib.sha256(html.encode()).hexdigest()

    wrote_again = await upsert(db_session, rec, vn, html, url)
    assert wrote_again is False
