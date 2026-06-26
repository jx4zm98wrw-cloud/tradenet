"""Mark embedding for the semantic feature store (Track 3b-1).

The ONLY module importing the embedding model. Mirrors api/_phash.py (the only
Pillow importer): the heavy dependency is lazy-loaded and cached here, off the
import path of the API routes and the pure tm_similarity engine — which read the
stored bytes, never the model. Produces an L2-normalised 768-dim LaBSE vector as
float32 bytes so a future cosine is a plain dot product.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

Encoder = Callable[[list[str]], "NDArray[np.float32]"]

_DIM = 768
_MODEL_NAME = "sentence-transformers/LaBSE"
_model = None  # cached SentenceTransformer singleton (lazy)


def _default_encoder(texts: list[str]) -> NDArray[np.float32]:
    """Lazy-load + cache LaBSE; encode to unit-norm float32 vectors."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer  # heavy; imported on first real use only

        _model = SentenceTransformer(_MODEL_NAME)
    return _model.encode(texts, normalize_embeddings=True, convert_to_numpy=True).astype(np.float32)


def compute_mark_embeddings(texts: list[str | None], *, encoder: Encoder | None = None) -> list[bytes | None]:
    """Batch variant of `compute_mark_embedding`: encode many marks in ONE call.

    Returns a list parallel to `texts`. Non-blank texts are gathered and encoded in
    a SINGLE encoder call (the real LaBSE already batches a list internally), then
    each result is L2-normalised and serialised exactly as the single path does;
    None/blank inputs map to None outputs (same rule as `compute_mark_embedding`).

    Numerically equivalent (not byte-identical) to calling `compute_mark_embedding`
    per text: CPU batched matmul accumulates float32 in a different order than
    batch-of-1, so a row can differ by ~1e-7 — irrelevant to the cosine the semantic
    axis computes. Throughput-only change; mark_embedding is numerically-stable, not
    byte-stable (the backfill may rewrite rows on re-run — encode cost is unchanged).
    """
    out: list[bytes | None] = [None] * len(texts)
    kept = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
    if not kept:
        return out
    enc = encoder or _default_encoder
    matrix = enc([t for _, t in kept])
    for slot, (i, _) in enumerate(kept):
        vec = np.asarray(matrix[slot], dtype=np.float32)
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec = (vec / norm).astype(np.float32)
        out[i] = vec.tobytes()
    return out


def compute_mark_embedding(text: str | None, *, encoder: Encoder | None = None) -> bytes | None:
    """Return the mark's L2-normalised 768-float32 embedding as bytes, or None.

    `text` is the resolved wordmark (`trademarks.mark_name`). None/blank → None
    (figurative marks with no transcribed name carry no embedding, like a no-logo
    mark carries no logo_phash). `encoder` is the DI seam: default loads the cached
    real LaBSE; tests pass a fake so no model is loaded. The output round-trips via
    `numpy.frombuffer(buf, dtype=numpy.float32)`.

    Thin wrapper over `compute_mark_embeddings([text])` so normalisation and
    serialisation live in one place; single-text behaviour is unchanged.
    """
    return compute_mark_embeddings([text], encoder=encoder)[0]
