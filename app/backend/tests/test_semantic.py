"""semantic_similarity: stdlib cosine + floor mapping, None/length-safe."""

from __future__ import annotations

import array
import math
import os

import pytest

from tm_similarity.semantic import SEMANTIC_FLOOR, semantic_similarity

_DIM = 768


def _unit(pairs: list[tuple[int, float]]) -> bytes:
    """Build an L2-normalised 768-float32 byte vector from (index, value) pairs."""
    v = array.array("f", [0.0] * _DIM)
    for i, val in pairs:
        v[i] = val
    n = math.sqrt(sum(x * x for x in v))
    for i in range(_DIM):
        v[i] = v[i] / n
    return v.tobytes()


def test_identical_vectors_score_1():
    a = _unit([(0, 1.0)])
    assert semantic_similarity(a, a) == 1.0


def test_orthogonal_vectors_score_0():
    a = _unit([(0, 1.0)])
    b = _unit([(1, 1.0)])
    assert semantic_similarity(a, b) == 0.0  # cos 0 is below the floor


def test_above_floor_maps_linearly():
    # cos = 0.85 -> (0.85 - 0.50)/(1 - 0.50) = 0.70
    b2 = math.sqrt(1.0 - 0.85**2)
    a = _unit([(0, 1.0)])
    b = _unit([(0, 0.85), (1, b2)])
    assert semantic_similarity(a, b) == 0.7


def test_none_returns_zero():
    a = _unit([(0, 1.0)])
    assert semantic_similarity(None, a) == 0.0
    assert semantic_similarity(a, None) == 0.0
    assert semantic_similarity(None, None) == 0.0


def test_malformed_buffer_returns_zero():
    a = _unit([(0, 1.0)])
    assert semantic_similarity(a, b"\x00\x01\x02") == 0.0  # not 768 floats


def test_floor_default():
    assert SEMANTIC_FLOOR == 0.50


@pytest.mark.skipif(
    os.environ.get("TM_RUN_MODEL_TESTS") != "1",
    reason="loads the 470MB LaBSE model; opt-in via TM_RUN_MODEL_TESTS=1",
)
def test_floor_separates_translation_from_unrelated():
    # Validate (and if needed re-tune) SEMANTIC_FLOOR against real LaBSE:
    # translation equivalents map high, unrelated low.
    from api._embed import compute_mark_embedding

    def sem(a: str, b: str) -> float:
        return semantic_similarity(compute_mark_embedding(a), compute_mark_embedding(b))

    assert sem("APPLE", "TÁO") >= 0.5
    assert sem("RED BULL", "BÒ ĐỎ") >= 0.5
    assert sem("APPLE", "CHAIR") <= 0.15
    assert sem("NIKE", "TABLE") <= 0.15
