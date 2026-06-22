"""Phase 2 entity-canon: migration presence + idempotent backfill.

Deterministic and sweep-safe: all DB writes use synthetic ids the live
domestic/madrid sweeps never touch, and the backfill is invoked scoped to
those ids.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.db.models import DomesticRecord, MadridRecord
from api.settings import get_settings


@pytest.mark.asyncio
async def test_clean_columns_and_norm_indexes_exist() -> None:
    """The migration added the 4 columns and btree-indexed the two *_norm keys."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        cols = set(
            (
                await s.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='trademarks' AND column_name = ANY(:cols)"
                    ),
                    {
                        "cols": [
                            "applicant_clean",
                            "applicant_norm",
                            "representative_clean",
                            "representative_norm",
                        ]
                    },
                )
            )
            .scalars()
            .all()
        )
        idx = set(
            (
                await s.execute(
                    text(
                        "SELECT indexname FROM pg_indexes "
                        "WHERE tablename='trademarks' AND indexname = ANY(:idx)"
                    ),
                    {"idx": ["ix_trademarks_applicant_norm", "ix_trademarks_representative_norm"]},
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert cols == {
        "applicant_clean",
        "applicant_norm",
        "representative_clean",
        "representative_norm",
    }
    assert idx == {"ix_trademarks_applicant_norm", "ix_trademarks_representative_norm"}


# Synthetic ids the live sweeps never touch.
_GZ = uuid.UUID("e2000000-0000-4000-8000-0000000000c1")
_IRN_A = "9300001"
_IRN_B = "9300002"
_APPNOS = ["BFAPP0", "BFAPP1", "BFAPP2", "BFAPP3"]  # 3 variants of one firm + 1 distinct
_TM_IDS = [uuid.UUID(f"e2000000-0000-4000-8000-00000000{i:04d}") for i in range(10, 16)]


@pytest_asyncio.fixture
async def bf_seed() -> AsyncIterator[list[uuid.UUID]]:
    """Seed: 4 domestic marks (3 NOIP-rep variants of one firm + 1 distinct),
    1 madrid mark with a WIPO record (glued-address rep), 1 un-enriched madrid
    mark (gazette fallback only)."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(delete(Trademark).where(Trademark.id.in_(_TM_IDS)))
        await s.execute(delete(DomesticRecord).where(DomesticRecord.application_number.in_(_APPNOS)))
        await s.execute(delete(MadridRecord).where(MadridRecord.irn.in_([_IRN_A, _IRN_B])))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))

    async with Session() as s:
        await _cleanup(s)
        s.add(
            Gazette(
                id=_GZ,
                filename="B_T1_2097.pdf",
                sha256="bf_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2097,
                issue_number=1,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # 4 domestic_registration marks (appno + cert) → join domestic_records.
        for i, appno in enumerate(_APPNOS):
            s.add(
                Trademark(
                    id=_TM_IDS[i],
                    gazette_id=_GZ,
                    record_type=RecordType.B_domestic,
                    application_number=appno,
                    certificate_number=f"BFCERT{i}",
                )
            )
        # 1 madrid_registration (cert only → lineage_key = cert = IRN_A), enriched.
        s.add(
            Trademark(
                id=_TM_IDS[4],
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                certificate_number=_IRN_A,
            )
        )
        # 1 madrid_renewal (madrid_number only → lineage_key = IRN_B), UN-enriched;
        # falls back to its gazette (740) value.
        s.add(
            Trademark(
                id=_TM_IDS[5],
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                madrid_number=_IRN_B,
                ip_agency_raw_740="Gazette Fallback Agency",
                applicant_name="Gazette Fallback Holder",
            )
        )
        # NOIP records: 3 case/whitespace variants of one rep firm + 1 distinct.
        s.add(
            DomesticRecord(
                application_number="BFAPP0", applicant_name="Acme Co", representative="Công ty Luật TAGA"
            )
        )
        s.add(
            DomesticRecord(
                application_number="BFAPP1", applicant_name="Acme Co", representative="CÔNG TY LUẬT TAGA"
            )
        )
        s.add(
            DomesticRecord(
                application_number="BFAPP2", applicant_name="Acme Co", representative="Công  ty   Luật   TAGA"
            )
        )
        s.add(
            DomesticRecord(
                application_number="BFAPP3", applicant_name="Beta Co", representative="Distinct Firm XYZ"
            )
        )
        # WIPO record for the enriched madrid mark (rep carries a glued address).
        s.add(
            MadridRecord(
                irn=_IRN_A,
                holder_name="WIPO Holder One",
                representative="WIPO Rep Alpha 12 Bahnhofstrasse, Zürich",
            )
        )
        await s.commit()
    await engine.dispose()
    yield list(_TM_IDS)
    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_resolves_precedence_and_collapses_variants(bf_seed) -> None:
    from api._entity_norm import norm
    from scripts.backfill_entity_clean import backfill

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill(s, ids=bf_seed)
        assert stats["scanned"] == 6
        assert stats["updated"] == 6

        rows = (
            await s.execute(
                select(
                    Trademark.id,
                    Trademark.application_number,
                    Trademark.applicant_clean,
                    Trademark.applicant_norm,
                    Trademark.representative_clean,
                    Trademark.representative_norm,
                ).where(Trademark.id.in_(bf_seed))
            )
        ).all()
    await engine.dispose()

    by_appno = {r.application_number: r for r in rows if r.application_number}
    # NOIP applicant + rep used for domestic marks.
    assert by_appno["BFAPP0"].applicant_clean == "Acme Co"
    # The 3 rep variants collapse to ONE norm key; the 4th stays distinct.
    rep_norms = {by_appno[a].representative_norm for a in ("BFAPP0", "BFAPP1", "BFAPP2")}
    assert rep_norms == {norm("Công ty Luật TAGA")}
    assert by_appno["BFAPP3"].representative_norm == norm("Distinct Firm XYZ")
    assert by_appno["BFAPP3"].representative_norm != norm("Công ty Luật TAGA")

    # Enriched madrid mark → WIPO holder + address-stripped WIPO rep.
    madrid_enriched = next(r for r in rows if r.id == _TM_IDS[4])
    assert madrid_enriched.applicant_clean == "WIPO Holder One"
    assert madrid_enriched.representative_clean == "WIPO Rep Alpha"

    # Un-enriched madrid mark → gazette fallback.
    madrid_fallback = next(r for r in rows if r.id == _TM_IDS[5])
    assert madrid_fallback.applicant_clean == "Gazette Fallback Holder"
    assert madrid_fallback.representative_clean == "Gazette Fallback Agency"


@pytest.mark.asyncio
async def test_backfill_is_idempotent(bf_seed) -> None:
    from scripts.backfill_entity_clean import backfill

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        first = await backfill(s, ids=bf_seed)
        assert first["updated"] == 6
        # Second run over the same rows changes nothing.
        second = await backfill(s, ids=bf_seed)
        assert second["scanned"] == 6
        assert second["updated"] == 0
        assert second["unchanged"] == 6
    await engine.dispose()
