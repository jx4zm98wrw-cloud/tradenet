"""Add GIN index on trademarks.vienna_codes.

The Vienna search mode in /api/v1/search/trademarks does array-overlap
queries via the `&&` operator (ANY semantics) and `@>` containment
(ALL semantics). Without a GIN index the planner falls back to a seq
scan on trademarks (~46k rows in the 2026 demo set), making Vienna
search noticeably slower than the other modes.

Mirrors the ix_trademarks_nice_classes_gin index added in the prior
schema reconciliation (20260526_0007).

Revision ID: 20260526_0008
Revises: 20260526_0007
Create Date: 2026-05-26 14:17:10.930358
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260526_0008"
down_revision: str | None = "20260526_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_trademarks_vienna_codes_gin",
        "trademarks",
        ["vienna_codes"],
        unique=False,
        postgresql_using="gin",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_trademarks_vienna_codes_gin",
        table_name="trademarks",
        postgresql_using="gin",
    )
