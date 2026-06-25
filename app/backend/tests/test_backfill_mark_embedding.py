"""backfill_mark_embedding sets bytea for marks with a mark_name; idempotent."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import date

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings
from scripts.backfill_mark_embedding import backfill_mark_embedding

_GZ = uuid.UUID("e3000000-0000-4000-8000-0000000000e1")
_WITH = uuid.UUID("e3000000-0000-4000-8000-0000000000e2")
_WITHOUT = uuid.UUID("e3000000-0000-4000-8000-0000000000e3")
_DIM = 768


def _fake_encoder(texts: list[str]) -> np.ndarray:
    out = np.zeros((len(texts), _DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        out[i, 0] = float(
            int(hashlib.md5(t.encode()).hexdigest(), 16) % 97 + 1
        )  # deterministic across processes, non-zero
    return out


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
                filename="A_TEST_embed.pdf",
                sha256="embed_" + uuid.uuid4().hex,
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
                application_number="EM-1",
                mark_name="APPLE",
                publication_date_441=date(2099, 1, 1),
            )
        )
        s.add(
            Trademark(
                id=_WITHOUT,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number="EM-2",
                mark_name=None,  # not yet name-backfilled -> no embedding
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


@pytest.mark.asyncio
async def test_backfill_sets_idempotent_and_skips_null_name():
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        stats = await backfill_mark_embedding(s, ids=[_WITH, _WITHOUT], encoder=_fake_encoder)
        assert stats["updated"] == 1  # only the mark_name row
        with_row = (await s.execute(select(Trademark).where(Trademark.id == _WITH))).scalar_one()
        without_row = (await s.execute(select(Trademark).where(Trademark.id == _WITHOUT))).scalar_one()
        assert with_row.mark_embedding is not None and len(with_row.mark_embedding) == _DIM * 4
        assert without_row.mark_embedding is None  # NULL mark_name -> not scanned
    async with Session() as s:
        stats2 = await backfill_mark_embedding(s, ids=[_WITH, _WITHOUT], encoder=_fake_encoder)
        assert stats2["updated"] == 0  # idempotent
        assert stats2["unchanged"] == 1
    await engine.dispose()
