"""Pure data contracts for the similarity engine — no ORM, no IO."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkFeatures:
    mark_text: str | None  # resolved name (mark_name ?? mark_sample); NEVER the applicant
    logo_phash: str | None  # 16-char hex pHash, precomputed; None = no usable logo
    nice_classes: list[str]  # same element type the routes pass from Trademark.nice_classes
    vienna_codes: list[str]
    logo_kind: str | None = None  # 'figurative' | 'wordmark' | None — specimen routing (Track 1)
    mark_embedding: bytes | None = None  # 768 L2-normalised float32 (Track 3b-1); None = no semantic signal


@dataclass(frozen=True)
class ScoreResult:
    composite: float
    verdict: str  # "Likely conflict" | "Possible conflict" | "Low risk"
    verdict_tone: str  # "stamp" | "warn" | "ok"
    phonetic: float
    visual: float
    semantic: float
    visual_confidence: str  # "phash" | "typographic" | "none"
    class_overlap: float
    vienna_overlap: float
