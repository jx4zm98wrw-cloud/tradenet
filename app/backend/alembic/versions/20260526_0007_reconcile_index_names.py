"""Reconcile index names with current models.

The Trademark model renamed two indexed columns (city -> applicant_city,
country_code -> applicant_country_code) without a corresponding migration,
and removed index=True from gazettes.uploaded_by without dropping the
underlying index. This migration aligns the database with the model.

Also declares the existing nice_classes GIN index on the model side
(via __table_args__) so future `alembic check` runs don't try to drop
it. The index itself is unchanged.

Revision ID: 20260526_0007
Revises: 20260521_0006
Create Date: 2026-05-26 11:12:29.358503

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260526_0007"
down_revision: str | None = "20260521_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_gazettes_uploaded_by", table_name="gazettes")
    op.drop_index("ix_trademarks_city", table_name="trademarks")
    op.drop_index("ix_trademarks_country_code", table_name="trademarks")
    op.create_index(
        op.f("ix_trademarks_applicant_city"),
        "trademarks",
        ["applicant_city"],
        unique=False,
    )
    op.create_index(
        op.f("ix_trademarks_applicant_country_code"),
        "trademarks",
        ["applicant_country_code"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trademarks_applicant_country_code"), table_name="trademarks")
    op.drop_index(op.f("ix_trademarks_applicant_city"), table_name="trademarks")
    op.create_index("ix_trademarks_country_code", "trademarks", ["applicant_country_code"], unique=False)
    op.create_index("ix_trademarks_city", "trademarks", ["applicant_city"], unique=False)
    op.create_index("ix_gazettes_uploaded_by", "gazettes", ["uploaded_by"], unique=False)
