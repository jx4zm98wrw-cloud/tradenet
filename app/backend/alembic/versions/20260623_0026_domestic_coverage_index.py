"""domestic coverage index: trademarks (mark_category, application_number)

Speeds /admin/domestic-enrichment's COUNT(DISTINCT application_number) per
mark_category, which at ~219k domestic rows was a seq-scan + on-disk merge sort
(~850ms across the two count queries). The partial composite btree lets the
GroupAggregate stream pre-sorted instead, dropping it to ~tens of ms.

Built CONCURRENTLY (via an autocommit block, since CONCURRENTLY cannot run in a
transaction) so the running domestic sweep is never blocked.

Revision ID: 20260623_0026
Revises: 20260623_0025
Create Date: 2026-06-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "20260623_0026"
down_revision: str | None = "20260623_0025"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            "ix_trademarks_markcat_appno",
            "trademarks",
            ["mark_category", "application_number"],
            unique=False,
            postgresql_concurrently=True,
            postgresql_where=sa.text("application_number IS NOT NULL"),
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(
            "ix_trademarks_markcat_appno",
            table_name="trademarks",
            postgresql_concurrently=True,
            if_exists=True,
        )
