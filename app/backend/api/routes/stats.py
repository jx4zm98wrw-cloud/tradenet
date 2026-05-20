"""Aggregation endpoints for the dashboard and facet counts."""
from __future__ import annotations
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, desc, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Gazette, GazetteStatus, RecordType, Trademark, get_session


router = APIRouter(prefix="/api/stats", tags=["stats"])


class StatsOverview(BaseModel):
    total: int
    by_record_type: dict[str, int]
    gazettes_total: int
    gazettes_completed: int
    gazettes_in_flight: int


@router.get("/overview", response_model=StatsOverview)
async def overview(session: AsyncSession = Depends(get_session)) -> StatsOverview:
    total = (await session.execute(select(func.count()).select_from(Trademark))).scalar_one()
    by_type_rows = (await session.execute(
        select(Trademark.record_type, func.count()).group_by(Trademark.record_type)
    )).all()
    by_type = {rt.value: n for rt, n in by_type_rows}
    g_total = (await session.execute(select(func.count()).select_from(Gazette))).scalar_one()
    g_done = (await session.execute(
        select(func.count()).select_from(Gazette).where(Gazette.status == GazetteStatus.completed)
    )).scalar_one()
    g_inflight = (await session.execute(
        select(func.count()).select_from(Gazette).where(
            Gazette.status.in_([GazetteStatus.uploaded, GazetteStatus.processing])
        )
    )).scalar_one()
    return StatsOverview(
        total=total, by_record_type=by_type,
        gazettes_total=g_total, gazettes_completed=g_done, gazettes_in_flight=g_inflight,
    )


class CountBucket(BaseModel):
    key: str
    label: Optional[str] = None
    count: int


@router.get("/countries", response_model=List[CountBucket])
async def by_country(limit: int = 10, session: AsyncSession = Depends(get_session)) -> List[CountBucket]:
    rows = (await session.execute(
        select(Trademark.applicant_country_code, func.count())
            .where(Trademark.applicant_country_code.is_not(None))
            .group_by(Trademark.applicant_country_code)
            .order_by(desc(func.count()))
            .limit(limit)
    )).all()
    return [CountBucket(key=k, count=n) for k, n in rows]


@router.get("/nice-classes", response_model=List[CountBucket])
async def by_nice_class(limit: int = 12, session: AsyncSession = Depends(get_session)) -> List[CountBucket]:
    # unnest nice_classes[] and count per class
    sql = text("""
        SELECT cls, count(*) AS n
          FROM (SELECT unnest(nice_classes) AS cls FROM trademarks WHERE nice_classes IS NOT NULL) t
         GROUP BY cls ORDER BY n DESC LIMIT :lim
    """)
    rows = (await session.execute(sql, {"lim": limit})).all()
    return [CountBucket(key=cls, label=NICE_LABELS.get(cls, ""), count=n) for cls, n in rows]


@router.get("/top-applicants", response_model=List[CountBucket])
async def top_applicants(limit: int = 10, session: AsyncSession = Depends(get_session)) -> List[CountBucket]:
    rows = (await session.execute(
        select(Trademark.applicant_name, func.count())
            .where(Trademark.applicant_name.is_not(None))
            .group_by(Trademark.applicant_name)
            .order_by(desc(func.count()))
            .limit(limit)
    )).all()
    return [CountBucket(key=k, count=n) for k, n in rows]


@router.get("/top-agents", response_model=List[CountBucket])
async def top_agents(limit: int = 10, session: AsyncSession = Depends(get_session)) -> List[CountBucket]:
    rows = (await session.execute(
        select(Trademark.ip_agency, func.count())
            .where(Trademark.ip_agency.is_not(None))
            .group_by(Trademark.ip_agency)
            .order_by(desc(func.count()))
            .limit(limit)
    )).all()
    return [CountBucket(key=k, count=n) for k, n in rows]


# Nice class labels (short, common-knowledge) — used to add context next to numeric class IDs.
# Not authoritative; a real product would import from WIPO's official Nice taxonomy.
NICE_LABELS: dict[str, str] = {
    "01": "Chemicals", "02": "Paints", "03": "Cosmetics & cleaning", "04": "Fuels",
    "05": "Pharmaceuticals", "06": "Metal goods", "07": "Machines", "08": "Hand tools",
    "09": "Software & electronics", "10": "Medical apparatus", "11": "Lighting & heating",
    "12": "Vehicles", "13": "Firearms", "14": "Jewelry", "15": "Musical instruments",
    "16": "Paper goods & printing", "17": "Rubber & plastics", "18": "Leather goods",
    "19": "Building materials", "20": "Furniture", "21": "Household utensils",
    "22": "Ropes & textiles", "23": "Yarns", "24": "Fabrics", "25": "Clothing & footwear",
    "26": "Lace & embroidery", "27": "Carpets", "28": "Toys & sporting goods",
    "29": "Meat, dairy, processed food", "30": "Coffee, foodstuffs", "31": "Agricultural products",
    "32": "Non-alcoholic beverages", "33": "Alcoholic beverages", "34": "Tobacco",
    "35": "Services & advertising", "36": "Insurance & finance", "37": "Construction & repair",
    "38": "Telecommunications", "39": "Transport & storage", "40": "Materials treatment",
    "41": "Education & entertainment", "42": "Scientific services", "43": "Food & lodging services",
    "44": "Medical services", "45": "Legal & security services",
}
