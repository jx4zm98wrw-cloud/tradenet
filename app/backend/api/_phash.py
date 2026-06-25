"""Logo pHash indexer — the ONLY place Pillow/imagehash touch similarity.

Computes the perceptual hash the pure tm_similarity engine consumes. Kept out
of tm_similarity so that package stays dependency-light (stdlib + jellyfish).
"""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image


def compute_logo_phash(image_path: Path) -> str | None:
    """Return the 16-char hex pHash of the image, or None if unreadable."""
    try:
        with Image.open(image_path) as img:
            return str(imagehash.phash(img))
    except Exception:
        return None


# Specimen-routing thresholds (provisional; see calibration note). A wordmark
# strip is wide, short, and sparse — mostly white with a thin band of text.
_AR_MIN = 3.0  # width / height
_INK_MAX = 0.20  # fraction of dark (text) pixels
_DARK_CUTOFF = 128  # luminance below this counts as "ink"


def classify_logo_kind(vienna_codes: list[str], image_path: Path | None) -> str | None:
    """Specimen kind for visual-axis routing: 'figurative' | 'wordmark' | None.

    Vienna (531) codes mean the mark HAS a figurative element → 'figurative'
    (the cheap, dominant signal; no pixel I/O). With no Vienna codes we look at
    the PNG. No image at all → None (nothing to route).
    """
    if vienna_codes:
        return "figurative"
    if image_path is None:
        return None
    return _pixel_backstop(image_path)


def _pixel_backstop(image_path: Path) -> str:
    """Wide+short+sparse PNG → 'wordmark'; otherwise 'figurative'. Fail-soft.

    Unreadable/corrupt images return 'figurative' so a bad read never silently
    suppresses a real logo (matches compute_logo_phash's fail-soft posture)."""
    try:
        with Image.open(image_path) as im:
            g = im.convert("L")
            w, h = g.size
            if w == 0 or h == 0:
                return "figurative"
            aspect = w / h
            dark = sum(g.histogram()[:_DARK_CUTOFF])
            ink = dark / (w * h)
    except Exception:
        return "figurative"
    if aspect >= _AR_MIN and ink <= _INK_MAX:
        return "wordmark"
    return "figurative"
