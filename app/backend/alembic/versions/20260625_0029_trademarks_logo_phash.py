"""trademarks logo_phash

Revision ID: 20260625_0029
Revises: 20260624_0028
Create Date: 2026-06-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260625_0029"
down_revision: Union[str, None] = "20260624_0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("logo_phash", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trademarks", "logo_phash")
