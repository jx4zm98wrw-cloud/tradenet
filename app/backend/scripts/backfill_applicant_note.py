"""Backfill: strip leading IP VIETNAM processing-notes from stored applicant names.

Cleans the two RAW applicant columns in place using the shared
``api._applicant_note.strip_registry_note`` helper (the same one the ingest
worker and the domestic-enrichment upsert now apply going forward):

  * ``trademarks.applicant_name``          (gazette-extracted, feeds the mark
                                            header / search cards / TrademarkOut)
  * ``domestic_records.applicant_name``    (IP VIETNAM-enriched, feeds the
                                            mark-detail Domestic record panel)

Idempotent: only rows whose stripped value differs are updated, so re-running is
a no-op. The original text is preserved in ``trademarks.raw`` (the untouched
section dict), so this is reversible.

AFTER running with ``--apply``, re-run ``scripts.backfill_entity_clean`` to
re-derive ``applicant_clean`` / ``applicant_norm`` from the cleaned names (the
grouping key), so the same company stops fragmenting across a noted/un-noted
variant.

Dry-run by default (prints what WOULD change). Usage (from app/backend):
    python -m scripts.backfill_applicant_note              # preview
    python -m scripts.backfill_applicant_note --apply      # write
"""

from __future__ import annotations

import argparse
import os

import psycopg2

from api._applicant_note import strip_registry_note

# Only rows beginning with a parenthesis can carry a LEADING note — cheap prefilter
# so we never scan/rewrite the whole corpus.
_CANDIDATE_SQL = "SELECT {key}, applicant_name FROM {table} WHERE applicant_name LIKE '(%%' ORDER BY {key}"


def _dsn() -> str:
    raw = os.environ.get("TM_DATABASE_URL_SYNC", "postgresql+psycopg2://tm:tm@localhost:5435/tm")
    return raw.replace("postgresql+psycopg2://", "postgresql://")


def _backfill_table(conn, table: str, key: str, *, apply: bool, show: int) -> tuple[int, int]:
    """Return (candidates_scanned, rows_changed) for one table."""
    cur = conn.cursor()
    cur.execute(_CANDIDATE_SQL.format(table=table, key=key))
    rows = cur.fetchall()
    changes: list[tuple[object, str, str]] = []
    for key_val, name in rows:
        cleaned = strip_registry_note(name)
        if cleaned != name:
            changes.append((key_val, name, cleaned))

    print(f"\n== {table}: {len(rows)} candidates (start with '('), {len(changes)} to clean ==")
    for key_val, before, after in changes[:show]:
        print(f"  {key_val}\n    - {before!r}\n    + {after!r}")
    if len(changes) > show:
        print(f"  … and {len(changes) - show} more")

    if apply and changes:
        upd = conn.cursor()
        upd.executemany(
            f"UPDATE {table} SET applicant_name = %s WHERE {key} = %s",
            [(after, key_val) for key_val, _before, after in changes],
        )
    return len(rows), len(changes)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Strip IP VIETNAM processing-notes from applicant names")
    ap.add_argument("--apply", action="store_true", help="write changes (default: dry-run preview)")
    ap.add_argument("--show", type=int, default=20, help="max before/after rows to print per table")
    args = ap.parse_args(argv)

    conn = psycopg2.connect(_dsn())
    conn.set_session(readonly=not args.apply, autocommit=False)
    total_changed = 0
    for table, key in (("trademarks", "id"), ("domestic_records", "application_number")):
        _scanned, changed = _backfill_table(conn, table, key, apply=args.apply, show=args.show)
        total_changed += changed
    if args.apply:
        conn.commit()
        print(
            f"\nAPPLIED: {total_changed} rows cleaned. "
            f"Now re-run `python -m scripts.backfill_entity_clean` to re-derive applicant_clean/norm."
        )
    else:
        print(f"\nDRY-RUN: {total_changed} rows would change. Re-run with --apply to write.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
