"""madrid_sweep_control.next_irn — the IRN the worker will fetch next

Revision ID: 20260619_0019
Revises: 20260619_0018
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260619_0019"
down_revision = "20260619_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("madrid_sweep_control", sa.Column("next_irn", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("madrid_sweep_control", "next_irn")
