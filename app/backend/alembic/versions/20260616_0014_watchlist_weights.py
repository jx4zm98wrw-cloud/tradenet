"""Per-matter similarity weights — add watchlists.weights (JSONB, nullable).

A watchlist IS the "matter" entity (it already carries client/matter columns).
This column stores per-channel similarity weight overrides
(keys: phonetic/visual/class/vienna). NULL means "use DEFAULT_WEIGHTS"; a
stored dict is merged over the defaults and renormalised at use time by
tm_similarity.resolve_weights. Applied when ranking similar marks in a
matter's context (e.g. pharma matters up-weight phonetic).

Additive and backward-compatible: existing watchlists keep NULL → default
behaviour unchanged.

Revision ID: 20260616_0014
Revises: 20260616_0013
Create Date: 2026-06-16

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260616_0014"
down_revision: str | None = "20260616_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlists", sa.Column("weights", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("watchlists", "weights")
