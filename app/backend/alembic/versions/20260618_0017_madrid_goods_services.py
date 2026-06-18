"""madrid_records.goods_services (per-class full goods text).

Revision ID: 20260618_0017
Revises: 20260617_0016
Create Date: 2026-06-18
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "20260618_0017"
down_revision: str | None = "20260617_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("madrid_records", sa.Column("goods_services", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("madrid_records", "goods_services")
