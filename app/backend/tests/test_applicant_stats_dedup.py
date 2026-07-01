"""Query-time dedup for the applicant-portfolio stats + co-marks endpoints.

`GET /api/v1/marks/{id}/applicant-stats` read RAW `trademarks` rows: it counted
`record_type == A` as `pending` and `record_type != A` as `activeMarks`. But a
single domestic mark appears as BOTH an application (A) row AND a registration
(B_domestic) row sharing an `application_number`, so every granted mark was
counted TWICE — once as `activeMarks` (its registration row) and once as
`pending` (its application row) — and `totalMarks` summed raw gazette
appearances rather than unique marks.

These tests mirror the live "TÂY ĐÔ LONG AN" repro (41 raw rows / 25 unique = 16
registered + 9 application-only) at a small, gazette-scoped scale: an applicant
with 3 unique marks, 2 of which are present as an application+registration pair.

  raw rows      = 5  (2 app + 2 reg + 1 solo app)
  unique marks  = 3
  activeMarks   = 2  (the two registered marks, counted ONCE — not also pending)
  pending       = 1  (the solo application-only mark)

The old endpoint returned totalMarks=5, activeMarks=2, pending=3 (the two
granted marks leaked into pending via their application rows). The deduped
endpoint returns totalMarks=3, activeMarks=2, pending=1.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000e1")
_APPLICANT = "DEDUPSTATS TAY DO LONG AN CO"

# Pair 1 (granted): application + registration share appno A1.
_P1_APP = uuid.UUID("e0000000-0000-4000-8000-0000000000e2")
_P1_REG = uuid.UUID("e0000000-0000-4000-8000-0000000000e3")
# Pair 2 (granted): application + registration share appno A2.
_P2_APP = uuid.UUID("e0000000-0000-4000-8000-0000000000e4")
_P2_REG = uuid.UUID("e0000000-0000-4000-8000-0000000000e5")
# Solo: application-only mark (no registration counterpart), not granted.
_SOLO = uuid.UUID("e0000000-0000-4000-8000-0000000000e6")

_A1 = "DEDUPS-4-2098-001"
_A2 = "DEDUPS-4-2098-002"
_A3 = "DEDUPS-4-2098-003"

_UNIQUE_MARKS = 3
_RAW_ROWS = 5
_ACTIVE = 2  # the two registered marks, counted once each
_PENDING = 1  # the solo application-only mark


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
                filename="B_TEST_dedup_stats.pdf",
                sha256="dedups_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2098,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )

        # lineage_key is a STORED GENERATED column: domestic rows derive it from
        # application_number, so an application row and a registration row
        # sharing an appno collapse to one dedup group.
        def app_row(rid: uuid.UUID, appno: str, granted: bool) -> Trademark:
            return Trademark(
                id=rid,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number=appno,
                applicant_name=_APPLICANT,
                # NULL mark_sample + a backfilled resolved mark_name: the real
                # shape of a domestic/figurative mark. Co-marks must resolve the
                # display name from mark_name, NOT fall through to the appno.
                mark_sample=None,
                mark_name="DEDUPSNAME",
                certificate_number=None,
                publication_date_441=date(2098, 1, 1),
                vn_grant_date=date(2098, 5, 1) if granted else None,
            )

        def reg_row(rid: uuid.UUID, appno: str, cert: str) -> Trademark:
            return Trademark(
                id=rid,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number=appno,
                applicant_name=_APPLICANT,
                # NULL mark_sample + a backfilled resolved mark_name: the real
                # shape of a domestic/figurative mark. Co-marks must resolve the
                # display name from mark_name, NOT fall through to the appno.
                mark_sample=None,
                mark_name="DEDUPSNAME",
                certificate_number=cert,
                publication_date_441=None,
                vn_grant_date=date(2098, 5, 1),
            )

        s.add(app_row(_P1_APP, _A1, granted=True))
        s.add(reg_row(_P1_REG, _A1, "CERT-2098-E1"))
        s.add(app_row(_P2_APP, _A2, granted=True))
        s.add(reg_row(_P2_REG, _A2, "CERT-2098-E2"))
        s.add(app_row(_SOLO, _A3, granted=False))
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_applicant_stats_counts_unique_marks(client: AsyncClient) -> None:
    """totalMarks is the unique-mark count and the two granted app+reg marks are
    counted ONCE as active, never also as pending."""
    # Resolve stats from the solo application row's id (any row of the applicant works).
    r = await client.get(f"/api/v1/marks/{_SOLO}/applicant-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == _APPLICANT
    assert body["totalMarks"] == _UNIQUE_MARKS, (
        f"totalMarks should be {_UNIQUE_MARKS} unique marks (raw rows={_RAW_ROWS}), got {body['totalMarks']}"
    )
    assert body["activeMarks"] == _ACTIVE, (
        f"the two registered marks count once as active, got {body['activeMarks']}"
    )
    assert body["pending"] == _PENDING, (
        f"only the solo application-only mark is pending (granted marks must NOT "
        f"leak into pending via their application row), got {body['pending']}"
    )
    # Invariant: active + pending reconciles to the unique-mark total.
    assert body["activeMarks"] + body["pending"] == body["totalMarks"]


@pytest.mark.asyncio
async def test_applicant_stats_resolved_from_registration_row(client: AsyncClient) -> None:
    """Stats are identical regardless of which of the applicant's rows the mark
    id points at (application vs registration)."""
    r = await client.get(f"/api/v1/marks/{_P1_REG}/applicant-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["totalMarks"] == _UNIQUE_MARKS
    assert body["activeMarks"] == _ACTIVE
    assert body["pending"] == _PENDING


@pytest.mark.asyncio
async def test_co_marks_returns_one_card_per_unique_mark(client: AsyncClient) -> None:
    """`/marks/{id}/co-marks` for one mark of the applicant returns the OTHER
    unique marks once each — not both the application and registration row of a
    mark that appears as an app+reg pair."""
    # Anchor on the solo mark; its co-marks are the two granted marks (A1, A2).
    r = await client.get(f"/api/v1/marks/{_SOLO}/co-marks", params={"limit": 10})
    assert r.status_code == 200
    cards = r.json()
    ids = [c["id"] for c in cards]
    assert len(ids) == len(set(ids)), "no duplicate co-mark cards"
    assert len(cards) == 2, f"two OTHER unique marks (A1, A2), got {len(cards)} cards"
    # Regression: the card must show the resolved MARK NAME, never the appno.
    # These rows have NULL mark_sample, so the old chain (mark_sample -> appno)
    # rendered the application number for every co-mark.
    appnos = {_A1, _A2, _A3}
    for c in cards:
        assert c["name"] == "DEDUPSNAME", f"co-mark name must be the resolved mark, got {c['name']!r}"
        assert c["name"] not in appnos, "co-mark name must never be the application number"
