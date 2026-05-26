"""Tests for the Vienna-code search filter and code normalizer.

The Vienna mode searches by figurative-element codes (`(531)` in WIPO INID
terminology). Codes are stored unpadded in the DB (`4.3.3` not `04.03.03`)
because the extractor strips leading zeros; the normalizer makes the
filter tolerate either form at query time.

These tests use httpx against the live ASGI app via conftest's `client`
fixture, so they cover the full route -> _filters -> SQL path. Counts
are loose (greater-than-zero) because the demo dataset evolves; the
contracts under test are:

  - The normalizer rejects shapes that can't be Vienna codes.
  - Vienna search rejects garbage codes without crashing.
  - ANY semantics return a superset of either individual code's results.
  - ALL semantics return a subset of either individual code's results.
  - Zero-padded input matches the unpadded storage form.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db import Gazette, GazetteStatus, GazetteType, RecordType, Trademark
from api.routes._filters import normalize_vienna_code
from api.settings import get_settings

# ----- fixture: seed a small set of Trademark rows with known vienna_codes ---
#
# The live-route tests below assert relative counts (parent >= child,
# ANY >= max, ALL <= min) and presence of specific codes. Both hold up
# whether the DB is empty (CI) or pre-populated with ~46k real marks
# (dev). This fixture inserts just enough rows for the empty-DB case;
# the assertions are robust to either.

_FIXTURE_GAZETTE_ID = uuid.UUID("e0000000-0000-4000-8000-000000000001")


@pytest_asyncio.fixture(autouse=True)
async def seed_vienna_test_data() -> AsyncIterator[None]:
    """Insert one Gazette + 7 Trademark rows with known vienna_codes,
    teardown after each test. Function-scoped because pytest-asyncio's
    event_loop is function-scoped by default and a higher-scoped fixture
    triggers ScopeMismatch. The data set is tiny (8 rows) so per-test
    setup/teardown is cheap."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    inserted_tm_ids: list[uuid.UUID] = []
    async with Session() as s:
        # Idempotency: drop any leftover seed rows from a previous aborted run.
        await s.execute(delete(Trademark).where(Trademark.gazette_id == _FIXTURE_GAZETTE_ID))
        await s.execute(delete(Gazette).where(Gazette.id == _FIXTURE_GAZETTE_ID))
        await s.commit()

        gz = Gazette(
            id=_FIXTURE_GAZETTE_ID,
            filename="TEST_vienna_fixture.pdf",
            sha256="vienna_test_" + uuid.uuid4().hex,
            gazette_type=GazetteType.A,
            issue_year=2099,
            storage_path="/dev/null",
            size_bytes=0,
            status=GazetteStatus.completed,
        )
        s.add(gz)

        # (vienna_codes, appno) tuples covering each assertion the suite makes.
        rows: list[tuple[list[str] | None, str]] = [
            (["26.1.1"], "TM-V-001"),
            (["26.1.1", "5.3.13"], "TM-V-002"),
            (["5.3.13"], "TM-V-003"),
            (["5.7.1"], "TM-V-004"),  # child of parent code 5.7
            (["5.7.20"], "TM-V-005"),  # another child
            (["15.7.1"], "TM-V-006"),  # boundary: 5.7 prefix must NOT match
            (None, "TM-V-007"),  # control row with no codes
        ]
        for codes, appno in rows:
            tm = Trademark(
                id=uuid.uuid4(),
                gazette_id=_FIXTURE_GAZETTE_ID,
                record_type=RecordType.A,
                application_number=appno,
                vienna_codes=codes,
            )
            s.add(tm)
            inserted_tm_ids.append(tm.id)
        await s.commit()

    try:
        yield
    finally:
        async with Session() as s:
            await s.execute(delete(Trademark).where(Trademark.gazette_id == _FIXTURE_GAZETTE_ID))
            await s.execute(delete(Gazette).where(Gazette.id == _FIXTURE_GAZETTE_ID))
            await s.commit()
        await engine.dispose()

# ----- normalizer unit tests --------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4.3.3", "4.3.3"),
        ("04.03.03", "4.3.3"),
        ("26.1.1", "26.1.1"),
        ("26.01.01", "26.1.1"),
        ("26.11.12", "26.11.12"),  # multi-digit segments preserved
        ("02.01", "2.1"),  # 2-level codes accepted
        ("  4.3.3  ", "4.3.3"),  # surrounding whitespace stripped
    ],
)
def test_normalize_vienna_code_strips_leading_zeros(raw: str, expected: str) -> None:
    assert normalize_vienna_code(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",  # empty
        "26",  # single segment — not a Vienna code
        "26.1.1.1",  # 4 segments — too many
        "26.a.1",  # non-numeric segment
        "26..1",  # empty segment
        "abc",  # garbage
    ],
)
def test_normalize_vienna_code_rejects_bad_shapes(raw: str) -> None:
    assert normalize_vienna_code(raw) is None


# ----- live route tests -------------------------------------------------------


