"""Regression: small-raster logos must not be dropped by MIN_SLICE_PX.

The audit (Phase 1 reset) surfaced 3 A-file marks whose logos got dropped
by image_extractor because the source raster height was below 20 px:

  - LG CNS CO., LTD.  (A_T3 / 4-2026-02248)  raster 189x18
  - FINETODAY CO.     (A_T4 / 4-2026-02737)  raster 188x14
  - THÀNH TRUNG       (A_T4 / 4-2025-57685)  raster  68x18

The PDF DISPLAYS the image at a normal logo size (e.g. 131x35 points),
but the underlying raster is small and the previous code applied a
MIN_SLICE_PX = 20 filter to every (slice, image) pair regardless of
whether the rect mapped to one or many sections. For single-slice rects
(one section), the filter drops the whole image — a real logo is lost.

This test builds a synthetic 1-page PDF, places a single (210) marker
label and a small raster image (12 px tall) below it in the layout the
extractor's saver expects, runs `_save_page_images`, and asserts that
the PNG IS written. With the pre-fix code, the test fails (no PNG
emitted). With the fix it passes.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image

# Silence MuPDF stderr like the extractor does.
_devnull_fd = os.open(os.devnull, os.O_WRONLY)
_saved_stderr_fd = os.dup(2)
os.dup2(_devnull_fd, 2)
try:
    import fitz
finally:
    os.dup2(_saved_stderr_fd, 2)
    os.close(_saved_stderr_fd)
    os.close(_devnull_fd)


def _make_small_raster_pdf(path: Path, marker_text: str, raster_height_px: int) -> None:
    """Build a 1-page PDF with one (210) marker label and one image below it.

    The image's intrinsic raster is `raster_height_px` tall but it's
    placed in the PDF at a 35-pt-tall display rect — mimicking the
    real gazette pattern where logos are small rasters scaled up.
    """
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((90, 200), marker_text, fontsize=10)
    # Build a small 100 × raster_height_px PNG with a recognisable pattern.
    img = Image.new("RGB", (100, raster_height_px), (0, 0, 0))
    for x in range(100):
        for y in range(raster_height_px):
            img.putpixel((x, y), (255, 100, 50) if (x + y) % 2 == 0 else (50, 100, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    # Display the image at a normal logo size (131 × 35 pt) BELOW the label.
    page.insert_image(fitz.Rect(120, 220, 251, 255), stream=buf.getvalue())
    doc.save(str(path))
    doc.close()


def test_small_raster_single_slice_logo_is_saved(tmp_path: Path) -> None:
    """Real bug: A_T4 row 4-2025-57685 had raster 68x18 dropped by the
    MIN_SLICE_PX=20 filter. Single-slice cases (one rect → one section)
    must always emit, regardless of raster size."""
    from image_extractor.extractor import PDFProcessor, ProcessingPaths

    pdf_path = tmp_path / "synthetic.pdf"
    _make_small_raster_pdf(pdf_path, "(210) 4-9999-TEST", raster_height_px=12)

    # Build the minimum config _save_page_images needs.
    config = {
        "image_settings": {"format": "PNG", "preserve_quality": True},
        "clustering": {"enabled": True, "cluster_threshold": 80, "combine_threshold": 80},
        "pdf_types": {
            "A": {
                "identifier": "A_",
                "text_pattern": r"\(\s*210\s*\)\s*([0-9][0-9A-Za-z\-]+)",
                "image_name_pattern": r"\(\s*210\s*\)\s*([0-9][0-9A-Za-z\-]+)",
            }
        },
    }

    paths = ProcessingPaths.create_default(str(tmp_path))
    paths.ensure_directories_exist()
    proc = PDFProcessor(paths, config)

    out_dir = tmp_path / "out"
    out_dir.mkdir()

    # Single label, single image — the bug case.
    doc = fitz.open(str(pdf_path))
    page = doc[0]
    # Match the label list shape the extractor builds: (y, identifier).
    labels = [(200.0, "4-9999-TEST")]
    proc._save_page_images(page, labels, out_dir, page_num=0, image_format="PNG", max_size=None)
    doc.close()

    expected = out_dir / "4-9999-TEST.png"
    assert expected.is_file(), (
        f"Small-raster single-slice logo was dropped — MIN_SLICE_PX regression. "
        f"PNG not at {expected}. Files in out_dir: {list(out_dir.iterdir())}"
    )
    # Sanity: PNG is non-empty and readable.
    assert expected.stat().st_size > 100
    Image.open(expected).verify()


def test_multi_slice_thin_sliver_still_dropped(tmp_path: Path) -> None:
    """The MIN_SLICE_PX guard's original purpose (drop thin slivers when a
    rect spans multiple labels) MUST be preserved. Build a tall image
    that gets sliced into one normal piece + one tiny sliver, and verify
    the tiny sliver is still dropped while the normal piece is kept.
    """
    from image_extractor.extractor import PDFProcessor, ProcessingPaths

    pdf_path = tmp_path / "multi.pdf"
    # Build PDF with two labels, but place ONE image that spans both.
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((90, 200), "(210) 4-9999-AAAA", fontsize=10)
    # Second label JUST inside the bottom of the image rect — simulates the
    # "1-2 px sliver" case the guard is for.
    page.insert_text((90, 318), "(210) 4-9999-BBBB", fontsize=10)
    # One tall image spanning Y 220-320.
    img = Image.new("RGB", (100, 200), (255, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    page.insert_image(fitz.Rect(120, 220, 251, 320), stream=buf.getvalue())
    doc.save(str(pdf_path))
    doc.close()

    config = {
        "image_settings": {"format": "PNG", "preserve_quality": True},
        "clustering": {"enabled": True, "cluster_threshold": 80, "combine_threshold": 80},
        "pdf_types": {"A": {"identifier": "A_", "text_pattern": "", "image_name_pattern": ""}},
    }

    paths = ProcessingPaths.create_default(str(tmp_path))
    paths.ensure_directories_exist()
    proc = PDFProcessor(paths, config)
    out_dir = tmp_path / "out2"
    out_dir.mkdir()

    doc = fitz.open(str(pdf_path))
    page = doc[0]
    labels = [(200.0, "4-9999-AAAA"), (318.0, "4-9999-BBBB")]
    proc._save_page_images(page, labels, out_dir, page_num=0, image_format="PNG", max_size=None)
    doc.close()

    # AAAA gets the bulk of the image (Y 220-318 = 98 pt of a 100 pt rect)
    assert (out_dir / "4-9999-AAAA.png").is_file(), "main slice should be saved"
    # BBBB would get just 2 pt of the rect — a thin sliver. Dropped.
    bbbb = out_dir / "4-9999-BBBB.png"
    # The sliver is tiny — at raster (200 px tall * 2/100 = 4 px), well below
    # MIN_SLICE_PX (20). Should NOT be emitted.
    assert not bbbb.is_file(), (
        f"Thin sliver from multi-slice split should still be filtered by MIN_SLICE_PX, but {bbbb} was written"
    )
