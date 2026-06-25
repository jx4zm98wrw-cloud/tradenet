"""Track 1: backfill_logo_kind is correct and idempotent."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from scripts.backfill_logo_kind import backfill_logo_kind

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000d1")
_FIG = uuid.UUID("e0000000-0000-4000-8000-0000000000d2")
_NOLOGO = uuid.UUID("e0000000-0000-4000-8000-0000000000d3")


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="B_TEST_logo_kind.pdf",
                sha256="lk_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        # Has a logo_path AND Vienna codes → classifier returns 'figurative'
        # via the Vienna branch without opening any file.
        s.add(
            Trademark(
                id=_FIG,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="LK-2099-1",
                logo_path="2099/x/fig.png",
                vienna_codes=["26.4.18"],
            )
        )
        # No logo at all → excluded from the work-list → logo_kind stays NULL.
        s.add(
            Trademark(
                id=_NOLOGO,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number="LK-2099-2",
                logo_path=None,
                vienna_codes=["26.4.18"],
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_sets_kind_and_is_idempotent() -> None:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        first = await backfill_logo_kind(s, ids=[_FIG, _NOLOGO])
        assert first["updated"] == 1  # only _FIG (has a logo_path)
        kind = (await s.execute(select(Trademark.logo_kind).where(Trademark.id == _FIG))).scalar_one()
        assert kind == "figurative"
        nolar = (await s.execute(select(Trademark.logo_kind).where(Trademark.id == _NOLOGO))).scalar_one()
        assert nolar is None
        second = await backfill_logo_kind(s, ids=[_FIG, _NOLOGO])
        assert second["updated"] == 0 and second["unchanged"] == 1
    await engine.dispose()
