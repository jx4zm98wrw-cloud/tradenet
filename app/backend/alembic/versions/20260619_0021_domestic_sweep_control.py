"""domestic_sweep_control singleton control row

Revision ID: 20260619_0021
Revises: 20260619_0020
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260619_0021"
down_revision = "20260619_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domestic_sweep_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="idle"),
        sa.Column("cap", sa.Integer(), nullable=True),
        sa.Column("delay", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("jitter", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_appno", sa.Text(), nullable=True),
        sa.Column("next_appno", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('idle','running','paused','stopping')",
            name="ck_domestic_sweep_status",
        ),
    )
    op.execute("INSERT INTO domestic_sweep_control (id, status) VALUES (1, 'idle')")


def downgrade() -> None:
    op.drop_table("domestic_sweep_control")
