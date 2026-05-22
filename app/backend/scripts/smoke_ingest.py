"""Smoke test: insert a Gazette + run ingest synchronously on a chosen PDF.

Requires the backend to be installed editable (`cd app/backend && pip install -e .`).

Usage:
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \\
    python -m scripts.smoke_ingest /abs/path/to/A_T2_2026.pdf
"""
from __future__ import annotations
import sys
import uuid
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from api.db.models import Gazette, GazetteStatus, Trademark
from api.settings import get_settings
from worker.ingest import ingest_pdf, parse_filename_meta, sha256_file


def main(pdf_path: Path) -> None:
    if not pdf_path.exists():
        sys.exit(f"PDF not found: {pdf_path}")
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    digest = sha256_file(pdf_path)
    gazette_type, issue_num, issue_year = parse_filename_meta(pdf_path.name)

    with Session() as s:
        existing = s.execute(select(Gazette).where(Gazette.sha256 == digest)).scalar_one_or_none()
        if existing:
            # Wipe prior rows for a clean re-ingest in the smoke test.
            s.execute(Trademark.__table__.delete().where(Trademark.gazette_id == existing.id))
            existing.status = GazetteStatus.uploaded
            existing.row_count = 0
            existing.error_message = None
            existing.processed_at = None
            # Re-point storage_path to the PDF the user just handed us. The
            # original Gazette may have been ingested via the upload pipeline
            # (digest-prefixed temp file under upload_dir that's since been
            # cleaned up); for a smoke re-ingest we want the in-repo input/
            # copy.
            existing.storage_path = str(pdf_path.resolve())
            s.add(existing)
            s.commit()
            gid = existing.id
            print(f"Re-using existing gazette row id={gid}")
        else:
            g = Gazette(
                id=uuid.uuid4(),
                filename=pdf_path.name,
                sha256=digest,
                gazette_type=gazette_type,
                issue_year=issue_year,
                issue_number=issue_num,
                storage_path=str(pdf_path.resolve()),
                size_bytes=pdf_path.stat().st_size,
                status=GazetteStatus.uploaded,
            )
            s.add(g)
            s.commit()
            gid = g.id
            print(f"Inserted new gazette id={gid}")

    result = ingest_pdf(str(gid))
    print("Ingest result:", result)

    with Session() as s:
        row = s.get(Gazette, gid)
        print(
            f"Gazette status={row.status.value} row_count={row.row_count} "
            f"processed_at={row.processed_at} error={row.error_message!r}"
        )
        # Quick sanity query
        from sqlalchemy import func
        nice_5 = s.execute(
            select(func.count()).select_from(Trademark).where(
                Trademark.gazette_id == gid,
                Trademark.nice_classes.contains(["05"]),
            )
        ).scalar_one()
        country = s.execute(
            select(func.count()).select_from(Trademark).where(
                Trademark.gazette_id == gid,
                Trademark.applicant_country_code == "VN",
            )
        ).scalar_one()
        print(f"  rows with Nice class 05: {nice_5}")
        print(f"  rows with country=VN:    {country}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: smoke_ingest.py <pdf_path>")
    main(Path(sys.argv[1]).resolve())
