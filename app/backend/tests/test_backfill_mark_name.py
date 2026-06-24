"""mark-name-resolution: migration presence + idempotent mark_name backfill.

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
async def test_mark_name_column_and_index_exist() -> None:
    """The migration added the column and btree-indexed it."""
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
                    {"cols": ["mark_name"]},
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
                    {"idx": ["ix_trademarks_mark_name"]},
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert cols == {"mark_name"}
    assert idx == {"ix_trademarks_mark_name"}


# Synthetic ids the live sweeps never touch (distinct from other backfill tests).
_GZ = uuid.UUID("e4000000-0000-4000-8000-0000000000c2")
_IRN = "9500001"
_APPNOS = ["MARKNAMEAPP0", "MARKNAMEAPP1", "MARKNAMEAPP3"]
_TM_IDS = [uuid.UUID(f"e4000000-0000-4000-8000-00000000{i:04d}") for i in range(20, 24)]


@pytest_asyncio.fixture
async def bf_seed() -> AsyncIterator[list[uuid.UUID]]:
    """Seed four marks exercising the resolution chain:
    1. domestic_registration with mark_sample → sample wins over DomesticRecord.
    2. domestic_registration, no sample → DomesticRecord.mark_text.
    3. madrid_renewal, no sample → MadridRecord.mark_text.
    4. domestic_registration, no sample, no DomesticRecord → NULL.
    """
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(delete(Trademark).where(Trademark.id.in_(_TM_IDS)))
        await s.execute(delete(DomesticRecord).where(DomesticRecord.application_number.in_(_APPNOS)))
        await s.execute(delete(MadridRecord).where(MadridRecord.irn == _IRN))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))

    async with Session() as s:
        await _cleanup(s)
        s.add(
            Gazette(
                id=_GZ,
                filename="B_T1_2097.pdf",
                sha256="markname_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2097,
                issue_number=1,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # 1. domestic_registration, mark_sample wins.
        s.add(
            Trademark(
                id=_TM_IDS[0],
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="MARKNAMEAPP0",
                certificate_number="MARKNAMECERT0",
                mark_sample="Taseko",
            )
        )
        # 2. domestic_registration, no sample → DomesticRecord.mark_text.
        s.add(
            Trademark(
                id=_TM_IDS[1],
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="MARKNAMEAPP1",
                certificate_number="MARKNAMECERT1",
            )
        )
        # 3. madrid_renewal, no sample, lineage_key = madrid_number = IRN.
        s.add(
            Trademark(
                id=_TM_IDS[2],
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                madrid_number=_IRN,
            )
        )
        # 4. domestic_registration, no sample, no DomesticRecord → NULL.
        s.add(
            Trademark(
                id=_TM_IDS[3],
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="MARKNAMEAPP3",
                certificate_number="MARKNAMECERT3",
            )
        )
        s.add(DomesticRecord(application_number="MARKNAMEAPP0", mark_text="X"))
        s.add(DomesticRecord(application_number="MARKNAMEAPP1", mark_text="TRADAGUI"))
        s.add(MadridRecord(irn=_IRN, mark_text="LANDSTORM"))
        await s.commit()
    await engine.dispose()
    yield list(_TM_IDS)
    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_resolves_mark_names(bf_seed) -> None:
    from scripts.backfill_mark_name import backfill_mark_name

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill_mark_name(s, ids=bf_seed)
        assert stats["scanned"] == 4
        # marks 1-3 get a name; mark 4 stays NULL (no-op).
        assert stats["updated"] == 3

        rows = (
            await s.execute(select(Trademark.id, Trademark.mark_name).where(Trademark.id.in_(bf_seed)))
        ).all()
    await engine.dispose()

    by_id = {r.id: r.mark_name for r in rows}
    assert by_id[_TM_IDS[0]] == "Taseko"  # mark_sample wins
    assert by_id[_TM_IDS[1]] == "TRADAGUI"  # domestic_records.mark_text
    assert by_id[_TM_IDS[2]] == "LANDSTORM"  # madrid_records.mark_text
    assert by_id[_TM_IDS[3]] is None  # no source → NULL


@pytest.mark.asyncio
async def test_backfill_is_idempotent(bf_seed) -> None:
    from scripts.backfill_mark_name import backfill_mark_name

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        first = await backfill_mark_name(s, ids=bf_seed)
        assert first["updated"] == 3
        second = await backfill_mark_name(s, ids=bf_seed)
        assert second["scanned"] == 4
        assert second["updated"] == 0
        assert second["unchanged"] == 4
    await engine.dispose()
