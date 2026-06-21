"""dead_mode columns on domestic_sweep_control (mode, concurrency)

Revision ID: 20260621_0022
Revises: 20260619_0021
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260621_0022"
down_revision: str | None = "20260619_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "domestic_sweep_control",
        sa.Column("mode", sa.Text(), nullable=False, server_default="normal"),
    )
    op.add_column(
        "domestic_sweep_control",
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_domestic_sweep_mode", "domestic_sweep_control", "mode IN ('normal','dead')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_domestic_sweep_mode", "domestic_sweep_control", type_="check")
    op.drop_column("domestic_sweep_control", "concurrency")
    op.drop_column("domestic_sweep_control", "mode")
