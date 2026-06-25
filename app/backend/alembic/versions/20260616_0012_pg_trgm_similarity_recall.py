"""Enable pg_trgm + GIN trigram indexes for two-stage similar-marks recall.

The phonetic similarity engine (tm_similarity) is examiner-grade, but the
search route only ever scored a publication-date-ordered over-fetch window of
~100 rows in Python — so "sort by similarity" never ranked the full corpus and
could miss the true top conflicts. This migration adds the DB-side recall half
of a two-stage retrieval: cheap trigram candidate generation in Postgres, then
precise rerank by the Python engine.

Two functional GIN indexes (on lower(mark_sample) and lower(applicant_name))
back the pg_trgm `%` operator. Both columns are indexed because A-files
(applications) typically have no mark_sample and fall back to applicant_name
as the phonetic target, while B-files carry the wordmark in mark_sample.

`lower(...)` is IMMUTABLE, so the expression indexes are valid. The extension
and indexes are additive and safe; downgrade drops the indexes (the extension
is left in place — dropping it could affect anything else that adopted trgm).

Revision ID: 20260616_0012
Revises: 20260528_0011
Create Date: 2026-06-16

"""

from __future__ import annotations

from alembic import op

revision: str = "20260616_0012"
down_revision: str | None = "20260528_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # CONCURRENTLY would avoid a write lock in prod, but Alembic runs inside a
    # transaction by default and CONCURRENTLY can't. The trademarks table is
    # bulk-loaded by the ingest worker, not under live OLTP write contention,
    # so a plain index build is acceptable here.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_sample_trgm "
        "ON trademarks USING gin (lower(mark_sample) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_applicant_name_trgm "
        "ON trademarks USING gin (lower(applicant_name) gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_applicant_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_sample_trgm")
    # Intentionally leave the pg_trgm extension installed.
