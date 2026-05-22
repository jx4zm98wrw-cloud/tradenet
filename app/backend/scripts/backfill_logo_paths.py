"""Backfill trademarks.logo_path for gazettes ingested before the logo
integration shipped (b5b5abd / PR #1).

Looks at every Trademark with logo_path IS NULL, attempts to resolve a PNG
under image/<year>/<gazette_stem>/, sets logo_path to the relative path if
the file exists. Mirrors the resolution logic in worker.ingest._resolve_logo_path
but operates over already-parsed DB rows instead of in-flight section dicts.

Requires the backend installed editable (`cd app/backend && pip install -e .`).

Usage:
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \\
    python -m scripts.backfill_logo_paths             # all gazettes, all years
    python -m scripts.backfill_logo_paths --dry-run   # show counts, don't write
    python -m scripts.backfill_logo_paths --gazette A_T1_2026.pdf  # one file
"""

from __future__ import annotations

import argparse
import re
import string
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from api.db.models import Gazette, Trademark
from api.settings import get_settings

# Allowlist matches worker.ingest._ID_SAFE_RE. Stops a crafted PDF whose
# extracted (210)/(111)/(116) leaked path-traversal characters into the
# DB from poisoning the backfill's filesystem lookups.
_ID_SAFE_RE = re.compile(r"^[A-Za-z0-9\-]+$")


def _resolve(
    image_root: Path,
    year: int,
    stem: str,
    application_no: str | None,
    certificate_no: str | None,
    madrid_no: str | None,
) -> str | None:
    """Mirror of worker.ingest._resolve_logo_path, against DB columns.

    Tries (210) → (111) → (116). Suffix-variant fallback is restricted to
    `madrid_no` (matches the WIPO Madrid convention; A/B/C/D suffixes on a
    base registration denote modifications, not unrelated marks).
    """
    candidates = (
        (application_no, False),
        (certificate_no, False),
        (madrid_no, True),  # try A-Z suffix variants
    )
    for raw, try_suffix in candidates:
        if not raw:
            continue
        ident = raw.strip()
        if not ident or not _ID_SAFE_RE.match(ident):
            continue
        rel = f"{year}/{stem}/{ident}.png"
        if (image_root / rel).is_file():
            return rel
        if try_suffix:
            for suf in string.ascii_uppercase:
                rel = f"{year}/{stem}/{ident}{suf}.png"
                if (image_root / rel).is_file():
                    return rel
    return None


def backfill(dry_run: bool, gazette_filename: str | None) -> None:
    settings = get_settings()
    image_root = settings.data_dir / "image"
    if not image_root.is_dir():
        sys.exit(f"image root not found: {image_root}")

    engine = create_engine(settings.database_url_sync, future=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with Session() as s:
        q = select(Gazette).where(Gazette.issue_year.is_not(None))
        if gazette_filename:
            q = q.where(Gazette.filename == gazette_filename)
        gazettes = s.execute(q).scalars().all()

        if not gazettes:
            sys.exit(f"No matching gazettes found (filter: {gazette_filename or 'none'})")

        totals = Counter()
        for g in gazettes:
            stem = Path(g.filename).stem
            year = g.issue_year
            assert year is not None  # filtered above

            rows = (
                s.execute(
                    select(Trademark).where(Trademark.gazette_id == g.id, Trademark.logo_path.is_(None))
                )
                .scalars()
                .all()
            )

            updates = 0
            misses = 0
            for tm in rows:
                rel = _resolve(
                    image_root,
                    year,
                    stem,
                    tm.application_number,
                    tm.certificate_number,
                    tm.madrid_number,
                )
                if rel is None:
                    misses += 1
                    continue
                if not dry_run:
                    tm.logo_path = rel
                updates += 1

            totals["scanned"] += len(rows)
            totals["matched"] += updates
            totals["unmatched"] += misses
            print(f"  {g.filename:30s} scanned={len(rows):6d}  matched={updates:6d}  unmatched={misses:6d}")

        if not dry_run:
            s.commit()

        prefix = "[DRY RUN] " if dry_run else ""
        print(
            f"\n{prefix}Total scanned={totals['scanned']}  matched={totals['matched']}  unmatched={totals['unmatched']}"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="Show counts, don't write")
    ap.add_argument("--gazette", help="Limit to one gazette by filename (e.g., A_T1_2026.pdf)")
    args = ap.parse_args()
    backfill(dry_run=args.dry_run, gazette_filename=args.gazette)


if __name__ == "__main__":
    main()
