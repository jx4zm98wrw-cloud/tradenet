"""Enrich `trademarks.mark_sample` from manually-corrected per-PDF CSVs.

The `csv/` directory at the project root holds one CSV per ingested
gazette PDF, in the same schema the `tm_extractor` pipeline produces.
After ingest these files were edited by hand to fill in the `(540)
Trademark sample` column that the PDF parser left empty for most rows.
This script propagates those manual corrections back into the
`trademarks` table.

Match strategy depends on the CSV's filename, because each gazette type
has a different identifier that survives the round-trip:

    csv/A_T<N>_2026.csv         → A applications, key = (210) application_number
    csv/B_T<N>_2026.csv         → B_domestic certificates, key = (111) certificate_number
    csv/B_T<N>_2026_madrid.csv  → B_madrid international regs, key = (116) madrid_number
                                  (CSV side has bare digits; DB side is zero-padded
                                   to 7 — we normalize on the CSV side at load time)

Behavior:
  - Overwrites `mark_sample` unconditionally where the CSV has a non-empty
    (540). The user's manual edits are treated as the truth — any value
    previously set by `enrich_mark_samples.py` (PR #48) for these
    gazette rows gets superseded.
  - Skips CSV rows where (540) is empty (preserves whatever was in the
    DB — typically NULL — so re-running after more manual edits is safe).
  - Skips CSV rows whose ID doesn't appear in trademarks (the CSV row
    might describe a gazette section that was filtered out during ingest;
    we don't try to insert new rows here, only enrich existing ones).
  - Runs all per-file updates in one transaction so a parser error
    aborts the whole pass cleanly.

Idempotent + re-runnable. When new gazette CSVs get manually filled
(e.g. A_T4_2026.csv currently at 0%), re-run this script and only the
new rows get touched.

Usage:

    cd app/backend
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \\
    python -m scripts.enrich_from_per_pdf_csvs                    # dry-run
    python -m scripts.enrich_from_per_pdf_csvs --execute          # apply
    python -m scripts.enrich_from_per_pdf_csvs --csv-dir /abs/path # override
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

from api.settings import get_settings

# Project-root-relative location of the per-PDF CSVs.
# This file lives at app/backend/scripts/, so two parents up is the repo root.
DEFAULT_CSV_DIR = Path(__file__).resolve().parents[3] / "csv"

# CSV column header — same as the extractor emits.
COL_540 = "540 Trademark sample"
COL_210 = "210 Application number"
COL_111 = "111 Trademark registration certificate number"
COL_116 = "116 International registration number under Madrid Agreement"

# Excel error tokens — VLOOKUP misses / #N/A propagation from the manual
# editing pass. These look like real strings to CSV but encode "no value
# found" semantically. Saving them as mark_sample would poison search +
# display. Skip them as if the (540) field was empty.
_EXCEL_ERRORS = frozenset(
    {
        "#N/A",
        "#REF!",
        "#VALUE!",
        "#NAME?",
        "#NULL!",
        "#DIV/0!",
        "#NUM!",
    }
)


@dataclass(frozen=True)
class CsvKind:
    """Describes how to interpret one per-PDF CSV.

    Three kinds map 1:1 to the three `record_type` values:
      - A         (key = application_number, source col = COL_210)
      - B_domestic (key = certificate_number, source col = COL_111)
      - B_madrid  (key = madrid_number,     source col = COL_116, zero-padded)
    """

    record_type: str  # matches the `record_type` enum value in DB
    csv_id_col: str  # column to read from the CSV
    db_id_col: str  # column to join against in `trademarks`
    pad_to_7: bool  # zero-pad CSV IDs to 7 chars (Madrid only)


# Filename patterns route each CSV to the right kind. Order matters: the
# `_madrid` match has to be tried first since `B_T1_2026_madrid.csv` also
# matches the looser B pattern.
_KIND_BY_FILENAME = (
    (re.compile(r"^B_T\d_\d{4}_madrid\.csv$"), CsvKind("B_madrid", COL_116, "madrid_number", pad_to_7=True)),
    (re.compile(r"^A_T\d_\d{4}\.csv$"), CsvKind("A", COL_210, "application_number", pad_to_7=False)),
    (re.compile(r"^B_T\d_\d{4}\.csv$"), CsvKind("B_domestic", COL_111, "certificate_number", pad_to_7=False)),
)


def _classify(csv_path: Path) -> CsvKind | None:
    """Return the CsvKind for this filename, or None if we don't recognize it."""
    name = csv_path.name
    for pattern, kind in _KIND_BY_FILENAME:
        if pattern.match(name):
            return kind
    return None


def _normalize_id(raw: str, *, pad_to_7: bool) -> str:
    """Strip whitespace; for Madrid, left-pad with zeros to 7 chars.

    Our DB stores madrid_number as a 7-char zero-padded string
    (`0492543`), but IP VIETNAM publishes the same number in minimal form
    (`492543`) in the per-PDF CSVs. Normalize on the CSV side so the
    JOIN can be an equality match.
    """
    s = (raw or "").strip()
    if not s:
        return ""
    if pad_to_7 and s.isdigit() and len(s) < 7:
        return s.zfill(7)
    return s


