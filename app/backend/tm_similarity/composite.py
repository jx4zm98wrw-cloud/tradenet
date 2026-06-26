from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .visual import VisualConfidence

DEFAULT_WEIGHTS = {"phonetic": 0.35, "visual": 0.15, "semantic": 0.15, "class": 0.20, "vienna": 0.15}
"""Phonetic-protective 5-axis split (Track 3b-2). Semantic's 0.15 is drawn
mostly from visual (0.25->0.15), keeping phonetic (0.40->0.35) close to prior
behaviour so phonetic-conflict recall is least disturbed. 0.65 mark / 0.35
goods ratio preserved. Per-matter tunable via resolve_weights."""


def resolve_weights(overrides: dict[str, float] | None) -> dict[str, float]:
    """Merge per-matter weight overrides over DEFAULT_WEIGHTS and renormalise to 1.

    The single source of truth for turning a stored/requested weights dict into
    the normalised weights `composite_score` expects. Shared by the per-matter
    surfaces (watchlist-scoped similar marks) and the /compare endpoint so they
    validate identically.

    - None / empty → DEFAULT_WEIGHTS (a fresh copy).
    - Only the five known keys (phonetic/visual/semantic/class/vienna) are
      honoured; unknown keys are ignored and missing keys inherit their default.
    - Non-numeric / negative values are dropped (fall back to the default for
      that key); a non-positive total falls back entirely to DEFAULT_WEIGHTS.
    """
    if not overrides:
        return dict(DEFAULT_WEIGHTS)
    merged = dict(DEFAULT_WEIGHTS)
    for k in DEFAULT_WEIGHTS:
        v = overrides.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0:
            merged[k] = float(v)
    total = sum(merged.values())
    if total <= 0:
        return dict(DEFAULT_WEIGHTS)
    return {k: v / total for k, v in merged.items()}


@dataclass(frozen=True)
class CompositeScore:
    composite: float
    verdict: Literal["Likely conflict", "Possible conflict", "Low risk"]
    verdict_tone: Literal["stamp", "warn", "ok"]


def composite_score(
    phonetic: float,
    visual: float,
    semantic: float,
    class_o: float,
    vienna_o: float,
    weights: dict[str, float] | None = None,
    visual_confidence: VisualConfidence = "phash",
) -> CompositeScore:
    """Composite conflict score + verdict across 5 axes.

    The composite is a sum of two contributions:
      - mark_score    = w_phon*phonetic + w_vis*visual + w_sem*semantic
                        (the sight / sound / meaning axis)
      - goods_score   = w_class*class_o + w_vienna*vienna_o
                        (the goods-relatedness axis)

    They are NOT simply added with full weight. Trademark confusion
    requires similar marks AND related goods, multiplicatively — Apple
    Records vs Apple Computer (1976) had identical marks but unrelated
    goods → zero confusion. The symmetric case must hold: same goods
    + clearly different marks → minimal conflict score.

    So `goods_score` is dampened by mark strength. With no real
    sight / sound / meaning signal the goods axis contributes ~0 (class
    overlap alone can't carry a "conflict score"). At mark_strength ≥ 0.7
    the goods axis contributes fully.

      composite = mark_score + goods_score * min(1, mark_strength / 0.7)

    `semantic` (cross-language / conceptual meaning) is independent
    evidence like a pHash visual match — a translation-equivalent pair
    (e.g. APPLE vs POMME) can be aurally and visually unrelated yet
    confusingly similar in meaning — so it enters `mark_strength` and
    lets the goods axis count. `mark_strength` therefore takes the max of
    the independent axes:
      - `'phash'` visual: max(phonetic, semantic, visual) — all independent.
      - `'typographic'` / `'none'`: max(phonetic, semantic) — typographic
        visual is JW on the same wordmark text the phonetic raw saw, not
        independent, so it does NOT enter mark_strength.

    Verdict bands (applied after the math above; UNCHANGED from the 4-axis
    version):
      Likely:   composite >= 0.70, mark_strength >= 0.70, class >= 0.30
      Possible: composite >= 0.50, mark_strength >= 0.50, class >= 0.20
      else:     Low risk

    Conjunction guards (the mark_strength + class_o clauses) remain
    because the dampener fixes the numeric composite but not the
    verdict on edge cases. A pair with mark_strength 0.49 and class
    overlap 1.0 might still produce a composite ~0.5 from the
    dampener; the guard pins it as Low risk for examiner-grade
    consistency.

    Why this matters in practice — OMBRES TENDRES vs MAYBELLINE SPOT
    RESCUE was scoring 0.447 because class overlap added its full
    0.20 weight even though the marks themselves are clearly
    different. The dampener reduces that to ~0.36 — still nonzero
    (the marks DO share class-3 cosmetics, and JW always returns
    some baseline overlap for similar-length strings), but no longer
    visually misleading.
    """
    w = weights or DEFAULT_WEIGHTS

    mark_score = w["phonetic"] * phonetic + w["visual"] * visual + w["semantic"] * semantic
    goods_score = w["class"] * class_o + w["vienna"] * vienna_o

    # Conjunction signal: phonetic + semantic are always independent evidence;
    # pHash visual is too, but typographic / none is just JW on the wordmark
    # text and shouldn't double-count.
    candidates = [phonetic, semantic]
    if visual_confidence == "phash":
        candidates.append(visual)
    mark_strength = max(candidates)

    # Goods-dampener ramp:
    #   mark_strength <= 0.30  → goods contribute 0 (Jaro-Winkler baseline
    #                            noise; no real mark similarity to amplify)
    #   0.30 < mark_strength < 0.70 → linear ramp 0 → 1
    #   mark_strength >= 0.70  → goods contribute fully
    #
    # The 0.30 floor matters: JW returns ~0.30–0.45 for *any* two
    # similar-length strings just from shared common letters
    # (OMBRES TENDRES vs MAYBELLINE SPOT RESCUE scores phonetic 0.38
    # purely from that effect). Without the floor, class overlap would
    # still inflate the composite even though the marks are clearly
    # different. The floor cuts JW noise out of the goods contribution.
    goods_factor = max(0.0, min(1.0, (mark_strength - 0.30) / 0.40))
    composite = round(mark_score + goods_score * goods_factor, 3)

    if composite >= 0.70 and mark_strength >= 0.70 and class_o >= 0.30:
        return CompositeScore(composite, "Likely conflict", "stamp")
    if composite >= 0.50 and mark_strength >= 0.50 and class_o >= 0.20:
        return CompositeScore(composite, "Possible conflict", "warn")
    return CompositeScore(composite, "Low risk", "ok")
