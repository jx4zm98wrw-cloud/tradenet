"""Ground-truth audit: per-section image presence in the source PDF vs DB logo_path.

For every page of every input PDF, this script:
  1. Reads the WIPO INID label positions (210/111/116) directly from the
     PDF text layer using the same regex the extractor uses.
  2. Reads every image XObject placement on the page via fitz.get_images.
  3. Maps each image to the nearest INID label above it (mirrors the
     extractor's _save_page_images mapping).
  4. Cross-references against the DB to flag rows where:
        - The PDF section has >=1 image XObject of meaningful size, AND
        - The DB row's logo_path IS NULL.
     These are the **true misses**: gazette has a logo, we didn't capture it.

Cases that look like misses but aren't:
  - The 7 documented NEITHER cases (TOTO, CARMEDA, ...) where the gazette
    page has no figurative content at all — these correctly show
    PDF-image-count=0 + logo_path=NULL.
  - Sections where the only "image" XObject is a decorative footer/border
    repeated on every page; filtered by minimum-size threshold (default 50px).

Output (stdout JSON + text summary):
  per-PDF: total sections / sections with PDF image / sections in DB with
           logo_path / **missed candidates** (PDF has image but DB doesn't).

Usage:
    cd app/backend
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    ../.venv/bin/python -m scripts.audit_logos /abs/path/to/input/*.pdf
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable

# Lazy fitz import (consistent with extractor) — silences MuPDF stderr noise.
_orig_stderr_fd = os.dup(2)
_devnull = os.open(os.devnull, os.O_WRONLY)
os.dup2(_devnull, 2)
try:
    import fitz  # type: ignore
finally:
    os.dup2(_orig_stderr_fd, 2)
    os.close(_orig_stderr_fd)
    os.close(_devnull)

from sqlalchemy import create_engine, select  # noqa: E402

from api.db.models import Gazette, Trademark  # noqa: E402
from api.settings import get_settings  # noqa: E402

# Same marker pattern the extractor uses: (210) <num> / (111) <num> / (116) <num>.
# Captures the first non-empty group as the identifier.
_LABEL_RE = re.compile(r"\((210|111|116)\)\s*([\d\-A-Z]+)")

# Filter out tiny decoration glyphs (page borders, watermarks). Override via
# `AUDIT_MIN_IMAGE_PX` env var to widen/narrow what counts as a "real" image —
# decoration usually <40px; figurative marks usually >=50px in both axes.
_MIN_IMAGE_SIZE_PX = int(os.environ.get("AUDIT_MIN_IMAGE_PX", "50"))


def _page_labels(page) -> list[tuple[float, str, str]]:
    """Return [(y_top, code, identifier), ...] sorted by y."""
    out: list[tuple[float, str, str]] = []
    text_dict = page.get_text("dict")
    for block in text_dict.get("blocks", []):
        if not isinstance(block, dict) or block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            if not isinstance(line, dict):
                continue
            line_text = " ".join(
                str(s.get("text", "")) for s in line.get("spans", []) if isinstance(s, dict)
            )
            for m in _LABEL_RE.finditer(line_text):
                code = m.group(1)
                ident = m.group(2).strip()
                y0 = line.get("bbox", [0, 0, 0, 0])[1]
                out.append((float(y0), code, ident))
    out.sort(key=lambda t: t[0])
    return out


def _page_image_placements(page) -> list[tuple[float, float, float, float, int]]:
    """Return [(x0, y0, x1, y1, xref), ...] for every image XObject placed on
    the page, filtered to images >= _MIN_IMAGE_SIZE_PX on the SHORTER side."""
    out: list[tuple[float, float, float, float, int]] = []
    for xref_info in page.get_images(full=True):
        xref = xref_info[0]
        # Get bounding boxes for every placement of this xref on the page.
        for rect in page.get_image_rects(xref):
            w = rect.x1 - rect.x0
            h = rect.y1 - rect.y0
            if min(w, h) < _MIN_IMAGE_SIZE_PX:
                continue
            out.append((rect.x0, rect.y0, rect.x1, rect.y1, xref))
    return out


def _scan_pdf(pdf_path: Path) -> dict:
    """Walk the PDF, return {identifier: image_count_from_pdf}.

    Each image placement is attributed to the nearest INID label whose Y
    is above the image's Y0 (same logic as the extractor's saver). Images
    above the first label on a page (typically page-header decoration)
    are dropped.
    """
    per_id: dict[str, int] = defaultdict(int)
    sections_seen: set[str] = set()

    with fitz.open(pdf_path) as doc:
        for page in doc:
            labels = _page_labels(page)
            for _, _, ident in labels:
                sections_seen.add(ident)
            if not labels:
                continue
            for x0, y0, x1, y1, _ in _page_image_placements(page):
                # Nearest label whose y is <= image y0.
                attributed: str | None = None
                for ly, _code, ident in labels:
                    if ly <= y0 + 5.0:  # 5px slack: marker sometimes slightly below image start
                        attributed = ident
                    else:
                        break
                if attributed is not None:
                    per_id[attributed] += 1

    return {"per_section_image_count": dict(per_id), "sections_in_pdf": sorted(sections_seen)}


def _db_logo_status(pdf_filename: str) -> dict[str, bool]:
    """Return {identifier: logo_path_is_not_null} for every trademark row in
    this PDF's gazette. identifier = application_number OR certificate_number
    OR madrid_number (per the extractor's saver lookup order)."""
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    with engine.connect() as conn:
        # `select(Gazette.id)` so the Core row's [0] is the UUID directly,
        # not a Row wrapping an ORM entity.
        gazette_id = conn.execute(
            select(Gazette.id).where(Gazette.filename == pdf_filename)
        ).scalar_one_or_none()
        if gazette_id is None:
            return {}
        rows = conn.execute(
            select(
                Trademark.application_number,
                Trademark.certificate_number,
                Trademark.madrid_number,
                Trademark.logo_path,
            ).where(Trademark.gazette_id == gazette_id)
        ).all()
    out: dict[str, bool] = {}
    for appno, certno, madrid, logo in rows:
        for ident in (appno, certno, madrid):
            if ident:
                out[str(ident)] = logo is not None
    return out


def audit(pdfs: Iterable[Path]) -> list[dict]:
    reports = []
    for pdf in pdfs:
        scan = _scan_pdf(pdf)
        per_id_imgs = scan["per_section_image_count"]
        db = _db_logo_status(pdf.name)
        # Misses: PDF section has >=1 image, DB row has no logo_path.
        misses: list[dict] = []
        sections_with_pdf_image = 0
        for ident, img_count in per_id_imgs.items():
            if img_count >= 1:
                sections_with_pdf_image += 1
                if db.get(ident) is False:
                    misses.append({"identifier": ident, "pdf_image_count": img_count})
        report = {
            "pdf": pdf.name,
            "sections_in_pdf": len(scan["sections_in_pdf"]),
            "sections_in_db": len(db),
            "sections_with_pdf_image": sections_with_pdf_image,
            "missed_candidates": misses,
            "miss_count": len(misses),
        }
        reports.append(report)
        print(
            f"{pdf.name}: sections={report['sections_in_pdf']} "
            f"with_pdf_image={sections_with_pdf_image} "
            f"miss_candidates={len(misses)}",
            file=sys.stderr,
        )
    return reports


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python -m scripts.audit_logos <pdf> [<pdf> ...]")
    pdfs = [Path(p).resolve() for p in sys.argv[1:]]
    for p in pdfs:
        if not p.is_file():
            sys.exit(f"Not a file: {p}")
    reports = audit(pdfs)
    print(json.dumps(reports, indent=2))


if __name__ == "__main__":
    main()
