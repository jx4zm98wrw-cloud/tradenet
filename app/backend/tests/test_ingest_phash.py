"""Ingest sets logo_phash from the resolved logo PNG."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from worker.ingest import _phash_for_logo  # small helper added in Step 3


def test_phash_for_logo(tmp_path: Path):
    rel = "x/logo.png"
    (tmp_path / "x").mkdir()
    img = Image.new("L", (32, 32), 0)
    img.putpixel((7, 7), 255)
    img.save(tmp_path / rel)
    assert _phash_for_logo(tmp_path, rel) is not None
    assert _phash_for_logo(tmp_path, None) is None
