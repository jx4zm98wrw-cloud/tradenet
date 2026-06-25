"""trademarks logo_kind

Revision ID: 20260625_0030
Revises: 20260625_0029
Create Date: 2026-06-25 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260625_0030"
down_revision: Union[str, None] = "20260625_0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("logo_kind", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trademarks", "logo_kind")
