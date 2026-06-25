"""Track 1: specimen-type classifier (Vienna-primary, pixel backstop)."""

from __future__ import annotations

from PIL import Image, ImageDraw

from api._phash import _pixel_backstop, classify_logo_kind


def test_vienna_present_is_figurative_without_touching_image():
    # No file at this path — Vienna branch must short-circuit before any open().
    assert classify_logo_kind(["26.4.18"], None) == "figurative"


def test_no_vienna_no_image_is_none():
    assert classify_logo_kind([], None) is None


def test_wide_sparse_strip_is_wordmark(tmp_path):
    p = tmp_path / "strip.png"
    img = Image.new("L", (600, 80), 255)  # wide, short, white
    d = ImageDraw.Draw(img)
    d.text((10, 30), "ACME BRAND", fill=0)  # thin dark text → sparse ink
    img.save(p)
    assert _pixel_backstop(p) == "wordmark"


def test_square_dense_device_is_figurative(tmp_path):
    p = tmp_path / "device.png"
    img = Image.new("L", (200, 200), 255)
    d = ImageDraw.Draw(img)
    d.ellipse((20, 20, 180, 180), fill=0)  # big solid blob → dense ink, square
    img.save(p)
    assert _pixel_backstop(p) == "figurative"


def test_unreadable_image_fails_to_figurative(tmp_path):
    p = tmp_path / "broken.png"
    p.write_bytes(b"not a png")
    assert _pixel_backstop(p) == "figurative"


def test_classify_no_vienna_routes_to_backstop(tmp_path):
    p = tmp_path / "strip.png"
    img = Image.new("L", (600, 80), 255)
    ImageDraw.Draw(img).text((10, 30), "ACME BRAND", fill=0)
    img.save(p)
    assert classify_logo_kind([], p) == "wordmark"


def test_logo_kind_for_helper_none_path_is_none(tmp_path):
    from worker.ingest import _logo_kind_for

    assert _logo_kind_for([], tmp_path, None) is None


def test_logo_kind_for_helper_vienna_is_figurative(tmp_path):
    from worker.ingest import _logo_kind_for

    # Vienna present → 'figurative' without needing the file to exist.
    assert _logo_kind_for(["26.4"], tmp_path, "missing.png") == "figurative"