async def _vienna_count(client: AsyncClient, **params) -> int:
    """Hit /api/v1/search/trademarks?mode=vienna&... and return total."""
    p: dict = {"mode": "vienna", "limit": "1"}
    for k, v in params.items():
        p[k] = v if isinstance(v, list) else str(v)
    r = await client.get("/api/v1/search/trademarks", params=p)
    assert r.status_code == 200, r.text
    return int(r.json()["total"])


async def test_vienna_filter_returns_subset_of_total(client: AsyncClient) -> None:
    """A specific Vienna code matches strictly fewer marks than the full corpus."""
    total = await _vienna_count(client, mode="text")  # baseline w/o vienna filter
    sub = await _vienna_count(client, vienna_codes=["26.1.1"])
    assert 0 < sub <= total, f"expected 0 < {sub} <= {total}"


async def test_vienna_zero_padded_matches_unpadded(client: AsyncClient) -> None:
    """Front-end / WIPO references zero-pad; the normalizer strips them
    so the same query returns the same count either way."""
    unpadded = await _vienna_count(client, vienna_codes=["26.1.1"])
    padded = await _vienna_count(client, vienna_codes=["26.01.01"])
    assert unpadded == padded, f"unpadded={unpadded} padded={padded}"


async def test_vienna_garbage_code_returns_no_extra_results(client: AsyncClient) -> None:
    """A malformed code is dropped silently after normalization."""
    just_one = await _vienna_count(client, vienna_codes=["26.1.1"])
    garbage_and_one = await _vienna_count(client, vienna_codes=["not.a.code", "26.1.1"])
    assert garbage_and_one == just_one


async def test_vienna_any_is_superset_of_each(client: AsyncClient) -> None:
    """ANY semantics: matches rows containing code A OR code B. Must be
    at least as many as either alone."""
    a = await _vienna_count(client, vienna_codes=["26.1.1"])
    b = await _vienna_count(client, vienna_codes=["5.3.13"])
    any_ab = await _vienna_count(client, vienna_codes=["26.1.1", "5.3.13"], vienna_codes_mode="any")
    assert any_ab >= max(a, b)


async def test_vienna_all_is_subset_of_each(client: AsyncClient) -> None:
    """ALL semantics: matches rows containing code A AND code B. Must be
    at most as many as either alone."""
    a = await _vienna_count(client, vienna_codes=["26.1.1"])
    b = await _vienna_count(client, vienna_codes=["5.3.13"])
    all_ab = await _vienna_count(client, vienna_codes=["26.1.1", "5.3.13"], vienna_codes_mode="all")
    assert all_ab <= min(a, b)


async def test_vienna_mode_drops_text_q(client: AsyncClient) -> None:
    """When mode=vienna, the `q` field is ignored — codes ARE the query.
    Otherwise typing codes in the textbox would do a substring search
    on applicant_name / mark_sample and return zero matches.
    """
    just_codes = await _vienna_count(client, vienna_codes=["26.1.1"])
    with_text = await _vienna_count(client, vienna_codes=["26.1.1"], q="zzzzz_does_not_exist")
    assert just_codes == with_text, "q should be ignored in vienna mode"


async def test_vienna_results_include_the_requested_code(client: AsyncClient) -> None:
    """Sanity: every row returned by a Vienna search must actually contain
    the requested code in its vienna_codes list."""
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"mode": "vienna", "vienna_codes": "26.1.1", "limit": "5"},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    for it in items:
        codes = it["mark"]["vienna_codes"]
        assert codes is not None and "26.1.1" in codes, f"unexpected row: {it}"


async def test_vienna_parent_code_matches_child_codes(client: AsyncClient) -> None:
    """A 2-level parent code like `5.7` (Flowers) must match marks carrying
    any 3-level child like `5.7.1` or `5.7.20`. The DB stores only 3-level
    codes, so without prefix expansion a user clicking the 'Flowers'
    quick-pick would see 0 results — broken UX.
    """
    parent_count = await _vienna_count(client, vienna_codes=["5.7"])
    child_count = await _vienna_count(client, vienna_codes=["5.7.1"])
    assert parent_count > 0, "parent code must match some marks"
    assert (
        child_count <= parent_count
    ), f"parent ({parent_count}) should be a superset of any single child ({child_count})"


async def test_vienna_parent_zero_padded_matches_child(client: AsyncClient) -> None:
    """Same as above but the user types the zero-padded form (05.07).
    Normalizer strips zeros, then the prefix expansion finds children."""
    a = await _vienna_count(client, vienna_codes=["5.7"])
    b = await _vienna_count(client, vienna_codes=["05.07"])
    assert a == b > 0


async def test_vienna_parent_does_not_match_unrelated_prefixes(client: AsyncClient) -> None:
    """`5.7` must NOT match `5.70.x` or `15.7.x` — the prefix expansion is
    boundary-aware via comma delimiters."""
    r = await client.get(
        "/api/v1/search/trademarks",
        params={"mode": "vienna", "vienna_codes": "5.7", "limit": "20"},
    )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) > 0
    for it in items:
        codes = it["mark"]["vienna_codes"] or []
        assert any(c == "5.7" or c.startswith("5.7.") for c in codes), (
            f"row {it['mark']['application_number']} matched 5.7 but its "
            f"codes are {codes} — boundary leak"
        )
