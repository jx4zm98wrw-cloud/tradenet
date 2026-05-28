"""Audit `trademarks.mark_sample` coverage after enrichment.

Run after `scripts/enrich_mark_samples.py --execute` to confirm:
  1. Coverage jumped from ~0% on A-files to near-100%
  2. The remaining gap is small + explained (rows with no CSV match,
     or rows where extraction had filled mark_sample with a Vienna
     code that we'd kept rather than overwrite)
  3. A random spot-check of enriched rows pairs the right wordmark
     to the right app number

Read-only; safe to run anytime.

Usage:

    cd app/backend
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    python -m scripts.audit_enrichment
"""

from __future__ import annotations

import psycopg2

from api.settings import get_settings


def _make_sync_dsn() -> str:
    raw = get_settings().database_url_sync
    return raw.replace("postgresql+psycopg2://", "postgresql://", 1)


def main() -> int:
    conn = psycopg2.connect(_make_sync_dsn())
    try:
        with conn.cursor() as cur:
            print("=" * 60)
            print("Coverage by record_type")
            print("=" * 60)
            cur.execute(
                """
                SELECT
                  record_type::text,
                  COUNT(*) AS total,
                  COUNT(*) FILTER (WHERE mark_sample IS NOT NULL AND mark_sample <> '') AS has_name,
                  ROUND(
                    100.0 * COUNT(*) FILTER (WHERE mark_sample IS NOT NULL AND mark_sample <> '')
                    / NULLIF(COUNT(*), 0),
                    2
                  ) AS pct
                FROM trademarks
                GROUP BY 1
                ORDER BY 1
                """
            )
            print(f"  {'record_type':<14} {'total':>8} {'has_name':>10} {'%':>8}")
            for rt, total, has_name, pct in cur.fetchall():
                print(f"  {rt:<14} {total:>8,} {has_name:>10,} {pct:>7}%")

            print()
            print("=" * 60)
            print("Rows still missing mark_sample (gap analysis)")
            print("=" * 60)
            cur.execute(
                """
                SELECT
                  CASE
                    WHEN t.application_number IS NULL OR t.application_number = '' THEN 'no_application_number'
                    WHEN idx.application_number IS NULL THEN 'no_csv_match'
                    ELSE 'unknown'
                  END AS gap_kind,
                  COUNT(*) AS n
                FROM trademarks t
                LEFT JOIN tm_name_index idx
                  ON t.application_number = idx.application_number
                WHERE t.mark_sample IS NULL OR t.mark_sample = ''
                GROUP BY 1
                ORDER BY 2 DESC
                """
            )
            for kind, n in cur.fetchall():
                print(f"  {kind:<22} {n:>6,}")

            print()
            print("=" * 60)
            print("Sample of the 'no_csv_match' rows (manual review)")
            print("=" * 60)
            cur.execute(
                """
                SELECT t.application_number,
                       t.record_type::text,
                       EXTRACT(YEAR FROM t.submission_date)::int AS year
                FROM trademarks t
                LEFT JOIN tm_name_index idx
                  ON t.application_number = idx.application_number
                WHERE (t.mark_sample IS NULL OR t.mark_sample = '')
                  AND t.application_number IS NOT NULL
                  AND t.application_number <> ''
                  AND idx.application_number IS NULL
                ORDER BY t.application_number
                LIMIT 20
                """
            )
            rows = cur.fetchall()
            if not rows:
                print("  (none)")
            else:
                print(f"  {'app_number':<18} {'record_type':<14} {'year':>6}")
                for app, rt, year in rows:
                    print(f"  {app:<18} {rt:<14} {year!s:>6}")

            print()
            print("=" * 60)
            print("Random spot-check: 10 enriched rows (DB row ↔ CSV row)")
            print("=" * 60)
            cur.execute(
                """
                SELECT t.application_number, t.mark_sample, idx.mark_sample
                FROM trademarks t
                JOIN tm_name_index idx
                  ON t.application_number = idx.application_number
                WHERE t.mark_sample IS NOT NULL
                  AND t.mark_sample <> ''
                ORDER BY random()
                LIMIT 10
                """
            )
            mismatches = 0
            for app, db_mark, csv_mark in cur.fetchall():
                # Loose comparison — case-insensitive, whitespace-collapsed —
                # because DB-side extraction is mostly empty so most matches
                # came straight from the CSV anyway. A mismatch here means
                # PDF extraction filled mark_sample with something the CSV
                # disagrees with, which is rare but useful to notice.
                norm_db = " ".join(db_mark.split()).lower()
                norm_csv = " ".join(csv_mark.split()).lower()
                tag = "OK" if norm_db == norm_csv else "DIFF"
                if tag == "DIFF":
                    mismatches += 1
                # Truncate long marks for display
                d_disp = (db_mark[:30] + "…") if len(db_mark) > 30 else db_mark
                c_disp = (csv_mark[:30] + "…") if len(csv_mark) > 30 else csv_mark
                print(f"  [{tag}] {app:<16}  db={d_disp!r}  csv={c_disp!r}")
            if mismatches:
                print(f"\n  {mismatches} mismatch(es) in spot-check — review above")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
