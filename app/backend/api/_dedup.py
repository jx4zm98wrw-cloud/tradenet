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

from sqlalchemy import ColumnElement, Text, and_, cast, func, select
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
    """A ``DISTINCT ON (dedup key)`` view of `trademarks` that keeps the
    MOST-ADVANCED row per mark — the SQL twin of ``search._dedup_pref``
    (certificate present > granted > id).

    Returns an aliased ``Trademark`` entity backed by the DISTINCT-ON subquery,
    so callers can ``SELECT`` / ``GROUP BY`` / ``JOIN`` its columns and
    ``COUNT(*)`` the unique marks, with `where` applied INSIDE the subquery.

    DISTINCT ON keeps the first row per key by the inner ``ORDER BY``; the key
    must lead that ORDER BY. The remaining terms reproduce ``_dedup_pref``'s
    max-wins tuple ``(certificate_number is not None, vn_grant_date is not None,
    str(id))`` as DESC so the same physical row survives as in the Python paths.
    """
    if not where:
        # Unfiltered: the maintained `is_representative` flag already marks exactly
        # one row per dedup group (the SQL twin of the DISTINCT ON below), so filter
        # the indexed boolean instead of sorting the WHOLE table — the DISTINCT ON
        # seq-scanned 238k rows and spilled a ~19 MB external-merge sort to disk on
        # every facet / default-search call. Semantically identical to the
        # unfiltered DISTINCT ON (both yield the representative row of every group).
        return aliased(Trademark, select(Trademark).where(Trademark.is_representative).subquery())
    key = dedup_key_expr()
    sub = select(Trademark).where(and_(*where))
    sub = sub.distinct(key).order_by(
        key,
        Trademark.certificate_number.is_not(None).desc(),
        Trademark.vn_grant_date.is_not(None).desc(),
        cast(Trademark.id, Text).desc(),
    )
    return aliased(Trademark, sub.subquery())


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
