"""Compare — side-by-side conflict scoring.

Two callers feed this: Search → multi-select → Compare N, and Detail → "Compare
in side-by-side". Until a real similarity engine exists, per-channel scores
(phonetic / visual / class-overlap) are mocked except for class overlap, which
is real Jaccard math. Composite weights are tunable per request.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Trademark, get_session
from ..schemas import TrademarkOut

router = APIRouter(prefix="/api/v1/compare", tags=["compare"])


DEFAULT_WEIGHTS = {"phonetic": 0.4, "visual": 0.3, "classOverlap": 0.3}


class CompareRequest(BaseModel):
    markIds: list[str] = Field(min_length=2, max_length=3)
    anchorId: str | None = None
    weights: dict[str, float] = Field(default_factory=lambda: DEFAULT_WEIGHTS.copy())


class PairScore(BaseModel):
    markId: str
    phonetic: float
    visual: float
    classOverlap: float
    composite: float
    verdict: str  # "Likely conflict" | "Possible conflict" | "Low risk"
    verdictTone: str  # "stamp" | "warn" | "ok"


class CompareResponse(BaseModel):
    anchorId: str
    marks: list[TrademarkOut]  # in input order
    scores: list[PairScore]  # one per non-anchor mark, in input order
    weights: dict[str, float]


@router.post("", response_model=CompareResponse)
async def compare(body: CompareRequest, session: AsyncSession = Depends(get_session)) -> CompareResponse:
    if len(body.markIds) < 2:
        raise HTTPException(400, "Need at least 2 marks to compare")
    if len(body.markIds) > 3:
        raise HTTPException(400, "Max 3 marks")
    weights = {**DEFAULT_WEIGHTS, **body.weights}
    total = sum(weights.values()) or 1
    weights = {k: v / total for k, v in weights.items()}

    rows = (await session.execute(select(Trademark).where(Trademark.id.in_(body.markIds)))).scalars().all()
    by_id = {str(m.id): m for m in rows}
    ordered = [by_id[mid] for mid in body.markIds if mid in by_id]
    if len(ordered) < 2:
        raise HTTPException(404, "Some mark IDs were not found")

    anchor_id = body.anchorId or body.markIds[0]
    anchor = by_id.get(anchor_id)
    if anchor is None:
        raise HTTPException(400, "anchorId must be one of markIds")

    scores: list[PairScore] = []
    for m in ordered:
        if str(m.id) == str(anchor.id):
            continue
        scores.append(_score_pair(anchor, m, weights))

    return CompareResponse(
        anchorId=str(anchor.id),
        marks=[TrademarkOut.model_validate(m) for m in ordered],
        scores=scores,
        weights=weights,
    )


def _score_pair(anchor: Trademark, other: Trademark, w: dict[str, float]) -> PairScore:
    # Class overlap = Jaccard over the anchor's classes (asymmetric — overlap
    # of OTHER classes against the anchor's full set).
    a_classes = set(anchor.nice_classes or [])
    o_classes = set(other.nice_classes or [])
    overlap = len(a_classes & o_classes)
    class_score = overlap / max(1, len(a_classes))

    # Phonetic: 0.88 when first 3 chars match (case-insensitive), 0.42 otherwise,
    # plus stable jitter.
    an = (anchor.mark_sample or anchor.applicant_name or "").lower()
    on = (other.mark_sample or other.applicant_name or "").lower()
    phon = 0.88 if an[:3] == on[:3] and an[:3] else 0.42

    # Visual: stable per-pair jitter in [0.5, 0.85].
    seed = f"{anchor.id}|{other.id}"
    h = int(hashlib.md5(seed.encode()).hexdigest()[:8], 16)
    visual = round(0.5 + (h % 350) / 1000.0, 2)

    composite = w["phonetic"] * phon + w["visual"] * visual + w["classOverlap"] * class_score

    if composite >= 0.75:
        verdict, tone = "Likely conflict", "stamp"
    elif composite >= 0.55:
        verdict, tone = "Possible conflict", "warn"
    else:
        verdict, tone = "Low risk", "ok"

    return PairScore(
        markId=str(other.id),
        phonetic=round(phon, 2),
        visual=round(visual, 2),
        classOverlap=round(class_score, 2),
        composite=round(composite, 2),
        verdict=verdict,
        verdictTone=tone,
    )


@router.post("/export.pdf", status_code=501)
async def export_pdf():
    """PDF report — design referenced; engine to come."""
    raise HTTPException(501, "Not implemented yet")
