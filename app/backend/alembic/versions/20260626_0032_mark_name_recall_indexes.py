"""mark_name recall indexes: GIN trgm + dmetaphone on lower(mark_name).

Backs the search recall/rank paths added alongside mark_sample/applicant_name so a
mark found only by its resolved display name doesn't seq-scan. Mirrors 0012 (pg_trgm)
and 0013 (dmetaphone). Additive — no column, no data change.
"""

from __future__ import annotations

from alembic import op

revision: str = "20260626_0032"
down_revision: str | None = "20260625_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_name_trgm "
        "ON trademarks USING gin (lower(mark_name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_trademarks_mark_name_dmeta "
        "ON trademarks (dmetaphone(lower(mark_name)))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_name_dmeta")
    op.execute("DROP INDEX IF EXISTS ix_trademarks_mark_name_trgm")
