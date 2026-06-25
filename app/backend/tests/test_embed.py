"""compute_mark_embedding: shape, normalisation, None-handling (fake encoder)."""

from __future__ import annotations

import os

import numpy as np
import pytest

from api._embed import compute_mark_embedding

_DIM = 768


def _fake_encoder(texts: list[str]) -> np.ndarray:
    # Deterministic, NOT unit-norm (so the function's own L2-normalise is exercised).
    base = np.zeros((len(texts), _DIM), dtype=np.float32)
    for i, t in enumerate(texts):
        base[i, 0] = float(len(t))
        base[i, 1] = 3.0
    return base


def test_returns_768_float32_bytes():
    b = compute_mark_embedding("APPLE", encoder=_fake_encoder)
    assert isinstance(b, bytes)
    assert len(b) == _DIM * 4  # 768 float32


def test_round_trips_and_is_l2_normalised():
    b = compute_mark_embedding("APPLE", encoder=_fake_encoder)
    v = np.frombuffer(b, dtype=np.float32)
    assert v.shape == (_DIM,)
    assert abs(float(np.linalg.norm(v)) - 1.0) < 1e-5


def test_none_and_blank_return_none():
    assert compute_mark_embedding(None, encoder=_fake_encoder) is None
    assert compute_mark_embedding("", encoder=_fake_encoder) is None
    assert compute_mark_embedding("   ", encoder=_fake_encoder) is None


@pytest.mark.skipif(
    os.environ.get("TM_RUN_MODEL_TESTS") != "1",
    reason="loads the 470MB LaBSE model; opt-in via TM_RUN_MODEL_TESTS=1",
)
def test_real_labse_cross_lingual_ordering():
    # Translation equivalents must be closer than unrelated concepts.
    def cos(a: str, b: str) -> float:
        va = np.frombuffer(compute_mark_embedding(a), dtype=np.float32)
        vb = np.frombuffer(compute_mark_embedding(b), dtype=np.float32)
        return float(va @ vb)  # both unit-norm -> dot == cosine

    assert cos("APPLE", "TÁO") > cos("APPLE", "CHAIR")
    assert cos("RED BULL", "BÒ ĐỎ") > cos("RED BULL", "TABLE")
