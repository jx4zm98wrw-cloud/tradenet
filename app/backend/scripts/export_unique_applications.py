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

# Excel/Sheets hard cap is 32,767 chars per cell. The (511) goods & services text
# can exceed it for marks with many/long Nice classes. Rather than truncate (which
# still trips some importers near the cap), any application with an over-limit cell
# is pulled OUT of the CSV in full to a sidecar `*_overflow.json`, and the CSV cell
# is replaced with a short pointer — so the CSV always opens. We stay well under
# the hard cap for safety margin.
_CELL_LIMIT = 32000


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
    if isinstance(v, (datetime.date, datetime.datetime)):
        return v.isoformat()
    if isinstance(v, (list, dict)):
        return json.dumps(v, ensure_ascii=False)
    return v


def _json_default(o: object) -> object:
    """Make non-JSON-native DB values (dates) serializable for the overflow file."""
    if isinstance(o, (datetime.date, datetime.datetime)):
        return o.isoformat()
    return str(o)


def _export(
    conn,
    table: str,
    key_col: str,
    universe_sql: str,
    base_cols: list[str],
    join_sql: str,
    extra: dict[str, str],
    out_path: pathlib.Path,
    json_path: pathlib.Path,
) -> tuple[int, int, int]:
    """Export the COMPLETE unique universe (every distinct key from `trademarks`),
    LEFT JOIN the enrichment table so not-yet-enriched applications still appear
    (with blank fields) and are flagged `enriched=false`.

    Any application with a cell over `_CELL_LIMIT` is written IN FULL to `json_path`
    (untruncated, structured) and its over-limit cell(s) in the CSV are replaced with
    a short `[overflow -> file]` pointer, so the CSV always opens.

    The key column comes from the universe `u` (always present); other enrichment
    columns come from `e` (NULL when unenriched). Returns (rows, enriched, overflow).
    """
    select_cols = [f"u.{key_col} AS {c}" if c == key_col else f"e.{c}" for c in base_cols]
    select = (
        ", ".join(select_cols) + ", " + ", ".join(extra.values()) + f", (e.{key_col} IS NOT NULL) AS enriched"
    )
    headers = base_cols + list(extra.keys()) + ["enriched"]
    cur = conn.cursor(name=f"export_{table}")  # server-side: stream without loading all
    cur.itersize = 5000
    cur.execute(
        f"SELECT {select} FROM ({universe_sql}) u LEFT JOIN {table} e ON e.{key_col} = u.{key_col} {join_sql}"
    )
    n = enriched = 0
    overflow: list[dict] = []
    jb = json_path.name
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for row in cur:
            cells = [_cell(v) for v in row]
            big = [i for i, c in enumerate(cells) if isinstance(c, str) and len(c) > _CELL_LIMIT]
            if big:
                # full untruncated record (structured) -> sidecar JSON
                overflow.append(dict(zip(headers, row, strict=True)))
                for i in big:
                    cells[i] = f"[overflow: {len(cells[i])} chars -> {jb}]"
            w.writerow(cells)
            n += 1
            if row[-1]:  # the `enriched` boolean
                enriched += 1
    cur.close()
    if overflow:
        with json_path.open("w", encoding="utf-8") as jf:
            json.dump(overflow, jf, ensure_ascii=False, indent=2, default=_json_default)
    return n, enriched, len(overflow)


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

    # --- Domestic: EVERY unique application_number (universe = trademarks) + enrichment ---
    dom_cols = _enrichment_columns(meta, "domestic_records")
    dom_universe = (
        "SELECT DISTINCT application_number FROM trademarks "
        "WHERE mark_category LIKE 'domestic%' AND application_number IS NOT NULL"
    )
    dom_join = (
        "LEFT JOIN LATERAL ("
        "  SELECT mark_name, logo_path, applicant_clean, applicant_norm, vn_grant_date"
        "  FROM trademarks t WHERE t.application_number = u.application_number"
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
    dom_json = out_dir / "unique_domestic_applications_overflow.json"
    n_dom, e_dom, o_dom = _export(
        conn,
        "domestic_records",
        "application_number",
        dom_universe,
        dom_cols,
        dom_join,
        dom_extra,
        dom_path,
        dom_json,
    )

    # --- Madrid: EVERY unique IRN (universe = trademarks.lineage_key) + enrichment ---
    mad_cols = _enrichment_columns(meta, "madrid_records")
    mad_universe = (
        "SELECT DISTINCT lineage_key AS irn FROM trademarks "
        "WHERE mark_category LIKE 'madrid%' AND lineage_key IS NOT NULL"
    )
    mad_join = (
        "LEFT JOIN LATERAL ("
        "  SELECT mark_name, logo_path FROM trademarks t WHERE t.lineage_key = u.irn"
        "  ORDER BY (t.logo_path IS NULL), (t.mark_name IS NULL) LIMIT 1"
        ") tm ON true"
    )
    mad_extra = {"resolved_mark_name": "tm.mark_name", "logo_path": "tm.logo_path"}
    mad_path = out_dir / "unique_madrid_applications.csv"
    mad_json = out_dir / "unique_madrid_applications_overflow.json"
    n_mad, e_mad, o_mad = _export(
        conn,
        "madrid_records",
        "irn",
        mad_universe,
        mad_cols,
        mad_join,
        mad_extra,
        mad_path,
        mad_json,
    )

    conn.close()
    print(
        f"domestic: {n_dom} unique ({e_dom} enriched, {n_dom - e_dom} unenriched, "
        f"{o_dom} overflow->json) -> {dom_path}"
    )
    print(
        f"madrid:   {n_mad} unique ({e_mad} enriched, {n_mad - e_mad} unenriched, "
        f"{o_mad} overflow->json) -> {mad_path}"
    )
    if o_dom:
        print(f"  domestic overflow JSON ({o_dom} full records): {dom_json}")
    if o_mad:
        print(f"  madrid overflow JSON ({o_mad} full records): {mad_json}")
    print(f"total unique applications: {n_dom + n_mad}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
