"""Query-time dedup for the FILTER-ONLY search path and the FACET counts.

PR #129 (test_search_dedup.py) collapsed application+registration row pairs for
the *text* and *phonetic* search paths. But a filter-only search
(`/search?applicant=…` with no `q`) and every `/api/v1/facets/*` count still
read raw `trademarks` rows, so a mark present as BOTH an application row and a
registration row (same `application_number`) was counted twice — inflating
"Showing 1-N of N" and the sidebar facet tallies (e.g. "Granted 32" when only
16 marks are granted).

These tests pin the extension: filter-only results AND facet counts collapse
rows sharing `COALESCE(application_number, lineage_key, id)` into one mark,
counting each unique mark once under its MOST-ADVANCED representative row
(registration over application). They mirror the live "TÂY ĐÔ LONG AN" applicant
repro (41 raw rows / 25 unique = 16 registered + 9 application-only) at a small,
gazette-scoped scale.

Crucially, the granted pairs carry `vn_grant_date` on BOTH the application and
registration rows — that is how the production backfill resolves it (per mark,
written to every gazette row of that appno), and it is what made the raw
`count(*)` Granted facet report 2x the true number of granted marks.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import date

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api._dedup import recompute_is_representative_sql
from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings

_GZ = uuid.UUID("e0000000-0000-4000-8000-0000000000f1")
_APPLICANT = "DEDUPFACET TAY DO LONG AN CO"

# Pair 1 (granted): application + registration share appno A1.
_P1_APP = uuid.UUID("e0000000-0000-4000-8000-0000000000f2")
_P1_REG = uuid.UUID("e0000000-0000-4000-8000-0000000000f3")
# Pair 2 (granted): application + registration share appno A2.
_P2_APP = uuid.UUID("e0000000-0000-4000-8000-0000000000f4")
_P2_REG = uuid.UUID("e0000000-0000-4000-8000-0000000000f5")
# Solo: application-only mark (no registration counterpart), not granted.
_SOLO = uuid.UUID("e0000000-0000-4000-8000-0000000000f6")

_A1 = "DEDUPF-4-2099-001"
_A2 = "DEDUPF-4-2099-002"
_A3 = "DEDUPF-4-2099-003"

# 3 unique marks, 5 raw rows. Granted unique = 2 (both pairs); raw granted = 4.
_UNIQUE_MARKS = 3
_RAW_ROWS = 5


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
                filename="B_TEST_dedup_facets.pdf",
                sha256="dedupf_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )

        # mark_category + lineage_key are STORED GENERATED columns derived from
        # application_number / certificate_number / madrid_number — never set
        # directly; the column SHAPE picks the generated value. Domestic rows →
        # lineage_key = application_number, so an application row and a
        # registration row sharing an appno collapse together.
        def app_row(rid: uuid.UUID, appno: str, granted: bool) -> Trademark:
            return Trademark(
                id=rid,
                gazette_id=_GZ,
                record_type=RecordType.A,
                application_number=appno,
                applicant_name=_APPLICANT,
                mark_sample="DEDUPFMARK",
                certificate_number=None,
                publication_date_441=date(2099, 1, 1),
                # Production writes the resolved grant date onto EVERY gazette
                # row of the appno, including the application row.
                vn_grant_date=date(2099, 5, 1) if granted else None,
            )

        def reg_row(rid: uuid.UUID, appno: str, cert: str) -> Trademark:
            return Trademark(
                id=rid,
                gazette_id=_GZ,
                record_type=RecordType.B_domestic,
                application_number=appno,
                applicant_name=_APPLICANT,
                mark_sample="DEDUPFMARK",
                certificate_number=cert,
                publication_date_441=None,
                vn_grant_date=date(2099, 5, 1),
            )

        # Pair 1 + Pair 2: granted, present as application AND registration rows.
        s.add(app_row(_P1_APP, _A1, granted=True))
        s.add(reg_row(_P1_REG, _A1, "CERT-2099-F1"))
        s.add(app_row(_P2_APP, _A2, granted=True))
        s.add(reg_row(_P2_REG, _A2, "CERT-2099-F2"))
        # Solo application-only mark, not granted.
        s.add(app_row(_SOLO, _A3, granted=False))
        await s.commit()
        # Flag the representative row of each dedup group — representative_marks
        # (dedup-then-filter) reads is_representative, which direct-seeded rows lack.
        await s.execute(text(recompute_is_representative_sql(scoped_to_gazette=True)), {"gid": _GZ})
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _GZ))
        await s.execute(delete(Gazette).where(Gazette.id == _GZ))
        await s.commit()
    await engine.dispose()


def _bucket(buckets: list[dict], key: str) -> int:
    for b in buckets:
        if b["key"] == key:
            return int(b["count"])
    return 0


# ---- Part 1: filter-only search results + total -----------------------------


@pytest.mark.asyncio
async def test_filter_only_returns_unique_marks(client: AsyncClient) -> None:
    """`/search?applicant=…` with no q returns one card per unique mark and
    `total` is the unique-mark count, not the raw-row count."""
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"applicant": _APPLICANT, "gazette_id": str(_GZ), "mode": "text", "limit": 50},
    )
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert body["total"] == _UNIQUE_MARKS, (
        f"total should be {_UNIQUE_MARKS} unique marks, got {body['total']}"
    )
    assert len(items) == _UNIQUE_MARKS, (
        f"expected {_UNIQUE_MARKS} cards (raw rows={_RAW_ROWS}), got {len(items)}"
    )
    appnos = sorted(it["mark"]["application_number"] for it in items)
    assert appnos == [_A1, _A2, _A3], f"each appno once, got {appnos}"
    # Each appno's surviving card is the most-advanced row (registration where one exists).
    by_appno = {it["mark"]["application_number"]: it["mark"] for it in items}
    assert by_appno[_A1]["id"] == str(_P1_REG)
    assert by_appno[_A2]["id"] == str(_P2_REG)
    assert by_appno[_A3]["id"] == str(_SOLO)


# ---- Part 2: facet counts ---------------------------------------------------


@pytest.mark.asyncio
async def test_facet_mark_categories_count_unique_marks(client: AsyncClient) -> None:
    """mark-categories counts each unique mark once under its representative
    row's category: application-only marks → domestic_application; marks with a
    registration row → domestic_registration (NOT both)."""
    r = await client.get(
        "/api/v1/facets/mark-categories",
        params={"applicant": _APPLICANT, "gazette_id": str(_GZ)},
    )
    assert r.status_code == 200
    buckets = r.json()
    assert _bucket(buckets, "domestic_application") == 1, "only the solo app-only mark"
    assert _bucket(buckets, "domestic_registration") == 2, "the two registered marks, once each"
    total = sum(int(b["count"]) for b in buckets)
    assert total == _UNIQUE_MARKS, (
        f"facet buckets must reconcile to {_UNIQUE_MARKS} unique marks, got {total}"
    )


@pytest.mark.asyncio
async def test_facet_granted_counts_each_mark_once(client: AsyncClient) -> None:
    """A granted mark present as both an application and a registration row
    (grant date on both) is counted ONCE, not twice."""
    r = await client.get(
        "/api/v1/facets/granted",
        params={"applicant": _APPLICANT, "gazette_id": str(_GZ)},
    )
    assert r.status_code == 200
    buckets = r.json()
    assert _bucket(buckets, "granted") == 2, "2 granted marks (raw rows would count 4)"


@pytest.mark.asyncio
async def test_facet_applicants_count_unique_marks(client: AsyncClient) -> None:
    """The applicant facet bucket counts unique marks, not raw gazette rows."""
    r = await client.get(
        "/api/v1/facets/applicants",
        params={"gazette_id": str(_GZ)},
    )
    assert r.status_code == 200
    buckets = r.json()
    assert _bucket(buckets, _APPLICANT) == _UNIQUE_MARKS, (
        f"applicant should have {_UNIQUE_MARKS} unique marks (raw rows={_RAW_ROWS})"
    )


@pytest.mark.asyncio
async def test_facet_all_matches_individual_endpoints(client: AsyncClient) -> None:
    """`/facets/all` returns every sidebar facet in ONE payload, with the same
    deduped counts as the individual endpoints."""
    r = await client.get(
        "/api/v1/facets/all",
        params={"applicant": _APPLICANT, "gazette_id": str(_GZ)},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {
        "countries",
        "nice_classes",
        "applicants",
        "ip_agencies",
        "mark_categories",
        "granted",
    }
    assert _bucket(body["mark_categories"], "domestic_registration") == 2
    assert _bucket(body["granted"], "granted") == 2
    assert _bucket(body["applicants"], _APPLICANT) == _UNIQUE_MARKS
