"""api/_phash.compute_logo_phash returns a 16-hex string or None."""

from __future__ import annotations

from pathlib import Path

import imagehash
from PIL import Image

from api._phash import compute_logo_phash


def test_compute_returns_hex(tmp_path: Path):
    p = tmp_path / "logo.png"
    img = Image.new("L", (32, 32), 0)
    img.putpixel((4, 4), 255)
    img.save(p)
    got = compute_logo_phash(p)
    assert got == str(imagehash.phash(Image.open(p)))
    assert len(got) == 16


def test_missing_file_returns_none(tmp_path: Path):
    assert compute_logo_phash(tmp_path / "nope.png") is None


def test_corrupt_image_returns_none(tmp_path: Path):
    p = tmp_path / "corrupt.png"
    p.write_bytes(b"not a real PNG, just junk bytes")
    assert compute_logo_phash(p) is None
