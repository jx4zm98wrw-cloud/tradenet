"""trademarks_mark_embedding

Revision ID: 20260625_0031
Revises: 20260625_0030
Create Date: 2026-06-26 06:12:14.643583

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260625_0031"
down_revision: Union[str, None] = "20260625_0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("mark_embedding", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("trademarks", "mark_embedding")
