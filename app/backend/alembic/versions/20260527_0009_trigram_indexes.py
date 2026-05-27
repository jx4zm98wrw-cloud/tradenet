"""Add pg_trgm extension + trigram GIN indexes on applicant_name / mark_sample.

Free-text search in /api/v1/search/trademarks uses ILIKE substring matches
on `applicant_name` and `mark_sample` (`_filters.py:build_trademark_where`).
Without a trigram index the planner falls back to a sequential scan on
trademarks (~46k rows in the 2026 demo set), so every "find marks
mentioning CHANEL" query reads the entire table.

pg_trgm + gin_trgm_ops enables index-backed ILIKE for any LIKE/ILIKE
pattern with at least one 3-grammable substring — the dominant case
in the search bar. Expected: 50-100x speedup on substring queries.

Notes:
  - The CREATE EXTENSION is idempotent (IF NOT EXISTS).
  - Indexes are created CONCURRENTLY only when DDL transaction guards
    allow it; alembic's default per-revision transaction does not, so
    we use plain CREATE INDEX. Acceptable for this dataset size; revisit
    if the table grows past ~1M rows.
  - The two new GIN indexes coexist with the existing `idx_trademarks_*`
    btree indexes on the same columns (which serve equality lookups);
    Postgres picks the index appropriate for each query shape.

Revision ID: 20260527_0009
Revises: 20260526_0008
Create Date: 2026-05-27 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260527_0009"
down_revision: str | None = "20260526_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent extension creation — safe to re-run.
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # Trigram GIN indexes for ILIKE %q% substring search.
    # `gin_trgm_ops` is the opclass that makes the index usable for
    # LIKE / ILIKE / regex match.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_applicant_name_trgm "
        "ON trademarks USING gin (applicant_name gin_trgm_ops) "
        "WHERE applicant_name IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_sample_trgm "
        "ON trademarks USING gin (mark_sample gin_trgm_ops) "
        "WHERE mark_sample IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_sample_trgm")
    op.execute("DROP INDEX IF EXISTS ix_trademarks_applicant_name_trgm")
    # Leave pg_trgm extension installed — it may be used by other tables/queries
    # (and dropping it would cascade-drop any other trigram indexes).
