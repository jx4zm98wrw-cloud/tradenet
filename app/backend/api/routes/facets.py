"""Faceted-count endpoints — same filter set as `/api/trademarks`, but each
endpoint excludes its own column from the WHERE so the user can see "if I
selected this value, how many results would I get" rather than zero.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import RecordType, Trademark, get_session
from ._filters import build_trademark_where
from .stats import NICE_LABELS, CountBucket

router = APIRouter(prefix="/api/v1/facets", tags=["facets"])


# Shared Query() filter signature — keep in sync with /api/trademarks search().
def _filter_params(
    q: str | None = Query(None),
    country: str | None = Query(None, min_length=2, max_length=2),
    nice_class: list[str] | None = Query(None),
    record_type: RecordType | None = None,
    applicant_type: str | None = Query(None),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    gazette_id: uuid.UUID | None = None,
    ip_agency: str | None = Query(None),
):
    return dict(
        q=q,
        country=country,
        nice_class=nice_class,
        record_type=record_type,
        applicant_type=applicant_type,
        year=year,
        month=month,
        gazette_id=gazette_id,
        ip_agency=ip_agency,
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
