"""compute_mark_embedding: shape, normalisation, None-handling (fake encoder)."""

from __future__ import annotations

import os

import numpy as np
import pytest

from api._embed import compute_mark_embedding, compute_mark_embeddings
from api.db import Trademark

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


def test_batch_matches_single_path_and_preserves_order():
    texts = ["APPLE", "TÁO", "RED BULL"]
    batch = compute_mark_embeddings(texts, encoder=_fake_encoder)
    singles = [compute_mark_embedding(t, encoder=_fake_encoder) for t in texts]
    assert batch == singles  # order preserved + byte-identical to the per-text path
    assert all(isinstance(b, bytes) and len(b) == _DIM * 4 for b in batch)


def test_batch_maps_none_and_blank_to_none_in_a_mixed_chunk():
    out = compute_mark_embeddings(["APPLE", None, "", "  ", "PEAR"], encoder=_fake_encoder)
    assert out[1] is None and out[2] is None and out[3] is None  # None / "" / whitespace
    assert out[0] == compute_mark_embedding("APPLE", encoder=_fake_encoder)
    assert out[4] == compute_mark_embedding("PEAR", encoder=_fake_encoder)


def test_batch_all_none_chunk_returns_all_none_without_encoding():
    def _exploding_encoder(texts: list[str]) -> np.ndarray:
        raise AssertionError("encoder must not be called for an all-blank chunk")

    assert compute_mark_embeddings([None, "", "   "], encoder=_exploding_encoder) == [None, None, None]
    assert compute_mark_embeddings([], encoder=_exploding_encoder) == []


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


@pytest.mark.skipif(
    os.environ.get("TM_RUN_MODEL_TESTS") != "1",
    reason="loads the 470MB LaBSE model; opt-in via TM_RUN_MODEL_TESTS=1",
)
def test_real_labse_batch_is_numerically_equivalent_to_single():
    # batch is NOT byte-identical to single: CPU batched matmul accumulates float32 in
    # a different order than batch-of-1 (non-associative FP), so a row differs by ~1e-7
    # depending on batch size — a property of batched BLAS that padding/config cannot
    # remove. The vectors are numerically equivalent (cosine identical to ~7 decimals),
    # which is all the semantic axis (cosine) needs. So mark_embedding is
    # numerically-stable, NOT byte-stable: the backfill's recompute-and-compare may
    # rewrite rows on re-run (the encode cost we optimised is unchanged — only DB writes).
    texts = ["APPLE", "TÁO QUÂN", "RED BULL"]  # includes a Vietnamese mark
    batch = compute_mark_embeddings(texts)
    singles = [compute_mark_embedding(t) for t in texts]
    for b, s in zip(batch, singles, strict=True):
        assert b is not None and s is not None
        vb = np.frombuffer(b, dtype=np.float32)
        vs = np.frombuffer(s, dtype=np.float32)
        assert np.allclose(vb, vs, atol=1e-5)


def test_trademark_has_mark_embedding_column():
    col = Trademark.__table__.c.mark_embedding
    assert col.nullable is True
