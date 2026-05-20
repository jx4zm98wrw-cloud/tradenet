"""Scored search — extends /api/trademarks with a similarity score per result.

Until the real similarity engine (phonetic Metaphone+Levenshtein / visual pHash /
semantic NLP) ships, scores are derived from how strongly the text mode matches:
exact substring → 0.95, prefix3 → 0.82, anywhere else within the result set → 0.6
plus a deterministic per-id jitter so the column stays stable across reloads.
"""
from __future__ import annotations
import hashlib
import uuid
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import RecordType, Trademark, get_session
from ..schemas import TrademarkOut
from ._filters import build_trademark_where


router = APIRouter(prefix="/api/search", tags=["search"])

SearchMode = Literal["text", "phonetic", "image", "vienna"]


class ScoredMark(BaseModel):
    mark: TrademarkOut
    score: float


class SearchResultsOut(BaseModel):
    items: List[ScoredMark]
    total: int
    limit: int
    offset: int


def _jitter(seed: str, lo: float = -0.04, hi: float = 0.04) -> float:
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    return lo + (hi - lo) * (h % 1000) / 1000.0


def _score(mark: Trademark, q: Optional[str], mode: SearchMode) -> float:
    """Mocked similarity score in [0, 1]. Swap this function for a real engine."""
    base = 0.6
    if mode == "image":
        base = 0.78  # all results "match" the uploaded image at varying strength
    elif mode == "vienna":
        base = 0.74
    elif q:
        ql = q.lower()
        bag = " ".join(
            (mark.mark_sample or ""),
        ).lower() + " " + (mark.applicant_name or "").lower()
        if (mark.mark_sample or "").lower() == ql:
            base = 0.98
        elif ql in (mark.mark_sample or "").lower():
            base = 0.92
        elif ql in bag:
            base = 0.78
        elif (mark.mark_sample or "")[:3].lower() == ql[:3]:
            base = 0.76
    s = base + _jitter(str(mark.id))
    return round(max(0.0, min(0.999, s)), 2)


@router.get("/trademarks", response_model=SearchResultsOut)
async def search_trademarks(
    q: Optional[str] = Query(None),
    mode: SearchMode = Query("text"),
    threshold: float = Query(0.4, ge=0, le=1, description="Minimum similarity"),
    country: Optional[str] = Query(None, min_length=2, max_length=2),
    nice_class: Optional[List[str]] = Query(None),
    nice_class_mode: Literal["any", "all"] = Query("any"),
    record_type: Optional[RecordType] = None,
    applicant_type: Optional[str] = Query(None),
    year: Optional[int] = None,
    month: Optional[int] = Query(None, ge=1, le=12),
    gazette_id: Optional[uuid.UUID] = None,
    ip_agency: Optional[str] = Query(None),
    sort: Literal["similarity", "publication-desc", "applicant-asc", "class-count"] = "similarity",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> SearchResultsOut:
    # The shared WHERE builder uses ALL-class semantics (Trademark.nice_classes.contains([nc])).
    # For ANY semantics we run a separate where with array overlap.
    where = build_trademark_where(
        q=q, country=country,
        nice_class=nice_class if nice_class_mode == "all" else None,
        record_type=record_type, applicant_type=applicant_type,
        year=year, month=month, gazette_id=gazette_id, ip_agency=ip_agency,
    )
    if nice_class and nice_class_mode == "any":
        where.append(Trademark.nice_classes.op("&&")(nice_class))

    stmt = select(Trademark)
    cnt_stmt = select(func.count()).select_from(Trademark)
    if where:
        stmt = stmt.where(and_(*where))
        cnt_stmt = cnt_stmt.where(and_(*where))

    if sort == "publication-desc":
        stmt = stmt.order_by(Trademark.publication_date_441.desc().nulls_last(), Trademark.id)
    elif sort == "applicant-asc":
        stmt = stmt.order_by(Trademark.applicant_name.asc().nulls_last(), Trademark.id)
    elif sort == "class-count":
        stmt = stmt.order_by(func.cardinality(Trademark.nice_classes).desc().nulls_last(), Trademark.id)
    else:
        # similarity: fetch then sort in Python (mock scores).
        stmt = stmt.order_by(Trademark.publication_date_441.desc().nulls_last(), Trademark.id)

    # Over-fetch so we can post-filter by threshold without ruining pagination.
    fetch_limit = max(limit + offset, limit) * 2
    rows = list((await session.execute(stmt.limit(fetch_limit))).scalars().all())
    total = (await session.execute(cnt_stmt)).scalar_one()

    scored = [(m, _score(m, q, mode)) for m in rows]
    scored = [(m, s) for (m, s) in scored if s >= threshold]
    if sort == "similarity":
        scored.sort(key=lambda x: (-x[1], str(x[0].id)))

    page = scored[offset : offset + limit]
    return SearchResultsOut(
        items=[ScoredMark(mark=TrademarkOut.model_validate(m), score=s) for m, s in page],
        total=total,
        limit=limit,
        offset=offset,
    )
