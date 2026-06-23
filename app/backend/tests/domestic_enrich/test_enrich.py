from pathlib import Path

import pytest
from sqlalchemy import delete, select

import domestic_enrich.enrich as enrich_mod
from api.db.models import DomesticNotFound, DomesticRecord
from domestic_enrich.client import FetchResult
from domestic_enrich.enrich import EnrichOutcome, enrich_one

FIXTURE = Path(__file__).parent.parent / "fixtures" / "domestic" / "VN4202600774.html"


@pytest.mark.asyncio
async def test_enrich_one_fetches_parses_stores(db_session, tmp_path):
    # Pre-seed cache by VNID filename so enrich_one hits no network.
    (tmp_path / "VN4202600774.html").write_text(FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")

    outcome = await enrich_one(db_session, "4-2026-00774", cache_dir=tmp_path)
    assert outcome is EnrichOutcome.WROTE

    row = (
        await db_session.execute(
            select(DomesticRecord).where(DomesticRecord.application_number == "4-2026-00774")
        )
    ).scalar_one()
    assert row.mark_text == "VTRAVEL"
    assert row.status_code


@pytest.mark.asyncio
async def test_enrich_one_skips_unmappable_appno(db_session, tmp_path):
    outcome = await enrich_one(db_session, "garbage", cache_dir=tmp_path)
    assert outcome is EnrichOutcome.UNMAPPABLE


@pytest.mark.asyncio
async def test_enrich_one_not_found_negative_caches(db_session, tmp_path, monkeypatch):
    # A NOIP not-published (200-skeleton) fetch must NOT write a domestic_records
    # row — it records the mark in domestic_not_found and returns NOT_FOUND.
    appno = "4-9999-88801"
    await db_session.execute(delete(DomesticNotFound).where(DomesticNotFound.application_number == appno))
    await db_session.commit()

    def fake_fetch(vnid, cache_dir, *, session=None, use_cache=True):
        return FetchResult(
            vnid=vnid, html="<html>skeleton</html>", source_url="u", from_cache=False, outcome="not_found"
        )

    monkeypatch.setattr(enrich_mod, "fetch_raw", fake_fetch)

    outcome = await enrich_one(db_session, appno, cache_dir=tmp_path)
    await db_session.commit()
    assert outcome is EnrichOutcome.NOT_FOUND

    # Recorded in the negative cache...
    nf = (
        await db_session.execute(select(DomesticNotFound).where(DomesticNotFound.application_number == appno))
    ).scalar_one()
    assert nf.vnid == "VN4999988801"
    assert nf.check_count == 1
    # ...and NOT written to domestic_records.
    dr = (
        await db_session.execute(select(DomesticRecord).where(DomesticRecord.application_number == appno))
    ).scalar_one_or_none()
    assert dr is None

    await db_session.execute(delete(DomesticNotFound).where(DomesticNotFound.application_number == appno))
    await db_session.commit()
