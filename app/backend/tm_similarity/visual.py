"""Visual similarity from a PRECOMPUTED hex pHash (no filesystem, no Pillow).

Track 0 keeps the exact 1 - HD/64 formula; recalibration is Track 1.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .phonetic import _token_jw, normalize_vn

VisualConfidence = Literal["phash", "typographic", "none"]


@dataclass(frozen=True)
class VisualScore:
    score: float
    confidence: VisualConfidence


def _hamming_hex(a: str, b: str) -> int:
    """Hamming distance between two 16-char hex pHashes (popcount of XOR)."""
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def visual_similarity(
    a_phash: str | None,
    b_phash: str | None,
    a_text: str | None,
    b_text: str | None,
) -> VisualScore:
    """pHash Hamming when both hashes exist; else typographic JW on the wordmark."""
    if a_phash and b_phash:
        hd = _hamming_hex(a_phash, b_phash)
        return VisualScore(round(max(0.0, 1.0 - hd / 64.0), 3), "phash")
    na, nb = normalize_vn(a_text), normalize_vn(b_text)
    if na and nb:
        return VisualScore(round(_token_jw(na, nb), 3), "typographic")
    return VisualScore(0.0, "none")
