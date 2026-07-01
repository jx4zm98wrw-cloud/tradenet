"""Fill missing B-file registration dates from enrichment data.

`trademarks.registration_date_151` is a GAZETTE column (INID marker (151)). B-file
rows can lack it: a handful of domestic registrations miss the marker, and Madrid
(116) registrations never carry (151) at all. This fills the NULLs from the
trusted enrichment source, keyed by identifier:

  * B_domestic ← `domestic_records.grant_date`        (by application_number)
  * B_madrid   ← `madrid_records.registration_date`   (by lineage_key = irn)

Only fills NULLs — never overwrites a gazette-provided (151) — so it is
idempotent and safe to re-run.

CAVEAT: this MIXES enrichment provenance into a gazette column, and the ingest
worker rewrites `registration_date_151` from the PDF marker on ingest — so
**re-run this after any re-ingest of a B-file** (same "run after ingest" caveat as
the resolved-column backfills). It also means `scripts/audit_fields.py`'s
"B-domestic missing (151)" check will read ~0 once this has run.

Dry-run by default (prints what WOULD change). Usage (from app/backend):
    python -m scripts.fill_registration_date_from_enrichment            # preview
    python -m scripts.fill_registration_date_from_enrichment --apply    # write
"""

from __future__ import annotations

import argparse
import os

import psycopg2

# (record_type, enrichment table, date column, join predicate) for each source.
_SOURCES = (
    ("B_domestic", "domestic_records", "grant_date", "e.application_number = t.application_number"),
    ("B_madrid", "madrid_records", "registration_date", "e.irn = t.lineage_key"),
)


def _dsn() -> str:
    raw = os.environ.get("TM_DATABASE_URL_SYNC", "postgresql+psycopg2://tm:tm@localhost:5435/tm")
    return raw.replace("postgresql+psycopg2://", "postgresql://")


def _fillable(cur, record_type: str, table: str, col: str, join: str) -> int:
    """Count rows this source WOULD fill (NULL (151) with a non-null enrichment date)."""
    cur.execute(
        f"SELECT count(*) FROM trademarks t JOIN {table} e ON {join} "
        f"WHERE t.record_type = %s AND t.registration_date_151 IS NULL AND e.{col} IS NOT NULL",
        (record_type,),
    )
    return int(cur.fetchone()[0])


def _fill(cur, record_type: str, table: str, col: str, join: str) -> int:
    cur.execute(
        f"UPDATE trademarks t SET registration_date_151 = e.{col} "
        f"FROM {table} e WHERE {join} "
        f"AND t.record_type = %s AND t.registration_date_151 IS NULL AND e.{col} IS NOT NULL",
        (record_type,),
    )
    return cur.rowcount


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Fill missing B-file (151) registration dates from enrichment")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview)")
    args = ap.parse_args(argv)

    conn = psycopg2.connect(_dsn())
    conn.set_session(readonly=not args.apply, autocommit=False)
    cur = conn.cursor()

    cur.execute(
        "SELECT count(*) FROM trademarks "
        "WHERE record_type IN ('B_domestic','B_madrid') AND registration_date_151 IS NULL"
    )
    before = int(cur.fetchone()[0])

    total = 0
    for record_type, table, col, join in _SOURCES:
        n = (
            _fill(cur, record_type, table, col, join)
            if args.apply
            else _fillable(cur, record_type, table, col, join)
        )
        verb = "filled" if args.apply else "fillable"
        print(f"  {record_type:12s} {verb}={n:>7,}  (<- {table}.{col})")
        total += n

    if args.apply:
        conn.commit()
        cur.execute(
            "SELECT count(*) FROM trademarks "
            "WHERE record_type IN ('B_domestic','B_madrid') AND registration_date_151 IS NULL"
        )
        after = int(cur.fetchone()[0])
        print(
            f"APPLIED: {total:,} filled. Missing (151) on B rows: {before:,} -> {after:,} "
            f"(remaining have no enrichment date)."
        )
    else:
        print(f"DRY-RUN: {total:,} of {before:,} missing would be filled. Re-run with --apply to write.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
