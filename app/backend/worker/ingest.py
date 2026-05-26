"""PDF ingest job — runs tm_extractor and bulk-inserts trademark rows."""

from __future__ import annotations

import hashlib
import logging
import re
import string
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import Gazette, GazetteStatus, GazetteType, Trademark
from api.settings import get_settings
from tm_extractor import ExtractorConfig, PDFProcessor

from .mapper import infer_record_type, section_to_trademark

logger = logging.getLogger("worker.ingest")


_FILENAME_RE = re.compile(r"^([ABab])_T(\d+)_(\d{4})", re.IGNORECASE)


def parse_filename_meta(filename: str) -> tuple[GazetteType, int | None, int | None]:
    """Extract gazette_type / issue_number / issue_year from a NOIP filename.

    Example: "A_T3_2026.pdf" -> (GazetteType.A, 3, 2026)
    Falls back to type-only when the issue/year pattern doesn't match.
    """
    letter = filename[:1].upper() if filename else "A"
    gazette_type = GazetteType.B if letter == "B" else GazetteType.A
    m = _FILENAME_RE.match(filename)
    if m:
        return gazette_type, int(m.group(2)), int(m.group(3))
    return gazette_type, None, None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _sync_session() -> Session:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)()


def _run_image_extraction(
    pdf_path: Path,
    output_stem: str,
    year: int | None,
    gazette_type: GazetteType,
    data_dir: Path,
) -> Path | None:
    """Best-effort logo extraction. Returns the absolute path of the per-PDF
    image directory on success, None on failure. CSV ingest continues either
    way — rows just get logo_path=NULL when extraction failed.

    Logging policy (post-audit):
      - WARNING for known degrade-paths: missing config file, missing year,
        extractor module not importable.
      - ERROR (with exc_info) for unexpected failures: extractor crashed
        mid-PDF, unexpected import error. These indicate a real problem
        worth investigating; the row count of NULL logo_path values on the
        gazette is the operator's smoke signal.
    """
    if year is None:
        logger.warning("Gazette has no issue_year; skipping image extraction for %s", pdf_path.name)
        return None

    # Lazy import: pymupdf/PIL/pdfplumber are heavy and only needed during extraction,
    # not on worker boot. Keeping the import inside the function also lets
    # test_run_image_extraction.py inject a fake `image_extractor` module via
    # `monkeypatch.setitem(sys.modules, ...)` before this line runs.
    try:
        import yaml

        from image_extractor import ImageExtractor, ImagePaths
    except (ImportError, ModuleNotFoundError) as e:
        # Extractor package or yaml not installed — degrade to no-logo.
        logger.warning("Image extractor not importable: %s", e)
        return None
    except Exception:
        # Anything else (SyntaxError on a hand-edit, AttributeError on a
        # renamed symbol, third-party RuntimeError at module init) is a real
        # programming error masquerading as "extractor missing." Surface it
        # so the operator can see what broke.
        logger.exception("Unexpected error importing image extractor")
        return None

    cfg_path = data_dir / "config_image_extractor.yaml"
    if not cfg_path.exists():
        logger.warning("Missing %s; skipping image extraction", cfg_path)
        return None
    with cfg_path.open() as f:
        image_cfg = yaml.safe_load(f) or {}

    year_str = str(year)
    image_dir = data_dir / "image" / year_str / output_stem
    modified_dir = data_dir / "modified" / year_str / output_stem
    image_link_dir = data_dir / "image_link" / year_str
    for d in (image_dir, modified_dir, image_link_dir):
        d.mkdir(parents=True, exist_ok=True)

    # ProcessingPaths wants the working_dir + per-type roots; we bypass its
    # single-PDF wrapper to keep control over output directory names (which
    # would otherwise be derived from the digest-prefixed storage filename).
    image_paths = ImagePaths(
        working_dir=data_dir,
        input_dir=pdf_path.parent,
        image_dir=data_dir / "image" / year_str,
        modified_dir=data_dir / "modified" / year_str,
        image_link_dir=image_link_dir,
    )
    extractor = ImageExtractor(image_paths, image_cfg, processing_mode="auto")
    pdf_type = "B" if gazette_type == GazetteType.B else "A"

    try:
        modified_pdf = extractor._modify_pdf(pdf_path, modified_dir, pdf_type)
        extractor._extract_images(modified_pdf, image_dir, pdf_type)
        extractor._create_image_link_csv(output_stem, image_dir, image_link_dir, year_folder=None)
    except Exception:
        # The extractor crashed mid-PDF. Partial output may already be on disk
        # (some PNGs in image_dir, modified PDF half-written). Log at ERROR with
        # exc_info so an operator can correlate it with the resulting NULL
        # logo_path rows. CSV ingest still proceeds — see ingest_pdf's caller.
        logger.exception(
            "Image extraction failed mid-PDF for %s (partial output may be in %s)",
            pdf_path.name,
            image_dir,
        )
        return None

    extracted_pngs = sum(1 for _ in image_dir.glob("*.png"))
    logger.info(
        "Image extraction completed for %s (%s, %d PNGs)",
        pdf_path.name,
        image_dir,
        extracted_pngs,
    )
    return image_dir


