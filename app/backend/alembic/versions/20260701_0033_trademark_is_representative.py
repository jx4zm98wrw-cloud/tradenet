"""trademarks.is_representative: indexed one-row-per-mark flag.

Lets the unfiltered facet/search path filter on a boolean instead of
DISTINCT-ON-sorting the whole `trademarks` table (the sort spilled ~19 MB to
disk per facet). Additive column (default false) + partial index; populated by
scripts/backfill_is_representative.py and maintained at ingest.
"""

from __future__ import annotations

from alembic import op

revision: str = "20260701_0033"
down_revision: str | None = "20260626_0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE trademarks ADD COLUMN IF NOT EXISTS is_representative "
        "boolean NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_representative "
        "ON trademarks (is_representative) WHERE is_representative"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_representative")
    op.execute("ALTER TABLE trademarks DROP COLUMN IF EXISTS is_representative")
