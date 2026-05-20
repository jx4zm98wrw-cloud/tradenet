"""widen nice_group_number and date_combined to TEXT

Revision ID: 20260520_0002
Revises: 20260520_0001
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0002"
down_revision: Union[str, None] = "20260520_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("trademarks", "nice_group_number", type_=sa.Text(), existing_nullable=True)
    op.alter_column("trademarks", "date_combined", type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("trademarks", "nice_group_number", type_=sa.String(32), existing_nullable=True)
    op.alter_column("trademarks", "date_combined", type_=sa.String(32), existing_nullable=True)
