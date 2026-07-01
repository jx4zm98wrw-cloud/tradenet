"""Faceted-count endpoints — same filter set as `/api/trademarks`, but each
endpoint excludes its own column from the WHERE so the user can see "if I
selected this value, how many results would I get" rather than zero.
"""

from __future__ import annotations

import functools
import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from typing import Any, TypeVar

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .._dedup import representative_marks
from ..db import RecordType, get_session
from ..db.models import MadridRecord
from ._filters import build_trademark_where
from .stats import NICE_LABELS, CountBucket

router = APIRouter(prefix="/api/v1/facets", tags=["facets"])


# --- Facet response cache -----------------------------------------------------
# The Search page fires ~7 facet counts in parallel on every visit, and the
# DEFAULT (unfiltered) counts are near-static — they change only when a gazette
# is ingested. Each count seq-scans the whole `representative_marks` set (~70 ms
# isolated, but ~600 ms under the 7-way concurrent contention on one worker), so
# an in-process TTL cache turns repeat visits into ~0 ms hits. Keyed by
# (endpoint, limit, filter signature) so filtered facets cache independently and
# never collide with the unfiltered defaults.
#
# TTL-bounded (no cross-process invalidation) — after an ingest, facet counts can
# be up to `_FACET_TTL_S` stale. Per-worker (fine: each warms on first hit).
_FACET_TTL_S = 120.0
_FACET_CACHE_MAX = 512  # bound memory; clear wholesale when exceeded (rare — few filter combos)
_facet_cache: dict[tuple[Any, ...], tuple[float, Any]] = {}

_F = TypeVar("_F", bound=Callable[..., Awaitable[Any]])


def _facet_cached(name: str) -> Callable[[_F], _F]:
    """Decorator: TTL-cache a facet endpoint's return by (name, limit, filters).

    Wraps with functools.wraps so FastAPI still resolves the original signature
    (its dependency injection follows __wrapped__)."""

    def deco(fn: _F) -> _F:
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            filters: dict = kwargs.get("filters", {})
            sig = tuple(sorted((k, str(v)) for k, v in filters.items() if v is not None))
            key = (name, kwargs.get("limit"), sig)
            now = time.monotonic()
            hit = _facet_cache.get(key)
            if hit is not None and hit[0] > now:
                return hit[1]
            result = await fn(*args, **kwargs)
            if len(_facet_cache) >= _FACET_CACHE_MAX:
                _facet_cache.clear()
            _facet_cache[key] = (now + _FACET_TTL_S, result)
            return result

        return wrapper  # type: ignore[return-value]

    return deco


# Shared Query() filter signature — keep in sync with /api/search/trademarks.
def _filter_params(
    q: str | None = Query(None),
    country: str | None = Query(None, min_length=2, max_length=2),
    nice_class: list[str] | None = Query(None),
    record_type: RecordType | None = None,
    mark_category: str | None = Query(None),
    applicant_type: str | None = Query(None),
    applicant: str | None = Query(None),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    gazette_id: uuid.UUID | None = None,
    ip_agency: str | None = Query(None),
    designated_country: str | None = Query(None),
    vn_status: str | None = Query(None),
    granted: bool | None = Query(None),
    grant_date_from: date | None = Query(None),
    grant_date_to: date | None = Query(None),
):
    return dict(
        q=q,
        country=country,
        nice_class=nice_class,
        record_type=record_type,
        mark_category=mark_category,
        applicant_type=applicant_type,
        applicant=applicant,
        year=year,
        month=month,
        gazette_id=gazette_id,
        ip_agency=ip_agency,
        designated_country=designated_country,
        vn_status=vn_status,
        granted=granted,
        grant_date_from=grant_date_from,
        grant_date_to=grant_date_to,
    )


