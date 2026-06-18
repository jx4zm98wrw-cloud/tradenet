"""Faceted-count endpoints — same filter set as `/api/trademarks`, but each
endpoint excludes its own column from the WHERE so the user can see "if I
selected this value, how many results would I get" rather than zero.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import RecordType, Trademark, get_session
from ..db.models import MadridRecord
from ._filters import build_trademark_where
from .stats import NICE_LABELS, CountBucket

router = APIRouter(prefix="/api/v1/facets", tags=["facets"])


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
        grant_date_from=grant_date_from,
        grant_date_to=grant_date_to,
    )


@router.get("/countries", response_model=list[CountBucket])
async def facet_countries(
    filters: dict = Depends(_filter_params),
    limit: int = Query(20, ge=1, le=300),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    where = build_trademark_where(**filters, exclude="country")
    stmt = (
        select(Trademark.applicant_country_code, func.count())
        .where(Trademark.applicant_country_code.is_not(None))
        .group_by(Trademark.applicant_country_code)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    if where:
        stmt = stmt.where(and_(*where))
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=cc, count=n) for cc, n in rows]


@router.get("/nice-classes", response_model=list[CountBucket])
async def facet_nice_classes(
    filters: dict = Depends(_filter_params),
    limit: int = Query(45, ge=1, le=45),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Unnest `nice_classes[]` and count per class, applying all current filters
    EXCEPT the `nice_class` filter itself.
    """
    where = build_trademark_where(**filters, exclude="nice_class")
    cls_col = func.unnest(Trademark.nice_classes).label("cls")
    stmt = (
        select(cls_col, func.count())
        .where(Trademark.nice_classes.is_not(None))
        .group_by(cls_col)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    if where:
        stmt = stmt.where(and_(*where))
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=cls, label=NICE_LABELS.get(cls, ""), count=n) for cls, n in rows]


@router.get("/applicants", response_model=list[CountBucket])
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
    stmt = (
        select(Trademark.applicant_name, func.count())
        .where(Trademark.applicant_name.is_not(None))
        .group_by(Trademark.applicant_name)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    if where:
        stmt = stmt.where(and_(*where))
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
    stmt = (
        select(Trademark.mark_category, func.count())
        .group_by(Trademark.mark_category)
        .order_by(desc(func.count()))
    )
    if where:
        stmt = stmt.where(and_(*where))
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=cat, label=MARK_CATEGORY_LABELS.get(cat, cat), count=n) for cat, n in rows]


VN_STATUS_LABELS: dict[str, str] = {
    "granted": "Granted in VN",
    "pending": "Pending in VN",
    "refused": "Refused in VN",
}


@router.get("/vn-status", response_model=list[CountBucket])
async def facet_vn_status(
    filters: dict = Depends(_filter_params),
    session: AsyncSession = Depends(get_session),
) -> list[CountBucket]:
    """Count marks per VN protection status under the current filter set
    (excluding the vn_status filter itself), via the lineage_key join."""
    where = build_trademark_where(**filters, exclude="vn_status")
    stmt = (
        select(MadridRecord.vn_status, func.count())
        .join(Trademark, Trademark.lineage_key == MadridRecord.irn)
        .where(*where)
        .group_by(MadridRecord.vn_status)
    )
    rows = (await session.execute(stmt)).all()
    return [
        CountBucket(key=st, label=VN_STATUS_LABELS.get(st, st), count=n) for st, n in rows if st is not None
    ]


@router.get("/ip-agencies", response_model=list[CountBucket])
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
    stmt = (
        select(Trademark.ip_agency, func.count())
        .where(Trademark.ip_agency.is_not(None))
        .group_by(Trademark.ip_agency)
        .order_by(desc(func.count()))
        .limit(limit)
    )
    if where:
        stmt = stmt.where(and_(*where))
    rows = (await session.execute(stmt)).all()
    return [CountBucket(key=name, count=n) for name, n in rows]
