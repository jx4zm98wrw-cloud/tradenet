"""Compare — side-by-side conflict scoring.

Two callers feed this: Search → multi-select → Compare N, and Detail →
"Compare in side-by-side". Per-channel scores are computed by the real
similarity engine in `api.similarity`:

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

from .. import similarity as sim
from ..db import Trademark, get_session
from ..schemas import TrademarkOut
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/compare", tags=["compare"])


# Public default — the design README's 40/30/30 from a 3-signal model;
# adding vienna as a 4th signal redistributes to 40/25/20/15.
DEFAULT_WEIGHTS = {
    "phonetic": 0.40,
    "visual": 0.25,
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


class CompareResponse(BaseModel):
    anchorId: str
    marks: list[TrademarkOut]
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

    rows = (await session.execute(select(Trademark).where(Trademark.id.in_(body.markIds)))).scalars().all()
    by_id = {str(m.id): m for m in rows}
    ordered = [by_id[mid] for mid in body.markIds if mid in by_id]
    if len(ordered) < 2:
        raise HTTPException(404, "Some mark IDs were not found")

    anchor_id = body.anchorId or body.markIds[0]
    anchor = by_id.get(anchor_id)
    if anchor is None:
        raise HTTPException(400, "anchorId must be one of markIds")

    image_root = get_settings().data_dir / "image"

    scores: list[PairScore] = []
    for m in ordered:
        if str(m.id) == str(anchor.id):
            continue
        scores.append(_score_pair(anchor, m, weights, image_root))

    return CompareResponse(
        anchorId=str(anchor.id),
        marks=[TrademarkOut.model_validate(m) for m in ordered],
        scores=scores,
        weights=weights,
    )


def _score_pair(anchor: Trademark, other: Trademark, w: dict[str, float], image_root) -> PairScore:
    """Compute the four per-signal scores + composite + examiner verdict.

    Inputs are drawn from real columns:
      - mark_sample (fall back to applicant_name for unbranded rows)
      - nice_classes, vienna_codes
      - logo_path (used for pHash comparison when both marks have one)

    The composite + verdict apply conjunction guards: composite alone
    isn't enough — at least one of phonetic/visual must clear a minimum
    strength, AND class proximity must be non-trivial. See
    api.similarity.composite_score for the rationale.
    """
    # Text for the wordmark comparisons. Fall back to applicant_name only
    # when there's literally no other signal — most A-files lack
    # mark_sample but have applicants, and "ZOTT SE & CO. KG" vs
    # "FAPA VITAL AG" is still a meaningful name comparison.
    a_text = anchor.mark_sample or anchor.applicant_name
    o_text = other.mark_sample or other.applicant_name

    phon = sim.phonetic_similarity(a_text, o_text)
    vis = sim.visual_similarity(
        a_logo=anchor.logo_path,
        b_logo=other.logo_path,
        a_text=a_text,
        b_text=o_text,
        image_root=image_root,
    )
    class_o = sim.class_overlap(anchor.nice_classes, other.nice_classes)
    vienna_o = sim.vienna_overlap(anchor.vienna_codes, other.vienna_codes)

    # Map the per-signal weights dict (which uses our public field names)
    # to the keys composite_score expects.
    composite_w = {
        "phonetic": w["phonetic"],
        "visual": w["visual"],
        "class": w["classOverlap"],
        "vienna": w["viennaOverlap"],
    }
    cs = sim.composite_score(phon, vis.score, class_o, vienna_o, composite_w)

    return PairScore(
        markId=str(other.id),
        phonetic=round(phon, 3),
        visual=round(vis.score, 3),
        classOverlap=round(class_o, 3),
        viennaOverlap=round(vienna_o, 3),
        composite=cs.composite,
        verdict=cs.verdict,
        verdictTone=cs.verdict_tone,
        visualConfidence=vis.confidence,
    )


@router.post("/export.pdf", status_code=501)
async def export_pdf():
    """PDF report — design referenced; engine to come."""
    raise HTTPException(501, "Not implemented yet")
