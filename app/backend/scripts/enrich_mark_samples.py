"""Backfill `trademarks.mark_sample` from `tm_name_index`.

After a fresh PDF ingest (or after `scripts/load_tm_name_index.py` loads a
IP VIETNAM wordmark CSV), ~100% of `record_type='A'` rows in `trademarks` have
NULL/empty `mark_sample` — the PDF parser doesn't extract `(540)` cleanly
for application-side gazettes. The IP VIETNAM wordmark CSV closes that gap.

This script runs a single UPDATE that joins `trademarks` to `tm_name_index`
on `application_number` and copies `mark_sample` over wherever it's currently
missing. The reference table is **not** consumed — it stays around for the
next time new gazettes get ingested.

Idempotent + safe to re-run: the WHERE clause excludes rows that already
have a wordmark, so we never clobber existing data extracted from PDFs
(which is more reliable than the CSV for the few rows where extraction did
succeed).

Usage:

    cd app/backend
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \\
    python -m scripts.enrich_mark_samples --dry-run
    python -m scripts.enrich_mark_samples --execute
"""

from __future__ import annotations

import argparse
import sys

import psycopg2

from api.settings import get_settings


def _make_sync_dsn() -> str:
    raw = get_settings().database_url_sync
    return raw.replace("postgresql+psycopg2://", "postgresql://", 1)


def enrich(*, execute: bool) -> int:
    """Run the enrichment. Returns the number of rows updated (or that
    would be updated, in dry-run)."""
    conn = psycopg2.connect(_make_sync_dsn())
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            # Sanity: tm_name_index populated?
            cur.execute("SELECT COUNT(*) FROM tm_name_index")
            idx_count = cur.fetchone()[0]
            if idx_count == 0:
                print(
                    "ERROR: tm_name_index is empty. Run "
                    "`python -m scripts.load_tm_name_index --csv ... --execute` "
                    "first.",
                    file=sys.stderr,
                )
                return -1

            # Pre-count: how many trademarks rows currently need enrichment
            # AND have a match in tm_name_index. This is the upper bound on
            # what the UPDATE will touch.
            cur.execute(
                """
                SELECT COUNT(*)
                FROM trademarks t
                JOIN tm_name_index idx
                  ON t.application_number = idx.application_number
                WHERE t.application_number IS NOT NULL
                  AND t.application_number <> ''
                  AND (t.mark_sample IS NULL OR t.mark_sample = '')
                """
            )
            matched = cur.fetchone()[0]
            print(f"  tm_name_index has {idx_count:,} reference rows")
            print(f"  {matched:,} trademarks rows are missing mark_sample AND have a match")

            if not execute:
                conn.rollback()
                print(f"DRY-RUN: would update {matched:,} trademarks rows. Re-run with --execute to apply.")
                return matched

            # The real update. Single-statement SQL — Postgres runs the
            # join + index lookup + write in one shot, ~5s for 42k rows.
            cur.execute(
                """
                UPDATE trademarks t
                SET mark_sample = idx.mark_sample
                FROM tm_name_index idx
                WHERE t.application_number = idx.application_number
                  AND t.application_number IS NOT NULL
                  AND t.application_number <> ''
                  AND (t.mark_sample IS NULL OR t.mark_sample = '')
                """
            )
            updated = cur.rowcount
            conn.commit()
            print(f"OK: updated {updated:,} trademarks rows with wordmarks from tm_name_index")
            return updated
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually run the UPDATE. Without this flag we count-only and roll back.",
    )
    args = parser.parse_args(argv)
    result = enrich(execute=args.execute)
    return 0 if result >= 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
