"""trademarks.is_representative: flip column default false -> true.

A freshly-inserted row is usually a brand-new mark (its own dedup representative),
so defaulting is_representative TRUE keeps it visible until the ingest recompute
demotes any superseded sibling — a graceful degradation (shows, maybe twice) vs
false (invisible until the backfill runs). Existing rows are unchanged (already
flagged by scripts/backfill_is_representative.py); only the column DEFAULT changes.
"""

from __future__ import annotations

from alembic import op

revision: str = "20260701_0034"
down_revision: str | None = "20260701_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE trademarks ALTER COLUMN is_representative SET DEFAULT true")


def downgrade() -> None:
    op.execute("ALTER TABLE trademarks ALTER COLUMN is_representative SET DEFAULT false")
