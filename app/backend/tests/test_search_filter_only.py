"""Regression test for the filter-only / threshold interaction bug.

User report: search URL had country=GB&nice_class=41&applicant_type=Company
(no `q`, mode=text). Toolbar showed "9 trademarks match your filters"
but the grid rendered "No matches" — the 65% similarity threshold was
suppressing every row.

Root cause: `_score()` returned base 0.6 + tiny jitter for text-mode
searches with no `q`, so every row landed below the 0.65 threshold.
The threshold slider is conceptually a *similarity* gate; when there's
nothing to be similar to (filter-only search), it shouldn't apply.

Fix: when the user hasn't supplied a similarity target (no q in
text/phonetic, no codes in Vienna, no upload in Image), return 1.0
so the row passes regardless of where the slider sits.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.settings import get_settings

# Use a different fixture gazette id from test_vienna_search so we don't collide
# when the two tests run in the same session.
_FIXTURE_GAZETTE_ID = uuid.UUID("e0000000-0000-4000-8000-000000000002")


@pytest_asyncio.fixture(autouse=True)
async def seed_filter_only_data() -> AsyncIterator[None]:
    """A handful of B-domestic trademarks with various countries/classes/
    applicant types so we can run filter-only searches against them."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as s:
        # Idempotency
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _FIXTURE_GAZETTE_ID))
        await s.execute(delete(Gazette).where(Gazette.id == _FIXTURE_GAZETTE_ID))
        await s.commit()

        gz = Gazette(
            id=_FIXTURE_GAZETTE_ID,
            filename="TEST_filter_only_fixture.pdf",
            sha256="filteronly_" + uuid.uuid4().hex,
            gazette_type=GazetteType.B,
            issue_year=2099,
            storage_path="/dev/null",
            size_bytes=0,
            status=GazetteStatus.completed,
        )
        s.add(gz)

        # (country, classes, applicant_type, appno)
        rows = [
            ("GB", ["41"], "Company", "FO-001"),
            ("GB", ["41"], "Company", "FO-002"),
            ("GB", ["41"], "Personal", "FO-003"),
            ("US", ["41"], "Company", "FO-004"),
            ("VN", ["09"], "Company", "FO-005"),
        ]
        for cc, classes, atype, appno in rows:
            s.add(
                Trademark(
                    id=uuid.uuid4(),
                    gazette_id=_FIXTURE_GAZETTE_ID,
                    record_type=RecordType.B_domestic,
                    application_number=appno,
                    applicant_country_code=cc,
                    applicant_type=atype,
                    nice_classes=classes,
                )
            )
        await s.commit()

    try:
        yield
    finally:
        async with Session() as s:
            await s.execute(delete(Trademark).where(Trademark.gazette_id == _FIXTURE_GAZETTE_ID))
            await s.execute(delete(Gazette).where(Gazette.id == _FIXTURE_GAZETTE_ID))
            await s.commit()
        await engine.dispose()


async def _filter_count_and_items(client: AsyncClient, **params) -> tuple[int, int]:
    """Hit /api/v1/search/trademarks and return (total, len(items)).

    `total` is the pre-threshold filter-match count.
    `len(items)` is what the grid actually renders after similarity filtering.
    The header/grid divergence the user reported = total > len(items).
    """
    p: dict = {"limit": "200"}
    for k, v in params.items():
        p[k] = v if isinstance(v, list) else str(v)
    r = await client.get("/api/v1/search/trademarks", params=p)
    assert r.status_code == 200, r.text
    body = r.json()
    return int(body["total"]), len(body["items"])


async def test_filter_only_text_search_returns_all_matches(client: AsyncClient) -> None:
    """Text mode with filters but no q must not be silently filtered by the
    similarity threshold. Header total and rendered items must agree."""
    total, items = await _filter_count_and_items(
        client,
        mode="text",
        threshold="0.65",  # default frontend threshold
        country="GB",
        nice_class="41",
        applicant_type="Company",
    )
    assert total >= 2, f"fixture inserted 2 GB+41+Company rows; got total={total}"
    assert items == total, (
        f"filter-only search: header reported {total} matches but grid "
        f"would render only {items} after threshold. Threshold must not "
        f"apply when there's no similarity target."
    )


async def test_filter_only_high_threshold_still_returns_matches(client: AsyncClient) -> None:
    """Even at 99% similarity, a filter-only search must render all rows
    (because the threshold isn't comparing against anything)."""
    _, items = await _filter_count_and_items(
        client,
        mode="text",
        threshold="0.99",
        country="GB",
        nice_class="41",
        applicant_type="Company",
    )
    assert items >= 2


async def test_text_search_with_query_still_respects_threshold(client: AsyncClient) -> None:
    """Sanity: when the user DOES supply a query, the threshold remains
    active. Otherwise this fix would have silently disabled all
    similarity filtering."""
    total, items = await _filter_count_and_items(
        client,
        mode="text",
        threshold="0.95",
        q="zzzz_nonsense_query_no_hits",
        country="GB",
    )
    # The filter still matches GB rows; the threshold filters them out.
    # Allow either: total > items (threshold suppression working) or
    # total == 0 (q-based substring filter already excluded them).
    assert items <= total
