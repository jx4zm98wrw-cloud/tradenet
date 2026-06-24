"""Task 1 search-grant-status: migration presence + idempotent vn_grant_date backfill.

Deterministic and sweep-safe: all DB writes use synthetic ids the live
domestic/madrid sweeps never touch, and the backfill is invoked scoped to
those ids.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.db.models import DomesticRecord, MadridRecord
from api.settings import get_settings


@pytest.mark.asyncio
async def test_vn_grant_column_and_index_exist() -> None:
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
                    {"cols": ["vn_grant_date"]},
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
                    {"idx": ["ix_trademarks_vn_grant_date"]},
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()
    assert cols == {"vn_grant_date"}
    assert idx == {"ix_trademarks_vn_grant_date"}


# Synthetic ids the live sweeps never touch (distinct from test_entity_clean_backfill).
_GZ = uuid.UUID("e4000000-0000-4000-8000-0000000000c1")
_IRN = "9400001"
_IRN_PENDING = "9400002"  # Madrid mark with a vn_grant_date but vn_status != "granted".
_APPNOS = ["GRANTAPP0", "GRANTAPP2"]  # A: granted, B: ungranted (no DomesticRecord)
_TM_IDS = [uuid.UUID(f"e4000000-0000-4000-8000-00000000{i:04d}") for i in range(10, 14)]


@pytest_asyncio.fixture
async def bf_seed() -> AsyncIterator[list[uuid.UUID]]:
    """Seed: domestic mark A (granted via DomesticRecord.grant_date), a Madrid
    mark (granted via MadridRecord.vn_grant_date), domestic mark B (no record →
    ungranted)."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(delete(Trademark).where(Trademark.id.in_(_TM_IDS)))
        await s.execute(delete(DomesticRecord).where(DomesticRecord.application_number.in_(_APPNOS)))
        await s.execute(delete(MadridRecord).where(MadridRecord.irn.in_([_IRN, _IRN_PENDING])))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))

    async with Session() as s:
        await _cleanup(s)
        s.add(
            Gazette(
                id=_GZ,
                filename="B_T1_2096.pdf",
                sha256="grant_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2096,
                issue_number=1,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # Domestic mark A: appno + cert → mark_category=domestic_registration.
        s.add(
            Trademark(
                id=_TM_IDS[0],
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="GRANTAPP0",
                certificate_number="GRANTCERT0",
            )
        )
        # Madrid mark: madrid_number only → mark_category=madrid_renewal,
        # lineage_key = madrid_number = IRN.
        s.add(
            Trademark(
                id=_TM_IDS[1],
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                madrid_number=_IRN,
            )
        )
        # Domestic mark B: appno + cert, but NO DomesticRecord → ungranted.
        s.add(
            Trademark(
                id=_TM_IDS[2],
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="GRANTAPP2",
                certificate_number="GRANTCERT2",
            )
        )
        # Madrid mark with a vn_grant_date but vn_status != "granted" → resolver
        # gate must suppress it to NULL (the `else None` branch).
        s.add(
            Trademark(
                id=_TM_IDS[3],
                gazette_id=_GZ,
                record_type=RecordType.B_madrid,
                madrid_number=_IRN_PENDING,
            )
        )
        s.add(DomesticRecord(application_number="GRANTAPP0", grant_date=date(2024, 12, 9)))
        s.add(MadridRecord(irn=_IRN, vn_status="granted", vn_grant_date=date(2023, 1, 2)))
        s.add(MadridRecord(irn=_IRN_PENDING, vn_status="pending", vn_grant_date=date(2022, 5, 5)))
        await s.commit()
    await engine.dispose()
    yield list(_TM_IDS)
    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_resolves_grant_dates(bf_seed) -> None:
    from scripts.backfill_vn_grant import backfill_vn_grant

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill_vn_grant(s, ids=bf_seed)
        assert stats["scanned"] == 4
        # A + madrid granted resolve to a date; B (no record) and the
        # non-granted madrid mark both stay NULL (no-op).
        assert stats["updated"] == 2

        rows = (
            await s.execute(select(Trademark.id, Trademark.vn_grant_date).where(Trademark.id.in_(bf_seed)))
        ).all()
    await engine.dispose()

    by_id = {r.id: r.vn_grant_date for r in rows}
    assert by_id[_TM_IDS[0]] == date(2024, 12, 9)  # domestic granted
    assert by_id[_TM_IDS[1]] == date(2023, 1, 2)  # madrid granted
    assert by_id[_TM_IDS[2]] is None  # ungranted domestic (no DomesticRecord)
    # vn_status != "granted" gate suppresses the date even though one exists.
    assert by_id[_TM_IDS[3]] is None


@pytest.mark.asyncio
async def test_backfill_is_idempotent(bf_seed) -> None:
    from scripts.backfill_vn_grant import backfill_vn_grant

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        first = await backfill_vn_grant(s, ids=bf_seed)
        assert first["updated"] == 2
        second = await backfill_vn_grant(s, ids=bf_seed)
        assert second["scanned"] == 4
        assert second["updated"] == 0
        assert second["unchanged"] == 4
    await engine.dispose()