@router.get("/countries", response_model=list[CountBucket])
@_facet_cached("countries")
async def facet_countries(
    filters: dict = Depends(_filter_params),
    limit: int = Query(20, ge=1, le=300),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    where = build_trademark_where(**filters, exclude="country")
    # Count UNIQUE marks, not raw gazette rows: a mark with both an application
    # and a registration row would otherwise be tallied twice. The deduped view
    # carries `where` in its subquery and yields one (most-advanced) row per mark.
    rep = representative_marks(where)
    stmt = (
        select(rep.applicant_country_code, func.count())
        .where(rep.applicant_country_code.is_not(None))
        .group_by(rep.applicant_country_code)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=cc, count=n) for cc, n in rows]


@router.get("/nice-classes", response_model=list[CountBucket])
@_facet_cached("nice-classes")
async def facet_nice_classes(
    filters: dict = Depends(_filter_params),
    limit: int = Query(45, ge=1, le=45),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Unnest `nice_classes[]` and count per class, applying all current filters
    EXCEPT the `nice_class` filter itself.
    """
    where = build_trademark_where(**filters, exclude="nice_class")
    # Unnest the deduped view's class lists so each unique mark contributes its
    # classes once (raw rows would double-count a mark present as app + reg).
    rep = representative_marks(where)
    cls_col = func.unnest(rep.nice_classes).label("cls")
    stmt = (
        select(cls_col, func.count())
        .where(rep.nice_classes.is_not(None))
        .group_by(cls_col)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=cls, label=NICE_LABELS.get(cls, ""), count=n) for cls, n in rows]


@router.get("/applicants", response_model=list[CountBucket])
@_facet_cached("applicants")
async def facet_applicants(
    filters: dict = Depends(_filter_params),
    limit: int = Query(20, ge=1, le=300),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Top applicant names under the current filter set (excluding the
    applicant filter itself), ordered by mark count.

    Used by the sidebar's "Applicant" facet group. Applicant names that
    only show up once or twice are pushed down the list naturally —
    most users want to filter by the big repeat applicants (CHANEL,
    L'OREAL, CÔNG TY CỔ PHẦN …).
    """
    where = build_trademark_where(**filters, exclude="applicant")
    # Count unique marks per applicant (one most-advanced row per mark), so the
    # rail matches the deduped result total rather than raw gazette appearances.
    rep = representative_marks(where)
    stmt = (
        select(rep.applicant_name, func.count())
        .where(rep.applicant_name.is_not(None))
        .group_by(rep.applicant_name)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=name, count=n) for name, n in rows]


# Human-readable labels for the derived mark_category buckets. Mirrors the
# frontend MARK_CATEGORY_LABELS (lib/api.ts) — keep the two in sync.
MARK_CATEGORY_LABELS: dict[str, str] = {
    "domestic_application": "Domestic application",
    "domestic_registration": "Domestic registration",
    "madrid_registration": "Madrid registration",
    "madrid_renewal": "Madrid renewal",
    "unknown": "Unclassified",
}


