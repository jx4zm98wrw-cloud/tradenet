"""trademarks.is_representative maintenance + parity with the DISTINCT ON view.

`recompute_is_representative_sql` flags exactly the ONE most-advanced row of each
dedup group. This test seeds application+registration pairs (+ a solo) and asserts
the flag lands on the same rows `representative_marks` (the DISTINCT ON) keeps —
the two MUST agree, since the unfiltered fast path swaps one for the other.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api._dedup import dedup_key_expr, recompute_is_representative_sql, representative_marks
from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-000000009701")
_P1_APP = uuid.UUID("e0000000-0000-4000-8000-000000009702")
_P1_REG = uuid.UUID("e0000000-0000-4000-8000-000000009703")
_P2_APP = uuid.UUID("e0000000-0000-4000-8000-000000009704")
_P2_REG = uuid.UUID("e0000000-0000-4000-8000-000000009705")
_SOLO = uuid.UUID("e0000000-0000-4000-8000-000000009706")
_A1, _A2, _A3 = "ISREP-4-2097-001", "ISREP-4-2097-002", "ISREP-4-2097-003"


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[async_sessionmaker]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
        s.add(
            Gazette(
                id=_GZ,
                filename="B_TEST_isrep.pdf",
                sha256="isrep_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2097,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )

        def app_row(rid: uuid.UUID, appno: str, granted: bool) -> Trademark:
            return Trademark(
                id=rid,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number=appno,
                applicant_name="ISREP CO",
                mark_sample="ISREPMARK",
                vn_grant_date=date(2097, 5, 1) if granted else None,
            )

        def reg_row(rid: uuid.UUID, appno: str, cert: str) -> Trademark:
            return Trademark(
                id=rid,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number=appno,
                applicant_name="ISREP CO",
                mark_sample="ISREPMARK",
                certificate_number=cert,
                vn_grant_date=date(2097, 5, 1),
            )

        s.add(app_row(_P1_APP, _A1, granted=True))
        s.add(reg_row(_P1_REG, _A1, "CERT-2097-1"))
        s.add(app_row(_P2_APP, _A2, granted=True))
        s.add(reg_row(_P2_REG, _A2, "CERT-2097-2"))
        s.add(app_row(_SOLO, _A3, granted=False))
        await s.commit()
    yield Session
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


async def _flagged(Session: async_sessionmaker) -> set[uuid.UUID]:
    async with Session() as s:
        rows = await s.execute(
            select(Trademark.id).where(Trademark.gazette_id == _GZ, Trademark.is_representative.is_(True))
        )
        return set(rows.scalars().all())


@pytest.mark.asyncio
async def test_flag_marks_most_advanced_row_per_group(seed: async_sessionmaker) -> None:
    """After recompute, the registration row of each pair (and the solo) is flagged
    — the application counterpart is not."""
    async with seed() as s:
        await s.execute(text(recompute_is_representative_sql(scoped_to_gazette=True)), {"gid": _GZ})
        await s.commit()
    assert await _flagged(seed) == {_P1_REG, _P2_REG, _SOLO}


@pytest.mark.asyncio
async def test_flag_matches_distinct_on_view(seed: async_sessionmaker) -> None:
    """The flagged rows are EXACTLY the rows the DISTINCT ON `representative_marks`
    keeps — the fast path and the slow path must agree."""
    async with seed() as s:
        await s.execute(text(recompute_is_representative_sql(scoped_to_gazette=True)), {"gid": _GZ})
        await s.commit()
        rep = representative_marks([Trademark.gazette_id == _GZ])
        distinct_ids = set((await s.execute(select(rep.id))).scalars().all())
    assert await _flagged(seed) == distinct_ids


@pytest.mark.asyncio
async def test_recompute_is_idempotent(seed: async_sessionmaker) -> None:
    """A second recompute writes zero rows (flag already correct)."""
    sql = text(recompute_is_representative_sql(scoped_to_gazette=True))
    async with seed() as s:
        await s.execute(sql, {"gid": _GZ})
        await s.commit()
        result = await s.execute(sql, {"gid": _GZ})
        await s.commit()
        assert result.rowcount == 0


@pytest.mark.asyncio
async def test_exactly_one_flag_per_dedup_group(seed: async_sessionmaker) -> None:
    """No dedup group has two representatives (would resurrect the duplicate bug)."""
    async with seed() as s:
        await s.execute(text(recompute_is_representative_sql(scoped_to_gazette=True)), {"gid": _GZ})
        await s.commit()
        rows = await s.execute(
            select(dedup_key_expr(), Trademark.is_representative).where(Trademark.gazette_id == _GZ)
        )
        per_group: dict[str, int] = {}
        for key, flag in rows:
            per_group[key] = per_group.get(key, 0) + (1 if flag else 0)
    assert set(per_group.values()) == {1}, f"each group has exactly one rep, got {per_group}"


@pytest.mark.asyncio
async def test_representative_count_equals_distinct_dedup_count(seed: async_sessionmaker) -> None:
    """The unfiltered total swap is valid: COUNT(*) WHERE is_representative equals
    COUNT(DISTINCT dedup_key) over the same rows (search.py uses the former)."""
    from sqlalchemy import func

    async with seed() as s:
        await s.execute(text(recompute_is_representative_sql(scoped_to_gazette=True)), {"gid": _GZ})
        await s.commit()
        rep_count = (
            await s.execute(
                select(func.count()).where(Trademark.gazette_id == _GZ, Trademark.is_representative.is_(True))
            )
        ).scalar_one()
        distinct_count = (
            await s.execute(
                select(func.count(func.distinct(dedup_key_expr()))).where(Trademark.gazette_id == _GZ)
            )
        ).scalar_one()
    assert rep_count == distinct_count == 3