def _read_pairs(csv_path: Path, kind: CsvKind) -> Iterator[tuple[str, str]]:
    """Stream (normalized_id, mark) pairs from a per-PDF CSV.

    Yields only rows where both fields are non-empty — empty IDs are
    parser artifacts; empty marks are intentional skips (user hasn't
    filled that row yet).
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None or kind.csv_id_col not in reader.fieldnames:
            print(
                f"  skipped: missing header {kind.csv_id_col!r}",
                file=sys.stderr,
            )
            return
        for row in reader:
            raw_id = row.get(kind.csv_id_col) or ""
            mark = (row.get(COL_540) or "").strip()
            if not mark:
                continue
            if mark in _EXCEL_ERRORS:
                # User opened the CSV in Excel and a VLOOKUP-style formula
                # left an error sentinel behind. Treat as "no data" — don't
                # touch the DB row, leave it for the next manual pass.
                continue
            norm_id = _normalize_id(raw_id, pad_to_7=kind.pad_to_7)
            if not norm_id:
                continue
            yield norm_id, mark


def _make_sync_dsn() -> str:
    raw = get_settings().database_url_sync
    return raw.replace("postgresql+psycopg2://", "postgresql://", 1)


def _enrich_one_file(cur, csv_path: Path, kind: CsvKind) -> int:
    """Stage one CSV into a temp table, UPDATE trademarks. Returns rowcount."""
    pairs = list(_read_pairs(csv_path, kind))
    if not pairs:
        return 0

    # Dedup by id BEFORE staging (last write wins). A single execute_values
    # batch cannot contain the same ON CONFLICT key twice — Postgres raises
    # CardinalityViolation ("cannot affect row a second time"). The CSVs do
    # carry intra-file duplicate ids (multi-row / multi-class entries), so the
    # SQL-level ON CONFLICT alone is not enough; we must collapse them in Python.
    pairs = list({pid: mark for pid, mark in pairs}.items())

    # Per-file temp table; auto-dropped at transaction end.
    # Using a temp table + UPDATE-FROM-JOIN is significantly faster than
    # per-row UPDATE in a loop — one round-trip per file regardless of
    # row count, and Postgres can pick a hash join for the merge.
    cur.execute("CREATE TEMP TABLE _enrich_batch (id TEXT PRIMARY KEY, mark TEXT NOT NULL) ON COMMIT DROP")
    execute_values(
        cur,
        "INSERT INTO _enrich_batch (id, mark) VALUES %s "
        # Defence-in-depth across page_size batches; intra-batch dupes are
        # already removed above so this only guards cross-page collisions.
        "ON CONFLICT (id) DO UPDATE SET mark = EXCLUDED.mark",
        pairs,
        page_size=5_000,
    )

    # The actual enrichment.  `record_type` is in the predicate to keep us
    # from accidentally updating a B_domestic row that happens to share an
    # application_number with an A row (rare but possible — the A_T<n>
    # application becomes the parent of a B_T<n+k> certificate).
    cur.execute(
        f"""
        UPDATE trademarks t
        SET mark_sample = b.mark
        FROM _enrich_batch b
        WHERE t.{kind.db_id_col} = b.id
          AND t.record_type = %s
          -- Same content already? Skip — keeps rowcount honest at the
          -- "rows actually changed" level rather than counting no-ops.
          AND (t.mark_sample IS DISTINCT FROM b.mark)
        """,
        (kind.record_type,),
    )
    rows = cur.rowcount

    # Clean up so the next file gets a fresh temp table at the same name.
    cur.execute("DROP TABLE _enrich_batch")
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--csv-dir",
        type=Path,
        default=DEFAULT_CSV_DIR,
        help=f"Directory holding per-PDF CSVs (default: {DEFAULT_CSV_DIR}).",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually commit. Without this flag we run the UPDATEs in a "
        "transaction we then roll back, so you see what *would* change.",
    )
    args = parser.parse_args(argv)

    if not args.csv_dir.is_dir():
        print(f"ERROR: not a directory: {args.csv_dir}", file=sys.stderr)
        return 1

    # Collect + classify files. Sort for deterministic output ordering.
    files: list[tuple[Path, CsvKind]] = []
    for path in sorted(args.csv_dir.glob("*.csv")):
        kind = _classify(path)
        if kind is None:
            # Don't print every unmatched file — keeps the log readable.
            # Common skip: per-PDF overflow files like A_T1_2026_511_overflow.txt
            # (those aren't .csv anyway, just in case).
            continue
        files.append((path, kind))

    if not files:
        print(f"No recognized per-PDF CSVs in {args.csv_dir}.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(_make_sync_dsn())
    conn.autocommit = False

    total = 0
    try:
        with conn.cursor() as cur:
            print(f"  {'file':<32}  {'kind':<12}  {'updated':>8}")
            for path, kind in files:
                updated = _enrich_one_file(cur, path, kind)
                total += updated
                print(f"  {path.name:<32}  {kind.record_type:<12}  {updated:>8,}")

        if args.execute:
            conn.commit()
            print(f"\nOK: committed {total:,} mark_sample updates")
        else:
            conn.rollback()
            print(f"\nDRY-RUN: {total:,} rows would be updated. Re-run with --execute to apply.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
