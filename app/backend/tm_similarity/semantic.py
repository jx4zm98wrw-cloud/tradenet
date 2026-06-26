"""Semantic (meaning) similarity axis (Track 3b-2).

Pure stdlib. Reads two marks' stored LaBSE embeddings (bytea of 768
L2-normalised float32, written by Track 3b-1) and returns a floor-calibrated
cosine in [0, 1]. No numpy, no model — the engine consumes stored bytes only,
keeping tm_similarity at stdlib + jellyfish.
"""

from __future__ import annotations

import array

_DIM = 768

# Cosine floor. LaBSE cosine for unrelated short text sits well above 0, so map
# (cos - FLOOR) / (1 - FLOOR) clamped to [0, 1] (mirrors the visual axis's
# 1 - hd/T recalibration). Calibrated against real LaBSE — see the marked test
# in tests/test_semantic.py (TM_RUN_MODEL_TESTS=1).
SEMANTIC_FLOOR = 0.50


def _decode(buf: bytes | None) -> array.array | None:
    """Decode bytea into 768 float32, or None if missing/malformed."""
    if not buf:
        return None
    vec = array.array("f")
    try:
        vec.frombytes(buf)
    except ValueError:
        return None
    if len(vec) != _DIM:
        return None
    return vec


def semantic_similarity(a_embedding: bytes | None, b_embedding: bytes | None) -> float:
    """Floor-calibrated cosine of two stored mark embeddings, in [0, 1].

    Returns 0.0 when either embedding is missing or malformed (figurative or
    not-yet-backfilled marks contribute no semantic signal — permissive, like
    Track 1's NULL logo_kind). Both vectors were L2-normalised at write time
    (Track 3b-1), so cosine == dot product.
    """
    a = _decode(a_embedding)
    b = _decode(b_embedding)
    if a is None or b is None:
        return 0.0
    cos = sum(x * y for x, y in zip(a, b, strict=True))
    score = (cos - SEMANTIC_FLOOR) / (1.0 - SEMANTIC_FLOOR)
    return round(max(0.0, min(1.0, score)), 3)
