"""Export UNIQUE domestic + Madrid applications with full information (Option A).

The enrichment tables are already one-row-per-unique-application:
  domestic_records  — unique `application_number` (IP VIETNAM-authoritative bibliography)
  madrid_records    — unique `irn`               (WIPO-authoritative bibliography)

This writes two clean UTF-8-SIG CSVs, one per source, selecting every enrichment
column (minus bulky audit fields) plus the resolved display fields that live only
on `trademarks` (the gazette layer): `mark_name` (resolved name), `logo_path`,
`applicant_clean`/`applicant_norm`, and the unified `vn_grant_date`.

Read-only. Usage (from app/backend):
    python -m scripts.export_unique_applications [--out-dir DIR]

Defaults to writing into <project-root>/exports/.
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import pathlib

import psycopg2

# Bulky / audit-only columns excluded from the flat table (kept in the DB for audit).
_DENY = {"raw", "content_hash", "parse_version"}


def _dsn() -> str:
    raw = os.environ.get("TM_DATABASE_URL_SYNC", "postgresql+psycopg2://tm:tm@localhost:5435/tm")
    return raw.replace("postgresql+psycopg2://", "postgresql://")


def _enrichment_columns(cur, table: str) -> list[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
        (table,),
    )
    return [r[0] for r in cur.fetchall() if r[0] not in _DENY]


def _cell(v: object) -> object:
    """Serialize arrays/JSON to a JSON string and dates to ISO so the CSV is flat."""
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    return v


def _export(
    conn, table: str, base_cols: list[str], join_sql: str, extra: dict[str, str], out_path: pathlib.Path
) -> int:
    select = ", ".join(f"e.{c}" for c in base_cols) + ", " + ", ".join(extra.values())
    headers = base_cols + list(extra.keys())
    # Server-side cursor: stream ~196k rows without loading them all into memory.
    cur = conn.cursor(name=f"export_{table}")
    cur.itersize = 5000
    cur.execute(f"SELECT {select} FROM {table} e {join_sql}")
    n = 0
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in cur:
            w.writerow([_cell(v) for v in row])
            n += 1
    cur.close()
    return n


def main(argv: list[str] | None = None) -> int:
    project_root = pathlib.Path(__file__).resolve().parents[3]  # app/backend/scripts -> root
    ap = argparse.ArgumentParser(description="Export unique domestic + Madrid applications")
    ap.add_argument("--out-dir", default=str(project_root / "exports"))
    args = ap.parse_args(argv)
    out_dir = pathlib.Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    conn = psycopg2.connect(_dsn())
    conn.set_session(readonly=True, autocommit=False)
    meta = conn.cursor()

    # --- Domestic: domestic_records (unique appno) + resolved fields from trademarks ---
    dom_cols = _enrichment_columns(meta, "domestic_records")
    dom_join = (
        "LEFT JOIN LATERAL ("
        "  SELECT mark_name, logo_path, applicant_clean, applicant_norm, vn_grant_date"
        "  FROM trademarks t WHERE t.application_number = e.application_number"
        "  ORDER BY (t.logo_path IS NULL), (t.mark_name IS NULL) LIMIT 1"
        ") tm ON true"
    )
    dom_extra = {
        "resolved_mark_name": "tm.mark_name",
        "logo_path": "tm.logo_path",
        "applicant_clean": "tm.applicant_clean",
        "applicant_norm": "tm.applicant_norm",
        "resolved_vn_grant_date": "tm.vn_grant_date",
    }
    dom_path = out_dir / "unique_domestic_applications.csv"
    n_dom = _export(conn, "domestic_records", dom_cols, dom_join, dom_extra, dom_path)

    # --- Madrid: madrid_records (unique irn) + resolved fields from trademarks ---
    mad_cols = _enrichment_columns(meta, "madrid_records")
    mad_join = (
        "LEFT JOIN LATERAL ("
        "  SELECT mark_name, logo_path FROM trademarks t WHERE t.lineage_key = e.irn"
        "  ORDER BY (t.logo_path IS NULL), (t.mark_name IS NULL) LIMIT 1"
        ") tm ON true"
    )
    mad_extra = {"resolved_mark_name": "tm.mark_name", "logo_path": "tm.logo_path"}
    mad_path = out_dir / "unique_madrid_applications.csv"
    n_mad = _export(conn, "madrid_records", mad_cols, mad_join, mad_extra, mad_path)

    conn.close()
    print(f"domestic: {n_dom} unique applications -> {dom_path}")
    print(f"madrid:   {n_mad} unique applications -> {mad_path}")
    print(f"total unique applications: {n_dom + n_mad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
