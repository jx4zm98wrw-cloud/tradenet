"""widen ip_agency + ip_agency_status to TEXT

Some B-file (740) agency texts run to 200+ chars (Chinese, Turkish, Vietnamese
full agency addresses). varchar(64) was too narrow.

Revision ID: 20260520_0003
Revises: 20260520_0002
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260520_0003"
down_revision: Union[str, None] = "20260520_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("trademarks", "ip_agency", type_=sa.Text(), existing_nullable=True)
    op.alter_column("trademarks", "ip_agency_status", type_=sa.Text(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("trademarks", "ip_agency", type_=sa.String(64), existing_nullable=True)
    op.alter_column("trademarks", "ip_agency_status", type_=sa.String(64), existing_nullable=True)
