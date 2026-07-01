"""Query-time mark deduplication shared by search results and facet counts.

The `trademarks` table holds ONE ROW PER GAZETTE APPEARANCE, so a single mark
surfaces as both an application row and a registration row (sharing an
`application_number`), or a Madrid registration + renewal (sharing a
`lineage_key` / IRN, NULL appno). We never merge these in the DB — both rows are
real and carry distinct data — so instead we collapse them at QUERY TIME, so
each mark is counted/rendered once under its MOST-ADVANCED representative row.

`routes/search.py` carries Python equivalents (`_dedup_key` / `_dedup_pref` /
`_dedup_marks`) used by its in-memory text/phonetic rerank paths. The SQL
helpers here MUST keep the SAME key and the SAME preference so every surface
(search results, total, and every facet count) agrees on what "one mark" is.
This is purely query-side: it works automatically for future ingests with
nothing to re-run.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, Text, cast, func, select
from sqlalchemy.orm import aliased

from .db import Trademark


def dedup_key_expr() -> ColumnElement[str]:
    """SQL twin of ``search._dedup_key``: ``COALESCE(application_number,
    lineage_key, id::text)``.

    ``NULLIF(col, '')`` mirrors Python's ``a or b or c`` truthiness so an empty
    string falls through to the next term exactly as the in-memory helper does
    (a blank appno must not become its own dedup group).
    """
    return func.coalesce(
        func.nullif(Trademark.application_number, ""),
        func.nullif(Trademark.lineage_key, ""),
        cast(Trademark.id, Text),
    )


def representative_marks(where: Sequence[Any] = ()) -> Any:
    """A one-row-per-mark view of `trademarks` — the maintained `is_representative`
    row of each dedup group (most-advanced: certificate present > granted > id) —
    with `where` applied ON TOP of that deduped set (**dedup-then-filter**).

    Returns an aliased ``Trademark`` entity so callers can ``SELECT`` / ``GROUP
    BY`` / ``JOIN`` its columns and ``COUNT(*)`` the unique marks.

    DEDUP-THEN-FILTER (not filter-then-dedup) is deliberate: a mark is counted by
    its REPRESENTATIVE row's attributes, so a mark present as BOTH an application
    and a registration row is a `domestic_registration` and is NOT returned by a
    `mark_category=domestic_application` filter. This makes the filtered result
    total agree with the sidebar facet counts (which already group by the
    representative) — otherwise a filter that matches a non-representative row
    (e.g. the application row of a since-registered mark) would inflate the total.
    Filtering the indexed `is_representative` set is also faster than the old
    DISTINCT-ON-sort-then-filter. Requires `is_representative` to be maintained
    (ingest worker + backfill_is_representative).
    """
    return aliased(Trademark, select(Trademark).where(Trademark.is_representative, *where).subquery())


# --- Maintenance of trademarks.is_representative -----------------------------
# Raw-SQL twins of dedup_key_expr() and the representative_marks ORDER BY, used
# by the ingest worker (sync session) and scripts/backfill_is_representative.py
# to MAINTAIN the flag. They MUST mirror the constructs above.
_DEDUP_KEY_SQL = "coalesce(nullif(application_number, ''), nullif(lineage_key, ''), id::text)"
_REP_ORDER_SQL = "(certificate_number IS NOT NULL) DESC, (vn_grant_date IS NOT NULL) DESC, id::text DESC"


def recompute_is_representative_sql(*, scoped_to_gazette: bool) -> str:
    """UPDATE setting `is_representative = (row is its dedup group's most-advanced
    row)`.

    ``scoped_to_gazette=True`` recomputes only the groups touched by ``:gid``
    (post-ingest — keeps fresh rows correct without a full backfill); ``False``
    recomputes the whole table (backfill). Writes only rows whose flag actually
    changes, so it is idempotent and cheap to re-run.
    """
    scope = (
        f"WHERE {_DEDUP_KEY_SQL} IN "
        f"(SELECT DISTINCT {_DEDUP_KEY_SQL} FROM trademarks WHERE gazette_id = :gid)"
        if scoped_to_gazette
        else ""
    )
    return f"""
        WITH ranked AS (
            SELECT id, row_number() OVER (
                PARTITION BY {_DEDUP_KEY_SQL} ORDER BY {_REP_ORDER_SQL}
            ) AS rn
            FROM trademarks {scope}
        )
        UPDATE trademarks t
        SET is_representative = (r.rn = 1)
        FROM ranked r
        WHERE t.id = r.id AND t.is_representative IS DISTINCT FROM (r.rn = 1)
    """
