"""indexes for owner_id columns

Revision ID: 20260521_0005
Revises: 20260520_0004
Create Date: 2026-05-21

Adds indexes on `gazettes.uploaded_by` and `watchlists.owner_id` to keep
"my uploads / my watchlists" queries fast as the user base grows.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20260521_0005"
down_revision: Union[str, None] = "20260520_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_gazettes_uploaded_by", "gazettes", ["uploaded_by"])
    # watchlists.owner_id index already exists from 20260520_0004 — no-op here.


def downgrade() -> None:
    op.drop_index("ix_gazettes_uploaded_by", table_name="gazettes")
