"""madrid sweep mode

Revision ID: 20260623_0025
Revises: 20260623_0024
Create Date: 2026-06-23

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260623_0025"
down_revision: str | None = "20260623_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "madrid_sweep_control",
        sa.Column("mode", sa.Text(), nullable=False, server_default="normal"),
    )
    op.add_column(
        "madrid_sweep_control",
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint("ck_madrid_sweep_mode", "madrid_sweep_control", "mode IN ('normal','fast')")


def downgrade() -> None:
    op.drop_constraint("ck_madrid_sweep_mode", "madrid_sweep_control", type_="check")
    op.drop_column("madrid_sweep_control", "concurrency")
    op.drop_column("madrid_sweep_control", "mode")
