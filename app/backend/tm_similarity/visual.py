"""Visual similarity from a PRECOMPUTED hex pHash (no filesystem, no Pillow).

Track 1 recalibrates the curve to 1 - HD/VISUAL_PHASH_THRESHOLD.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .phonetic import _token_jw, normalize_vn

VISUAL_PHASH_THRESHOLD = 10
"""Hamming distance at/after which two 64-bit pHashes score 0 visual.

Two *random* pHashes differ in ~32 of 64 bits, so the old `1 - hd/64` floored
unrelated images at 0.50. Calibrated to 10 (see
docs/superpowers/notes/2026-06-25-phash-hamming-calibration.md): only genuinely
close hashes score; everything past the unrelated baseline maps to 0."""


def _phash_score(hd: int) -> float:
    """Recalibrated Hamming→similarity: linear to VISUAL_PHASH_THRESHOLD, then 0."""
    return round(max(0.0, 1.0 - hd / VISUAL_PHASH_THRESHOLD), 3)


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
        return VisualScore(_phash_score(_hamming_hex(a_phash, b_phash)), "phash")
    na, nb = normalize_vn(a_text), normalize_vn(b_text)
    if na and nb:
        return VisualScore(round(_token_jw(na, nb), 3), "typographic")
    return VisualScore(0.0, "none")
