"""Load NOIP wordmark CSV (TM_Name_A_*.csv) into `tm_name_index`.

The CSV is a NOIP-published flat extract of every Vietnam trademark
application's `(210) → (220) → (540)` triple from 2008 to present. We
load it into the dedicated `tm_name_index` reference table; downstream
enrichment (`scripts/enrich_mark_samples.py`) joins on
`application_number` to fill missing `mark_sample` values in
`trademarks`.

Why a custom loader (rather than `psql \\copy`):
  - CSV has a UTF-8 BOM that breaks `COPY ... FROM STDIN` without
    preprocessing.
  - Dates are `M/D/YY` (US-style), Postgres can't infer the century;
    we normalize to ISO before insert.
  - We want `ON CONFLICT (application_number) DO UPDATE` so the script
    is idempotent — re-running on a refreshed CSV updates wordmarks
    in place rather than failing.
  - 1 known in-file duplicate at time of writing — DO UPDATE handles
    it cleanly (last row wins, no human bookkeeping).

The loader streams rows in batches of 5_000 through `psycopg2.extras.execute_values`
to keep memory flat. End-to-end runtime on a 787k-row CSV is ~30-60s
depending on disk.

Usage (requires `pip install -e app/backend`):

    cd app/backend
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \\
    python -m scripts.load_tm_name_index --csv ../../TM_Name_A_2008-T4_2026.csv --dry-run
    python -m scripts.load_tm_name_index --csv ../../TM_Name_A_2008-T4_2026.csv --execute
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

from api.settings import get_settings

BATCH_SIZE = 5_000

# CSV column headers — first 3 columns; CSV may have trailing blank columns
# (it doesn't today, but defensive). Case-sensitive match against the BOM-
# stripped header row.
COL_APPNUM = "210 Application number"
COL_DATE = "220 Application submission date"
COL_MARK = "540 Trademark sample"


def _parse_us_date(raw: str) -> date | None:
    """Parse M/D/YY → date. Returns None on any error (log + skip)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    # `%y` (lowercase) interprets 2-digit years per Python's rule:
    # 00-68 → 2000-2068, 69-99 → 1969-1999. Real NOIP data only spans
    # 2003+ so we land in the right century.
    try:
        return datetime.strptime(raw, "%m/%d/%y").date()
    except ValueError:
        return None


def _make_sync_dsn() -> str:
    """Turn the SQLAlchemy URL into a libpq DSN for psycopg2.

    SQLAlchemy URL: postgresql+psycopg2://user:pass@host:port/db
    libpq DSN:      postgresql://user:pass@host:port/db
    """
    raw = get_settings().database_url_sync
    return raw.replace("postgresql+psycopg2://", "postgresql://", 1)


def load_csv(csv_path: Path, *, execute: bool) -> int:
    """Stream the CSV → tm_name_index. Returns the number of rows
    processed (== inserted-or-updated count when --execute, else the
    number that *would* be inserted)."""
    if not csv_path.exists():
        print(f"ERROR: csv not found: {csv_path}", file=sys.stderr)
        return -1

    conn = psycopg2.connect(_make_sync_dsn())
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            # utf-8-sig strips the leading BOM. Without this, the first
            # column header is `﻿210 Application number` and DictReader
            # never matches `COL_APPNUM`.
            with open(csv_path, encoding="utf-8-sig", newline="") as fh:
                reader = csv.DictReader(fh)
                if reader.fieldnames is None or COL_APPNUM not in reader.fieldnames:
                    print(
                        f"ERROR: csv missing expected header {COL_APPNUM!r}; got {reader.fieldnames!r}",
                        file=sys.stderr,
                    )
                    return -1

                batch: list[tuple[str, date | None, str]] = []
                total = 0
                skipped_no_appnum = 0
                skipped_no_mark = 0
                skipped_bad_date = 0

                for row in reader:
                    app_num = (row.get(COL_APPNUM) or "").strip()
                    mark = (row.get(COL_MARK) or "").strip()
                    date_raw = (row.get(COL_DATE) or "").strip()

                    if not app_num:
                        skipped_no_appnum += 1
                        continue
                    if not mark:
                        # `mark_sample TEXT NOT NULL` — can't insert.
                        # The user-visible CSV has 1 such row; log and skip.
                        skipped_no_mark += 1
                        continue

                    parsed = _parse_us_date(date_raw)
                    if date_raw and parsed is None:
                        skipped_bad_date += 1
                        # Keep the row anyway — submission_date is nullable.
                    batch.append((app_num, parsed, mark))

                    if len(batch) >= BATCH_SIZE:
                        if execute:
                            _flush(cur, batch)
                        total += len(batch)
                        batch.clear()
                        if total % 50_000 == 0:
                            print(f"  ...{total:,} rows", flush=True)

                # final partial batch
                if batch:
                    if execute:
                        _flush(cur, batch)
                    total += len(batch)

        if execute:
            conn.commit()
            print(
                f"OK: loaded {total:,} rows into tm_name_index "
                f"(skipped: {skipped_no_appnum} no-appnum, "
                f"{skipped_no_mark} no-mark, {skipped_bad_date} bad-date)"
            )
        else:
            conn.rollback()
            print(
                f"DRY-RUN: would load {total:,} rows "
                f"(skipped: {skipped_no_appnum} no-appnum, "
                f"{skipped_no_mark} no-mark, {skipped_bad_date} bad-date). "
                f"Run with --execute to apply."
            )
        return total
    finally:
        conn.close()


def _flush(cur, batch: list[tuple[str, date | None, str]]) -> None:
    """One bulk UPSERT for a batch.

    ON CONFLICT DO UPDATE makes the loader idempotent — re-running with
    an updated CSV refreshes mark_sample for existing app numbers
    instead of failing on the PK constraint.
    """
    execute_values(
        cur,
        """
        INSERT INTO tm_name_index (application_number, submission_date, mark_sample)
        VALUES %s
        ON CONFLICT (application_number) DO UPDATE
            SET submission_date = EXCLUDED.submission_date,
                mark_sample     = EXCLUDED.mark_sample
        """,
        batch,
        page_size=BATCH_SIZE,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv",
        type=Path,
        required=True,
        help="Path to TM_Name_A_*.csv",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually write to the DB. Without this flag we count-only and roll back.",
    )
    args = parser.parse_args(argv)
    result = load_csv(args.csv, execute=args.execute)
    return 0 if result >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
