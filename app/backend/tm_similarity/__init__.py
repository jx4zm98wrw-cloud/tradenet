"""tm_similarity — standalone trademark conflict-similarity engine.

Pure: depends only on stdlib + jellyfish. Features in, ScoreResult out.
"""

from __future__ import annotations

from .classes import class_overlap, vienna_overlap
from .composite import DEFAULT_WEIGHTS, CompositeScore, composite_score, resolve_weights
from .features import MarkFeatures, ScoreResult
from .phonetic import normalize_vn, phonetic_similarity
from .vn_phonetic import is_vietnamese, vn_phonetic_key
from .visual import VisualConfidence, VisualScore, visual_similarity

SIMILARITY_VERSION = "1.2"

__all__ = [
    "DEFAULT_WEIGHTS",
    "SIMILARITY_VERSION",
    "CompositeScore",
    "MarkFeatures",
    "ScoreResult",
    "VisualConfidence",
    "VisualScore",
    "class_overlap",
    "composite_score",
    "is_vietnamese",
    "normalize_vn",
    "phonetic_similarity",
    "resolve_weights",
    "score",
    "vienna_overlap",
    "visual_similarity",
    "vn_phonetic_key",
]


def score(a: MarkFeatures, b: MarkFeatures, *, weights: dict[str, float] | None = None) -> ScoreResult:
    """Score one pair of marks across all axes; assemble the full ScoreResult."""
    phon = phonetic_similarity(a.mark_text, b.mark_text)
    vis = visual_similarity(a.logo_phash, b.logo_phash, a.logo_kind, b.logo_kind, a.mark_text, b.mark_text)
    class_o = class_overlap(a.nice_classes, b.nice_classes)
    vienna_o = vienna_overlap(a.vienna_codes, b.vienna_codes)
    cs = composite_score(
        phon, vis.score, class_o, vienna_o, weights=weights, visual_confidence=vis.confidence
    )
    return ScoreResult(
        composite=cs.composite,
        verdict=cs.verdict,
        verdict_tone=cs.verdict_tone,
        phonetic=phon,
        visual=vis.score,
        visual_confidence=vis.confidence,
        class_overlap=class_o,
        vienna_overlap=vienna_o,
    )
