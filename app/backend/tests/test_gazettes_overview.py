"""Gazettes overview aggregation endpoint + list filters (PR 1 of the
gazettes-tab redesign).

These run against the shared dev DB while the enrichment sweeps may be
writing rows, so we seed into two synthetic FUTURE issue-years (2098/2099)
that no real gazette uses. That makes the *per-year* buckets for those
years exactly equal to what we seeded (deterministic, hand-computable),
while global totals/coverage are asserted only as lower-bound invariants
(they move under live data + the sweep).

Classification is keyed off `trademarks.mark_category` — the generated
column — NOT `record_type`. mark_category is derived from which id columns
are populated:
  domestic_application  → application_number only
  domestic_registration → application_number + certificate_number
  madrid_registration   → certificate_number only
  madrid_renewal        → madrid_number only
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
from api.db.models import DomesticRecord, MadridRecord
from api.settings import get_settings

# Two synthetic gazettes in two future years that live data never uses.
_GZ_A_2098 = uuid.UUID("e1000000-0000-4000-8000-000000000a01")  # A-file, 2098
_GZ_B_2099 = uuid.UUID("e1000000-0000-4000-8000-000000000b02")  # B-file, 2099
_IRN1 = "9200001"  # synthetic, above the live WIPO IRN range; no collision
_IRN2 = "9200002"

# Hand-computed seed plan (see _seed below):
#   2098 (A-file gazette): 3 domestic_application
#   2099 (B-file gazette): 2 domestic_registration
#                          2 madrid_registration  (certificate_number only)
#                          1 madrid_renewal       (madrid_number only)
_N_APP_2098 = 3
_N_DOMREG_2099 = 2
_N_MADREG_2099 = 2
_N_MADRENEW_2099 = 1

# Domestic representative seed: three case/whitespace variants of ONE firm
# (norm → 1 key, 3 marks) plus a genuinely distinct firm (1 key, 2 marks).
_REP_FIRM_A = "Công ty Luật TAGA"
_REP_FIRM_B = "Distinct Firm XYZ"

# mark_category values that count as "domestic" (mirrors routes/gazettes.py).
_DOMESTIC_CATEGORIES = ("domestic_application", "domestic_registration")


def _tm(gazette_id: uuid.UUID, *, rep: str | None = None, app: str | None = None, **ids: str) -> Trademark:
    from api._entity_norm import resolve_applicant, resolve_representative

    app_clean, app_norm = resolve_applicant(app, None, None)
    rep_clean, rep_norm = resolve_representative(rep, None, None)
    return Trademark(
        id=uuid.uuid4(),
        gazette_id=gazette_id,
        record_type=RecordType.A,
        applicant_clean=app_clean,
        applicant_norm=app_norm,
        representative_clean=rep_clean,
        representative_norm=rep_norm,
        **ids,
    )


@pytest_asyncio.fixture(autouse=True)
async def seed() -> AsyncIterator[None]:
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async def _cleanup(s) -> None:
        await s.execute(
            delete(DomesticRecord).where(
                DomesticRecord.application_number.in_(["OVWAPP0", "OVWAPP1", "OVWAPP2", "OVWREG0", "OVWREG1"])
            )
        )
        await s.execute(delete(MadridRecord).where(MadridRecord.irn.in_([_IRN1, _IRN2])))
        await s.execute(delete(Trademark).where(Trademark.gazette_id.in_([_GZ_A_2098, _GZ_B_2099])))
        await s.execute(delete(Gazette).where(Gazette.id.in_([_GZ_A_2098, _GZ_B_2099])))

    async with Session() as s:
        await _cleanup(s)
        await s.commit()

        s.add(
            Gazette(
                id=_GZ_A_2098,
                filename="A_T1_2098.pdf",
                sha256="ovw_a_" + uuid.uuid4().hex,
                gazette_type=GazetteType.A,
                issue_year=2098,
                issue_number=1,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.completed,
            )
        )
        s.add(
            Gazette(
                id=_GZ_B_2099,
                filename="B_T1_2099.pdf",
                sha256="ovw_b_" + uuid.uuid4().hex,
                gazette_type=GazetteType.B,
                issue_year=2099,
                issue_number=1,
                storage_path="/dev/null",
                size_bytes=0,
                status=GazetteStatus.processing,
            )
        )

        # 2098 A-file: 3 domestic_application carrying the 3 rep variants of one
        # firm (norm → 1 key) + applicant "TAGA Co".
        _rep_variants = ["Công ty Luật TAGA", "CÔNG TY LUẬT TAGA", "Công  ty   Luật   TAGA"]
        for i in range(_N_APP_2098):
            s.add(_tm(_GZ_A_2098, application_number=f"OVWAPP{i}", rep=_rep_variants[i], app="TAGA Co"))

        # 2099 B-file: 2 domestic_registration carrying the distinct firm.
        for i in range(_N_DOMREG_2099):
            s.add(
                _tm(
                    _GZ_B_2099,
                    application_number=f"OVWREG{i}",
                    certificate_number=f"OVWREGC{i}",
                    rep="Distinct Firm XYZ",
                    app="XYZ Ltd",
                )
            )
        # 2 madrid_registration (cert only) — soft-join to madrid_records by IRN
        s.add(_tm(_GZ_B_2099, certificate_number=_IRN1))
        s.add(_tm(_GZ_B_2099, certificate_number=_IRN2))
        # 1 madrid_renewal (madrid_number only)
        s.add(_tm(_GZ_B_2099, madrid_number="9200099"))

        # madrid_records for the two madrid_registration IRNs (origin + holder)
        s.add(
            MadridRecord(
                irn=_IRN1,
                holder_name="OVERVIEW HOLDER ONE",
                holder_country="ZZ",
                representative="OVW REP ALPHA 123 Main St, Zürich",
                vn_status="granted",
                vn_designated=True,
                designated_countries=["VN"],
            )
        )
        s.add(
            MadridRecord(
                irn=_IRN2,
                holder_name="OVERVIEW HOLDER ONE",  # same holder → n=2
                holder_country="ZZ",
                representative="OVW REP ALPHA 456 Other Rd, Bern",
                vn_status="granted",
                vn_designated=True,
                designated_countries=["VN"],
            )
        )
        # Domestic enrichment rows joined by application_number. The three
        # OVWAPP* reps are case/whitespace variants of ONE firm (norm → 1 key,
        # 3 marks); the two OVWREG* reps are a second, distinct firm (2 marks).
        s.add(
            DomesticRecord(
                application_number="OVWAPP0", applicant_name="TAGA Co", representative="Công ty Luật TAGA"
            )
        )
        s.add(
            DomesticRecord(
                application_number="OVWAPP1", applicant_name="TAGA Co", representative="CÔNG TY LUẬT TAGA"
            )
        )
        s.add(
            DomesticRecord(
                application_number="OVWAPP2",
                applicant_name="TAGA Co",
                representative="Công  ty   Luật   TAGA",
            )
        )
        s.add(
            DomesticRecord(
                application_number="OVWREG0", applicant_name="XYZ Ltd", representative="Distinct Firm XYZ"
            )
        )
        s.add(
            DomesticRecord(
                application_number="OVWREG1", applicant_name="XYZ Ltd", representative="Distinct Firm XYZ"
            )
        )
        await s.commit()
    yield
    async with Session() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


def _year_row(per_year: list[dict], year: int) -> dict:
    matches = [r for r in per_year if r["year"] == year]
    assert len(matches) == 1, f"expected exactly one per_year row for {year}, got {matches}"
    return matches[0]


@pytest.mark.asyncio
async def test_overview_per_year_stream_counts(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/gazettes/overview")
    assert r.status_code == 200
    d = r.json()

    # 2098 bucket = exactly our seeded A-file applications.
    y2098 = _year_row(d["per_year"], 2098)
    assert y2098["applications"] == _N_APP_2098
    assert y2098["domestic_registrations"] == 0
    assert y2098["madrid_registrations"] == 0
    assert y2098["madrid_renewals"] == 0

    # 2099 bucket = exactly our seeded B-file mix.
    y2099 = _year_row(d["per_year"], 2099)
    assert y2099["applications"] == 0
    assert y2099["domestic_registrations"] == _N_DOMREG_2099
    assert y2099["madrid_registrations"] == _N_MADREG_2099
    assert y2099["madrid_renewals"] == _N_MADRENEW_2099


@pytest.mark.asyncio
async def test_overview_totals_sum(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/gazettes/overview")
    d = r.json()
    t = d["totals"]
    # total == sum of the four streams.
    assert t["total"] == (
        t["applications"] + t["domestic_registrations"] + t["madrid_registrations"] + t["madrid_renewals"]
    )
    # totals == column-sum over per_year (internal consistency).
    assert t["applications"] == sum(row["applications"] for row in d["per_year"])
    assert t["domestic_registrations"] == sum(row["domestic_registrations"] for row in d["per_year"])
    assert t["madrid_registrations"] == sum(row["madrid_registrations"] for row in d["per_year"])
    assert t["madrid_renewals"] == sum(row["madrid_renewals"] for row in d["per_year"])
    # Our seed contributes its known minimums.
    assert t["applications"] >= _N_APP_2098
    assert t["madrid_registrations"] >= _N_MADREG_2099
    assert t["madrid_renewals"] >= _N_MADRENEW_2099


@pytest.mark.asyncio
async def test_overview_madrid_streams_use_mark_category_not_record_type(
    authed_client: AsyncClient,
) -> None:
    """All seeded trademarks carry record_type=A (the cheapest non-null value),
    yet the Madrid streams must still be populated from mark_category. If the
    endpoint keyed off record_type, the 2099 madrid_* buckets would be 0."""
    r = await authed_client.get("/api/v1/gazettes/overview")
    d = r.json()
    y2099 = _year_row(d["per_year"], 2099)
    assert y2099["madrid_registrations"] == _N_MADREG_2099
    assert y2099["madrid_renewals"] == _N_MADRENEW_2099
    # And the domestic_registration rows are NOT lumped with madrid.
    assert y2099["domestic_registrations"] == _N_DOMREG_2099


@pytest.mark.asyncio
async def test_overview_status_breakdown_and_coverage(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/gazettes/overview")
    d = r.json()
    sb = d["status_breakdown"]
    for key in ("completed", "processing", "failed", "uploaded", "flagged"):
        assert key in sb
    # We seeded one completed (2098) + one processing (2099).
    assert sb["completed"] >= 1
    assert sb["processing"] >= 1

    cov = d["coverage"]
    assert cov["present"] >= 1
    assert cov["expected"] >= cov["present"]
    assert "missing" in cov
    assert isinstance(cov["missing"], list)


@pytest.mark.asyncio
async def test_overview_madrid_origin_and_holders(authed_client: AsyncClient) -> None:
    # These panels are top-N ranked over the whole (live) corpus, so our two
    # synthetic rows won't surface above the real CN/US/DE leaders. Assert the
    # ranking contract instead: capped at the documented N, sorted desc.
    r = await authed_client.get("/api/v1/gazettes/overview")
    d = r.json()

    origins = d["madrid_origin"]
    assert len(origins) <= 8
    origin_ns = [o["n"] for o in origins]
    assert origin_ns == sorted(origin_ns, reverse=True)
    assert all(o["country"] is not None for o in origins)

    mad_apps = d["top_applicants"]["madrid"]
    assert len(mad_apps) <= 6
    app_ns = [a["n"] for a in mad_apps]
    assert app_ns == sorted(app_ns, reverse=True)

    dom_apps = d["top_applicants"]["domestic"]
    assert len(dom_apps) <= 6
    dom_ns = [a["n"] for a in dom_apps]
    assert dom_ns == sorted(dom_ns, reverse=True)


@pytest.mark.asyncio
async def test_overview_representatives_no_approximate_flag(authed_client: AsyncClient) -> None:
    """Counts are now exact (trusted source + norm), so the `approximate` flag
    is gone from the payload entirely."""
    r = await authed_client.get("/api/v1/gazettes/overview")
    d = r.json()
    reps = d["top_representatives"]
    assert "approximate" not in reps
    assert "domestic" in reps and "madrid" in reps
    assert isinstance(reps["domestic"], list)
    assert isinstance(reps["madrid"], list)
    # Ranking contract: capped at 6, sorted by descending count.
    for side in ("domestic", "madrid"):
        ns = [row["n"] for row in reps[side]]
        assert len(ns) <= 6
        assert ns == sorted(ns, reverse=True)


@pytest.mark.asyncio
async def test_overview_requires_admin(viewer_client: AsyncClient) -> None:
    r = await viewer_client.get("/api/v1/gazettes/overview")
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_overview_requires_auth(client: AsyncClient) -> None:
    r = await client.get("/api/v1/gazettes/overview")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# List filters
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_year_and_type(authed_client: AsyncClient) -> None:
    # year=2099 & gazette_type=B → only our seeded B-file gazette.
    r = await authed_client.get("/api/v1/gazettes?year=2099&gazette_type=B")
    assert r.status_code == 200
    d = r.json()
    assert d["total"] == 1
    assert d["items"][0]["filename"] == "B_T1_2099.pdf"
    assert d["items"][0]["gazette_type"] == "B"

    # year=2098 & gazette_type=B → none (our 2098 gazette is type A).
    r = await authed_client.get("/api/v1/gazettes?year=2098&gazette_type=B")
    assert r.json()["total"] == 0

    # year=2098 & gazette_type=A → our A-file gazette.
    r = await authed_client.get("/api/v1/gazettes?year=2098&gazette_type=A")
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["filename"] == "A_T1_2098.pdf"


@pytest.mark.asyncio
async def test_list_filter_status(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/gazettes?year=2099&status=processing")
    assert r.json()["total"] == 1
    r = await authed_client.get("/api/v1/gazettes?year=2099&status=completed")
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_summary_years(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/v1/gazettes?summary=years")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    by_year = {row["year"]: row for row in rows}

    assert 2098 in by_year
    assert by_year[2098]["issue_count"] == 1
    assert by_year[2098]["marks"] == _N_APP_2098
    assert "flagged" in by_year[2098]

    assert 2099 in by_year
    assert by_year[2099]["issue_count"] == 1
    assert by_year[2099]["marks"] == (_N_DOMREG_2099 + _N_MADREG_2099 + _N_MADRENEW_2099)


@pytest.mark.asyncio
async def test_list_default_behavior_unchanged(authed_client: AsyncClient) -> None:
    """No filters → still the paginated GazetteListOut with items + total."""
    r = await authed_client.get("/api/v1/gazettes")
    assert r.status_code == 200
    d = r.json()
    assert "items" in d and "total" in d
    assert isinstance(d["items"], list)


@pytest.mark.asyncio
async def test_domestic_reps_merge_variants_and_keep_distinct_firms_distinct() -> None:
    """The trusted-source join + norm grouping collapses case/whitespace variants
    of ONE firm into a single key (3 marks) while keeping a genuinely different
    firm separate (2 marks). Asserted on the seeded subset so it's immune to live
    data — it exercises the exact query + norm the endpoint uses."""
    from sqlalchemy import func, select

    from api._entity_norm import norm

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    appnos = ["OVWAPP0", "OVWAPP1", "OVWAPP2", "OVWREG0", "OVWREG1"]
    async with Session() as s:
        raws = (
            (
                await s.execute(
                    select(func.coalesce(DomesticRecord.representative, Trademark.ip_agency_raw_740))
                    .select_from(Trademark)
                    .outerjoin(
                        DomesticRecord,
                        DomesticRecord.application_number == Trademark.application_number,
                    )
                    .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
                    .where(Trademark.application_number.in_(appnos))
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()

    grouped: dict[str, int] = {}
    for raw in raws:
        grouped[norm(raw)] = grouped.get(norm(raw), 0) + 1

    assert grouped[norm(_REP_FIRM_A)] == 3  # three variants merged
    assert grouped[norm(_REP_FIRM_B)] == 2  # distinct firm kept separate
    assert norm(_REP_FIRM_A) != norm(_REP_FIRM_B)
    assert len(grouped) == 2


@pytest.mark.asyncio
async def test_domestic_reps_aggregator_equals_hand_computed_norm_grouping() -> None:
    """The production aggregator that builds /overview's domestic representative
    counts (`_top_entities`) equals a hand-computed
    `GROUP BY norm(coalesce(domestic_records.representative, ip_agency_raw_740))`
    over the same rows.

    Both sides are computed over ONE DB snapshot (a single fetch), so this is
    deterministic even while the live domestic sweep is writing rows — comparing
    the endpoint's HTTP response against a separate recompute would race the
    sweep across the request boundary (the table grows by ~1 row between the two
    reads). We instead assert the exact code path the endpoint uses is a correct
    norm-GROUP-BY. Compared by norm key so display tie-breaking can't spuriously
    fail."""
    from collections import Counter

    from sqlalchemy import func, select

    from api._entity_norm import norm
    from api.routes.gazettes import _top_entities

    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        raws = (
            (
                await s.execute(
                    select(func.coalesce(DomesticRecord.representative, Trademark.ip_agency_raw_740))
                    .select_from(Trademark)
                    .outerjoin(
                        DomesticRecord,
                        DomesticRecord.application_number == Trademark.application_number,
                    )
                    .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
                )
            )
            .scalars()
            .all()
        )
    await engine.dispose()

    # Hand-computed GROUP BY norm over the SAME snapshot.
    counts: Counter[str] = Counter()
    for raw in raws:
        if not raw or not raw.strip():
            continue
        key = norm(raw)
        if key:
            counts[key] += 1
    expected = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]

    # Production aggregator over the same snapshot; map display names back to
    # norm keys for an apples-to-apples (key, count) comparison.
    got = [(norm(nc.name), nc.n) for nc in _top_entities(raws)]
    assert got == expected


@pytest.mark.asyncio
async def test_overview_domestic_reps_are_a_valid_norm_grouping(authed_client: AsyncClient) -> None:
    """Live-endpoint invariant check: /overview's domestic representatives are a
    proper norm-grouping — each displayed name collapses to a DISTINCT norm key
    (no raw OCR fragments of one firm split across rows), capped at 6, sorted by
    descending count. Counts themselves move under the live sweep, so they are
    asserted exactly by the deterministic aggregator test above, not here."""
    from api._entity_norm import norm

    r = await authed_client.get("/api/v1/gazettes/overview")
    assert r.status_code == 200
    domestic = r.json()["top_representatives"]["domestic"]

    assert len(domestic) <= 6
    ns = [row["n"] for row in domestic]
    assert ns == sorted(ns, reverse=True)
    # Grouping happened: distinct rows must not share a norm key.
    keys = [norm(row["name"]) for row in domestic]
    assert len(keys) == len(set(keys))


@pytest.mark.asyncio
async def test_domestic_panels_column_groupby_equals_phase1_join_over_seed() -> None:
    """Phase-2 column GROUP BY equals the Phase-1 join grouping over the SAME
    seeded subset — proving 'same results, faster path'. Scoped to the synthetic
    OVW* marks so it is immune to the live sweep (no cross-read race)."""
    from collections import Counter

    from sqlalchemy import func, select

    from api._entity_norm import norm

    appnos = ["OVWAPP0", "OVWAPP1", "OVWAPP2", "OVWREG0", "OVWREG1"]
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        # Phase-1 path: coalesce(domestic_records.representative, 740) + Python norm.
        phase1_raws = (
            (
                await s.execute(
                    select(func.coalesce(DomesticRecord.representative, Trademark.ip_agency_raw_740))
                    .select_from(Trademark)
                    .outerjoin(
                        DomesticRecord,
                        DomesticRecord.application_number == Trademark.application_number,
                    )
                    .where(Trademark.application_number.in_(appnos))
                )
            )
            .scalars()
            .all()
        )
        # Phase-2 path: GROUP BY the denormalized representative_norm column.
        phase2 = (
            await s.execute(
                select(Trademark.representative_norm, func.count())
                .where(Trademark.application_number.in_(appnos))
                .where(Trademark.representative_norm.is_not(None))
                .group_by(Trademark.representative_norm)
            )
        ).all()
    await engine.dispose()

    phase1_counts = Counter(norm(r) for r in phase1_raws if r and r.strip())
    phase2_counts = {k: n for k, n in phase2}
    assert phase2_counts == dict(phase1_counts)
    # The 3 variants collapsed to one key (3 marks); the distinct firm kept (2).
    assert phase2_counts[norm("Công ty Luật TAGA")] == 3
    assert phase2_counts[norm("Distinct Firm XYZ")] == 2
