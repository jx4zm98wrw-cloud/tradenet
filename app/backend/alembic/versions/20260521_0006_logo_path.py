"""add logo_path to trademarks

Revision ID: 20260521_0006
Revises: 20260521_0005
Create Date: 2026-05-21

Adds a nullable `logo_path` TEXT column to `trademarks` for the relative
path of the extracted trademark logo PNG. Populated by the worker after
the image extractor has run; rows ingested before image extraction stay
NULL and the frontend falls back to `mark_sample` text rendering.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260521_0006"
down_revision: Union[str, None] = "20260521_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trademarks", sa.Column("logo_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("trademarks", "logo_path")
