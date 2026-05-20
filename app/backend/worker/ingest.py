"""PDF ingest job — runs tm_extractor and bulk-inserts trademark rows."""
from __future__ import annotations
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import Gazette, GazetteStatus, GazetteType, Trademark
from api.settings import get_settings
from tm_extractor import ExtractorConfig, PDFProcessor

from .mapper import infer_record_type, section_to_trademark


logger = logging.getLogger("worker.ingest")


_FILENAME_RE = re.compile(r"^([ABab])_T(\d+)_(\d{4})", re.IGNORECASE)


def parse_filename_meta(filename: str) -> Tuple[GazetteType, Optional[int], Optional[int]]:
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
        batch: list[Trademark] = []
        row_count = 0
        BATCH_SIZE = 200
        # Pass gazette_type explicitly — the stored path is `<digest>_<orig>.pdf`,
        # so the filename's first letter is the digest, not A/B.
        for section in processor.extract_records(pdf_path, gazette_type=letter):
            rt = infer_record_type(letter, section)
            batch.append(section_to_trademark(gazette.id, rt, section))
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
        gazette.processed_at = datetime.now(timezone.utc)
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
