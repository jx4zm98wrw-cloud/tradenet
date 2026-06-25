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


def compute_mark_embedding(text: str | None, *, encoder: Encoder | None = None) -> bytes | None:
    """Return the mark's L2-normalised 768-float32 embedding as bytes, or None.

    `text` is the resolved wordmark (`trademarks.mark_name`). None/blank → None
    (figurative marks with no transcribed name carry no embedding, like a no-logo
    mark carries no logo_phash). `encoder` is the DI seam: default loads the cached
    real LaBSE; tests pass a fake so no model is loaded. The output round-trips via
    `numpy.frombuffer(buf, dtype=numpy.float32)`.
    """
    if not text or not text.strip():
        return None
    enc = encoder or _default_encoder
    vec = np.asarray(enc([text])[0], dtype=np.float32)
    norm = float(np.linalg.norm(vec))
    if norm > 0.0:
        vec = (vec / norm).astype(np.float32)
    return vec.tobytes()
