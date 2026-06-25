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
