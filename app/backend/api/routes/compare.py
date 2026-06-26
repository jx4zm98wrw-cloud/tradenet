"""Compare — side-by-side conflict scoring.

Two callers feed this: Search → multi-select → Compare N, and Detail →
"Compare in side-by-side". Per-channel scores are computed by the real
similarity engine in `tm_similarity`:

  - phonetic    — Jaro-Winkler on raw + Metaphone-encoded forms,
                  Vietnamese-diacritic-aware
  - visual      — pHash on extracted PNG specimens when both marks
                  have them; typographic JW fallback otherwise (a
                  `visualConfidence` flag distinguishes the two)
  - classOverlap — Jaccard on Nice classes (real, kept)
  - viennaOverlap — Jaccard on Vienna figurative codes (new — independent
                    visual-category signal)

Default composite weights: 40/25/20/15. Per-matter tuning supported via
the request's `weights` field — pharma cases typically up-weight phonetic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tm_similarity import MarkFeatures, resolve_weights, score

from .._status import derive_status
from ..db import Trademark, get_session
from ..db.models import DomesticRecord
from ..schemas import TrademarkOut
from .today import DEMO_TODAY

router = APIRouter(prefix="/api/v1/compare", tags=["compare"])


# Public default — phonetic-protective 5-axis split (Track 3b-2). The 4 public
# axes sum to 0.85; resolve_weights() injects the semantic axis at 0.15 (the
# engine default) at score time, so the effective engine weights match
# DEFAULT_WEIGHTS {phonetic .35, visual .15, semantic .15, class .20, vienna .15}.
DEFAULT_WEIGHTS = {
    "phonetic": 0.35,
    "visual": 0.15,
    "classOverlap": 0.20,
    "viennaOverlap": 0.15,
}


class CompareRequest(BaseModel):
    markIds: list[str] = Field(min_length=2, max_length=3)
    anchorId: str | None = None
    weights: dict[str, float] = Field(default_factory=lambda: DEFAULT_WEIGHTS.copy())


class PairScore(BaseModel):
    markId: str
    phonetic: float
    visual: float
    semantic: float
    classOverlap: float
    viennaOverlap: float
    composite: float
    verdict: str  # "Likely conflict" | "Possible conflict" | "Low risk"
    verdictTone: str  # "stamp" | "warn" | "ok"
    # 'phash' = real visual comparison via perceptual hash on extracted PNGs.
    # 'typographic' = fall-back string similarity on the wordmark text;
    # less authoritative — a trademark expert should inspect the actual
    # specimens to confirm.
    # 'none' = no visual signal available (neither logo nor wordmark text).
    visualConfidence: str = "none"


class CompareMarkOut(TrademarkOut):
    status_label: str
    status_tone: str  # "ok" | "warn" | "mute"


class CompareResponse(BaseModel):
    anchorId: str
    marks: list[CompareMarkOut]
    scores: list[PairScore]
    weights: dict[str, float]


@router.post("", response_model=CompareResponse)
async def compare(body: CompareRequest, session: AsyncSession = Depends(get_session)) -> CompareResponse:
    if len(body.markIds) < 2:
        raise HTTPException(400, "Need at least 2 marks to compare")
    if len(body.markIds) > 3:
        raise HTTPException(400, "Max 3 marks")

    # Merge in any client-provided weight overrides and normalise to 1.
    weights = {**DEFAULT_WEIGHTS, **body.weights}
    total = sum(weights.values()) or 1.0
    weights = {k: v / total for k, v in weights.items()}

    result = (
        await session.execute(
            select(Trademark, DomesticRecord.status_code)
            .outerjoin(
                DomesticRecord,
                Trademark.application_number == DomesticRecord.application_number,
            )
            .where(Trademark.id.in_(body.markIds))
        )
    ).all()
    by_id = {str(m.id): m for m, _ in result}
    status_by_id = {str(m.id): status_code for m, status_code in result}
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
        marks=[_mark_out(m, status_by_id.get(str(m.id))) for m in ordered],
        scores=scores,
        weights=weights,
    )


def _mark_out(m: Trademark, status_code: str | None) -> CompareMarkOut:
    label, tone = derive_status(status_code, m.vn_grant_date, m.expiry_date_141, today=DEMO_TODAY)
    return CompareMarkOut(
        **TrademarkOut.model_validate(m).model_dump(),
        status_label=label,
        status_tone=tone,
    )


def _score_pair(anchor: Trademark, other: Trademark, w: dict[str, float]) -> PairScore:
    """Compute the four per-signal scores + composite + examiner verdict.

    Inputs are drawn from real columns: mark_sample (fall back to
    applicant_name for unbranded rows), nice_classes, vienna_codes, and the
    precomputed logo_phash. See tm_similarity.composite_score for the
    conjunction-guard rationale.
    """
    a_text = anchor.mark_sample or anchor.applicant_name
    o_text = other.mark_sample or other.applicant_name

    # Map the per-signal weights dict (public field names) to the keys the
    # engine expects.
    composite_w = {
        "phonetic": w["phonetic"],
        "visual": w["visual"],
        "class": w["classOverlap"],
        "vienna": w["viennaOverlap"],
    }
    result = score(
        MarkFeatures(
            mark_text=a_text,
            logo_phash=anchor.logo_phash,
            nice_classes=anchor.nice_classes or [],
            vienna_codes=anchor.vienna_codes or [],
            logo_kind=anchor.logo_kind,
            mark_embedding=anchor.mark_embedding,
        ),
        MarkFeatures(
            mark_text=o_text,
            logo_phash=other.logo_phash,
            nice_classes=other.nice_classes or [],
            vienna_codes=other.vienna_codes or [],
            logo_kind=other.logo_kind,
            mark_embedding=other.mark_embedding,
        ),
        weights=resolve_weights(composite_w),
    )
    return PairScore(
        markId=str(other.id),
        phonetic=round(result.phonetic, 3),
        visual=round(result.visual, 3),
        semantic=round(result.semantic, 3),
        classOverlap=round(result.class_overlap, 3),
        viennaOverlap=round(result.vienna_overlap, 3),
        composite=result.composite,
        verdict=result.verdict,
        verdictTone=result.verdict_tone,
        visualConfidence=result.visual_confidence,
    )


@router.post("/export.pdf", status_code=501)
async def export_pdf():
    """PDF report — design referenced; engine to come."""
    raise HTTPException(501, "Not implemented yet")
