"""watchlists table — standing queries re-run on each gazette issue.

Revision ID: 20260520_0004
Revises: 20260520_0003
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260520_0004"
down_revision: Union[str, None] = "20260520_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "watchlists",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("client", sa.String(256), nullable=True),
        sa.Column("matter", sa.String(64), nullable=True),
        sa.Column("query", postgresql.JSONB(), nullable=False),
        sa.Column("query_desc", sa.Text(), nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("owner_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_watchlists_owner_id", "watchlists", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_watchlists_owner_id", table_name="watchlists")
    op.drop_table("watchlists")
