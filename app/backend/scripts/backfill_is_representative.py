"""Backfill: populate trademarks.is_representative for the whole corpus.

Sets `is_representative = true` on exactly the ONE most-advanced row of each
dedup group (certificate present > granted > id desc — the SQL twin of
`_dedup.representative_marks`), so the unfiltered facet/search path can filter an
indexed boolean instead of DISTINCT-ON-sorting the whole table.

Idempotent (writes only rows whose flag changes) and re-runnable. The ingest
worker maintains the flag for freshly-ingested groups, so this is only needed for
the INITIAL population (and after a bulk backfill of `vn_grant_date`, which is a
tiebreaker in the ordering). Usage (from app/backend):

    python -m scripts.backfill_is_representative
"""

from __future__ import annotations

import os
import time

import psycopg2

from api._dedup import recompute_is_representative_sql


def _dsn() -> str:
    raw = os.environ.get("TM_DATABASE_URL_SYNC", "postgresql+psycopg2://tm:tm@localhost:5435/tm")
    return raw.replace("postgresql+psycopg2://", "postgresql://")


def main() -> int:
    conn = psycopg2.connect(_dsn())
    conn.autocommit = False
    cur = conn.cursor()
    t0 = time.time()
    cur.execute(recompute_is_representative_sql(scoped_to_gazette=False))
    changed = cur.rowcount
    conn.commit()
    cur.execute("SELECT count(*) FROM trademarks WHERE is_representative")
    reps = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM trademarks")
    total = cur.fetchone()[0]
    conn.close()
    print(
        f"is_representative: {reps:,} representatives / {total:,} rows "
        f"({changed:,} flags changed, {(time.time() - t0) * 1000:.0f} ms)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
