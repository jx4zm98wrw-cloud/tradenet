"""backfill_logo_phash sets hex for marks with a readable logo; idempotent."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from PIL import Image
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from scripts.backfill_logo_phash import backfill_logo_phash

_GZ = uuid.UUID("e3000000-0000-4000-8000-0000000000d1")
_WITH = uuid.UUID("e3000000-0000-4000-8000-0000000000d2")
_WITHOUT = uuid.UUID("e3000000-0000-4000-8000-0000000000d3")
_REL = "2099/test_phash/logo.png"


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    p = get_settings().data_dir / "image" / _REL
    p.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("L", (32, 32), 0)
    img.putpixel((6, 6), 255)
    img.save(p)
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="A_TEST_phash.pdf",
                sha256="phash_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        s.add(
            Trademark(
                id=_WITH,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="PH-1",
                logo_path=_REL,
                publication_date_441=date(2099, 1, 1),
            )
        )
        s.add(
            Trademark(
                id=_WITHOUT,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="PH-2",
                logo_path=None,
                publication_date_441=date(2099, 1, 1),
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()
    p.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_backfill_sets_and_is_idempotent():
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill_logo_phash(s, ids=[_WITH, _WITHOUT])
        assert stats["updated"] == 1
        with_row = (await s.execute(select(Trademark).where(Trademark.id == _WITH))).scalar_one()
        without_row = (await s.execute(select(Trademark).where(Trademark.id == _WITHOUT))).scalar_one()
        assert with_row.logo_phash and len(with_row.logo_phash) == 16
        assert without_row.logo_phash is None
    async with Session() as s:
        stats2 = await backfill_logo_phash(s, ids=[_WITH, _WITHOUT])
        assert stats2["updated"] == 0  # idempotent
    await engine.dispose()
