"""Trademark search routes."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import RecordType, Trademark, get_session
from ..schemas import TrademarkListOut, TrademarkOut
from ._filters import build_trademark_where, normalize_vienna_code

router = APIRouter(prefix="/api/v1/trademarks", tags=["trademarks"])


@router.get("", response_model=TrademarkListOut)
async def search(
    q: str | None = Query(
        None, description="Free-text — matches applicant name / mark sample / application number"
    ),
    country: str | None = Query(None, min_length=2, max_length=2),
    nice_class: list[str] | None = Query(
        None, description="One or more Nice classes; repeat param to combine"
    ),
    vienna_codes: list[str] | None = Query(
        None,
        description="One or more Vienna figurative codes (NN.NN or NN.NN.NN); "
        "leading zeros are stripped to match storage format",
    ),
    record_type: RecordType | None = None,
    applicant_type: str | None = Query(None, description="Personal | Company"),
    year: int | None = None,
    month: int | None = Query(None, ge=1, le=12),
    gazette_id: uuid.UUID | None = None,
    ip_agency: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> TrademarkListOut:
    norm_vienna: list[str] | None = None
    if vienna_codes:
        norm_vienna = [c for c in (normalize_vienna_code(v) for v in vienna_codes) if c]
    where = build_trademark_where(
        q=q,
        country=country,
        nice_class=nice_class,
        vienna_codes=norm_vienna,
        record_type=record_type,
        applicant_type=applicant_type,
        year=year,
        month=month,
        gazette_id=gazette_id,
        ip_agency=ip_agency,
    )

    base = select(Trademark)
    cnt = select(func.count()).select_from(Trademark)
    if where:
        base = base.where(and_(*where))
        cnt = cnt.where(and_(*where))
    base = (
        base.order_by(Trademark.publication_date_441.desc().nulls_last(), Trademark.id)
        .limit(limit)
        .offset(offset)
    )

    rows = (await session.execute(base)).scalars().all()
    total = (await session.execute(cnt)).scalar_one()
    return TrademarkListOut(
        items=[TrademarkOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{trademark_id}", response_model=TrademarkOut)
async def get_trademark(
    trademark_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> TrademarkOut:
    r = await session.get(Trademark, trademark_id)
    if r is None:
        raise HTTPException(404, "Trademark not found")
    return TrademarkOut.model_validate(r)
