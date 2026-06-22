"""Denormalized clean entity columns on trademarks (entity-canon phase 2).

Adds applicant_clean/applicant_norm + representative_clean/representative_norm,
btree-indexing the two *_norm grouping keys. Populated by
scripts/backfill_entity_clean.py.

Revision ID: 20260622_0023
Revises: 20260621_0022
Create Date: 2026-06-22
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260622_0023"
down_revision: str | None = "20260621_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("applicant_clean", sa.Text(), nullable=True))
    op.add_column("trademarks", sa.Column("applicant_norm", sa.Text(), nullable=True))
    op.add_column("trademarks", sa.Column("representative_clean", sa.Text(), nullable=True))
    op.add_column("trademarks", sa.Column("representative_norm", sa.Text(), nullable=True))
    op.create_index("ix_trademarks_applicant_norm", "trademarks", ["applicant_norm"])
    op.create_index("ix_trademarks_representative_norm", "trademarks", ["representative_norm"])


def downgrade() -> None:
    op.drop_index("ix_trademarks_representative_norm", table_name="trademarks")
    op.drop_index("ix_trademarks_applicant_norm", table_name="trademarks")
    op.drop_column("trademarks", "representative_norm")
    op.drop_column("trademarks", "representative_clean")
    op.drop_column("trademarks", "applicant_norm")
    op.drop_column("trademarks", "applicant_clean")
