"""Faceted-count endpoints — same filter set as `/api/trademarks`, but each
endpoint excludes its own column from the WHERE so the user can see "if I
selected this value, how many results would I get" rather than zero.
"""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import RecordType, Trademark, get_session
from ._filters import build_trademark_where
from .stats import CountBucket, NICE_LABELS


router = APIRouter(prefix="/api/facets", tags=["facets"])


# Shared Query() filter signature — keep in sync with /api/trademarks search().
def _filter_params(
    q: Optional[str] = Query(None),
    country: Optional[str] = Query(None, min_length=2, max_length=2),
    nice_class: Optional[List[str]] = Query(None),
    record_type: Optional[RecordType] = None,
    applicant_type: Optional[str] = Query(None),
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    gazette_id: Optional[uuid.UUID] = None,
    ip_agency: Optional[str] = Query(None),
):
    return dict(
        q=q, country=country, nice_class=nice_class, record_type=record_type,
        applicant_type=applicant_type, year=year, month=month,
        gazette_id=gazette_id, ip_agency=ip_agency,
    )


@router.get("/countries", response_model=List[CountBucket])
async def facet_countries(
    filters: dict = Depends(_filter_params),
    limit: int = Query(20, ge=1, le=300),
    session: AsyncSession = Depends(get_session),
) -> List[CountBucket]:
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


@router.get("/nice-classes", response_model=List[CountBucket])
async def facet_nice_classes(
    filters: dict = Depends(_filter_params),
    limit: int = Query(45, ge=1, le=45),
    session: AsyncSession = Depends(get_session),
) -> List[CountBucket]:
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