# Identifier values come from the PDF text layer (extracted by the parser
# from raw bytes that a third party authored). An allowlist on this value
# stops a crafted PDF from poisoning trademarks.logo_path with a
# path-traversal string. Matches the extractor's own image_name_pattern
# in config_image_extractor.yaml: alphanumerics + dash.
_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9\-]+$")


def _resolve_logo_path(section: dict, image_subdir_rel: str, image_root: Path) -> str | None:
    """Look up the extracted PNG for this section. Tries (210) (A-file
    applications), (111) (B-file domestic VN registrations), and (116)
    (B-file Madrid international registrations) in that order. Returns the
    path relative to image_root (which is mounted at /static/image/), or
    None if no logo file exists.

    The standalone extractor names PNGs after whichever section-start
    marker it found first; for B-files that's `(111)` or `(116)`, not
    `(210)`, so omitting `(111)` here drops every domestic-only B row.

    Letter-suffix fallback (e.g. 0181946 → 0181946A.png) applies ONLY to
    (116) Madrid: WIPO publishes modifications/renewals of a base Madrid
    registration with A-Z suffixes. (210)/(111) numbers have a different
    structure (4-YYYY-NNNN / 7-digit certificate) and an `A` suffix on
    one of those would be an unrelated mark, not the same registration.
    """
    for marker in ("(210)", "(111)", "(116)"):
        v = section.get(marker)
        if not v:
            continue
        ident = str(v).strip()
        if not ident or not _ID_SAFE_RE.match(ident):
            continue
        # Exact name first.
        rel = f"{image_subdir_rel}/{ident}.png"
        if (image_root / rel).is_file():
            return rel
        # Madrid-only suffix variants.
        if marker == "(116)":
            for suf in string.ascii_uppercase:
                rel = f"{image_subdir_rel}/{ident}{suf}.png"
                if (image_root / rel).is_file():
                    return rel
    return None


def ingest_pdf(gazette_id: str) -> dict:
    """Run extraction for an existing `gazettes` row and write `trademarks` rows.

    Intended to be called as an RQ job. `gazette_id` is the UUID string of an
    already-persisted Gazette in status='uploaded'. Updates status as it runs.
    """
    settings = get_settings()
    session = _sync_session()
    try:
        gid = uuid.UUID(gazette_id)
        gazette = session.get(Gazette, gid)
        if gazette is None:
            raise ValueError(f"Gazette {gazette_id} not found")
        if gazette.status != GazetteStatus.uploaded:
            logger.warning("Gazette %s status=%s; skipping", gazette_id, gazette.status)
            return {"gazette_id": gazette_id, "status": gazette.status.value, "skipped": True}

        gazette.status = GazetteStatus.processing
        session.add(gazette)
        session.commit()

        pdf_path = Path(gazette.storage_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF missing on disk: {pdf_path}")

        cfg = ExtractorConfig(
            data_dir=settings.data_dir,
            input_dir=pdf_path.parent,
            output_dir=settings.upload_dir / "csv",  # unused by extract_records, but required
            log_dir=settings.upload_dir / "log",
        )
        cfg.ensure_dirs()
        processor = PDFProcessor(cfg)

        letter = "B" if gazette.gazette_type == GazetteType.B else "A"

        # Image extraction — best-effort, runs before the CSV loop so logos
        # are on disk when the mapper looks them up per-section. The output
        # subdir uses the original (un-digested) filename stem so it stays
        # human-readable and stable across re-ingests of the same PDF.
        output_stem = Path(gazette.filename).stem
        _run_image_extraction(
            pdf_path=pdf_path,
            output_stem=output_stem,
            year=gazette.issue_year,
            gazette_type=gazette.gazette_type,
            data_dir=settings.data_dir,
        )
        image_root = settings.data_dir / "image"
        image_subdir_rel = f"{gazette.issue_year}/{output_stem}" if gazette.issue_year else None

        batch: list[Trademark] = []
        row_count = 0
        BATCH_SIZE = 200
        # Pass gazette_type explicitly — the stored path is `<digest>_<orig>.pdf`,
        # so the filename's first letter is the digest, not A/B.
        for section in processor.extract_records(pdf_path, gazette_type=letter):
            rt = infer_record_type(letter, section)
            logo_path = (
                _resolve_logo_path(section, image_subdir_rel, image_root) if image_subdir_rel else None
            )
            batch.append(section_to_trademark(gazette.id, rt, section, logo_path=logo_path))
            if len(batch) >= BATCH_SIZE:
                session.add_all(batch)
                session.commit()
                row_count += len(batch)
                batch.clear()
        if batch:
            session.add_all(batch)
            session.commit()
            row_count += len(batch)

        gazette.status = GazetteStatus.completed
        gazette.row_count = row_count
        gazette.processed_at = datetime.now(UTC)
        gazette.error_message = None
        session.add(gazette)
        session.commit()

        logger.info("Ingested %s rows from %s", row_count, pdf_path.name)
        return {"gazette_id": gazette_id, "row_count": row_count, "status": "completed"}

    except Exception as e:
        logger.exception("Ingest failed for gazette %s", gazette_id)
        try:
            g = session.get(Gazette, uuid.UUID(gazette_id))
            if g is not None:
                g.status = GazetteStatus.failed
                g.error_message = str(e)[:4000]
                session.add(g)
                session.commit()
        except Exception:
            session.rollback()
        raise
    finally:
        session.close()