@router.get("/mark-categories", response_model=list[CountBucket])
@_facet_cached("mark-categories")
async def facet_mark_categories(
    filters: dict = Depends(_filter_params),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Count rows per derived mark_category under the current filter set
    (excluding the mark_category filter itself), so the rail can show "if I
    picked Madrid registration, how many?" — the bucket record_type can't
    express because it folds Madrid registrations into B_domestic.
    """
    where = build_trademark_where(**filters, exclude="mark_category")
    # Group by the deduped view's category so each unique mark lands in ONE
    # bucket — its most-advanced row's category. A mark present as both an
    # application and a registration row counts once under domestic_registration
    # (not once under each), so the buckets sum to the deduped result total.
    rep = representative_marks(where)
    stmt = select(rep.mark_category, func.count()).group_by(rep.mark_category).order_by(desc(func.count()))
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=cat, label=MARK_CATEGORY_LABELS.get(cat, cat), count=n) for cat, n in rows]


VN_STATUS_LABELS: dict[str, str] = {
    "granted": "Granted in VN",
    "pending": "Pending in VN",
    "refused": "Refused in VN",
}


@router.get("/vn-status", response_model=list[CountBucket])
@_facet_cached("vn-status")
async def facet_vn_status(
    filters: dict = Depends(_filter_params),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Count marks per VN protection status under the current filter set
    (excluding the vn_status filter itself), via the lineage_key join."""
    where = build_trademark_where(**filters, exclude="vn_status")
    # Join the deduped view (one row per IRN) so a Madrid mark present as both a
    # registration and a renewal row — sharing lineage_key — counts once.
    rep = representative_marks(where)
    stmt = (
        select(MadridRecord.vn_status, func.count())
        .join(rep, rep.lineage_key == MadridRecord.irn)
        .group_by(MadridRecord.vn_status)
    )
    rows = (await session.execute(stmt)).all()
    return [
        CountBucket(key=st, label=VN_STATUS_LABELS.get(st, st), count=n) for st, n in rows if st is not None
    ]


@router.get("/granted", response_model=list[CountBucket])
@_facet_cached("granted")
async def facet_granted(
    filters: dict = Depends(_filter_params),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Count of marks with a resolved VN grant date (trademarks.vn_grant_date
    IS NOT NULL) under the current filter set, excluding the granted filter
    itself. Unifies domestic + Madrid grants — replaces the Madrid-only
    vn_status='granted' bucket."""
    where = build_trademark_where(**filters, exclude="granted")
    # Count unique granted marks over the deduped view. The grant date is
    # resolved per mark and written to EVERY gazette row of an appno, so a raw
    # count(*) tallied each granted mark once per row (app + reg = 2x); the
    # representative row carries the same grant date, counted once.
    rep = representative_marks(where)
    stmt = select(func.count()).select_from(rep).where(rep.vn_grant_date.is_not(None))
    n = (await session.execute(stmt)).scalar_one()
    return [CountBucket(key="granted", label="Granted", count=n)]


@router.get("/ip-agencies", response_model=list[CountBucket])
@_facet_cached("ip-agencies")
async def facet_ip_agencies(
    filters: dict = Depends(_filter_params),
    limit: int = Query(20, ge=1, le=300),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Top IP-agency / law-firm names under the current filter set,
    excluding the ip_agency filter itself.

    The DB stores the agency name as free text from the gazette's
    (740) marker, so two slightly different spellings of the same firm
    will appear as separate buckets — acceptable for a facet picker
    where the user picks the exact spelling they want to match.
    """
    where = build_trademark_where(**filters, exclude="ip_agency")
    # Count unique marks per agency (one most-advanced row per mark).
    rep = representative_marks(where)
    stmt = (
        select(rep.ip_agency, func.count())
        .where(rep.ip_agency.is_not(None))
        .group_by(rep.ip_agency)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=name, count=n) for name, n in rows]


class AllFacets(BaseModel):
    """Every sidebar facet in one payload — see `facet_all`."""

    countries: list[CountBucket]
    nice_classes: list[CountBucket]
    applicants: list[CountBucket]
    ip_agencies: list[CountBucket]
    mark_categories: list[CountBucket]
    granted: list[CountBucket]


@router.get("/all", response_model=AllFacets)
async def facet_all(
    filters: dict = Depends(_filter_params),
    session: AsyncSession = Depends(get_session),
) -> AllFacets:
    """One request returning all six sidebar facets, replacing the ~6 the Search
    page fired in parallel. Computed SEQUENTIALLY on the request's session (an
    AsyncSession is not concurrency-safe) — which also avoids the self-contention
    that inflated each parallel call — with every sub-call hitting the per-facet
    TTL cache. Limits mirror the individual endpoints' frontend defaults.
    """
    return AllFacets(
        countries=await facet_countries(filters=filters, limit=20, session=session),
        nice_classes=await facet_nice_classes(filters=filters, limit=45, session=session),
        applicants=await facet_applicants(filters=filters, limit=8, session=session),
        ip_agencies=await facet_ip_agencies(filters=filters, limit=8, session=session),
        mark_categories=await facet_mark_categories(filters=filters, session=session),
        granted=await facet_granted(filters=filters, session=session),
    )
