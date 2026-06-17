"""madrid_records table + indexes.

Revision ID: 20260617_0016
Revises: 20260617_0015
Create Date: 2026-06-17
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision: str = "20260617_0016"
down_revision: str | None = "20260617_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "madrid_records",
        sa.Column("irn", sa.Text(), primary_key=True),
        sa.Column("holder_name", sa.Text()),
        sa.Column("holder_address", sa.Text()),
        sa.Column("holder_country", sa.Text()),
        sa.Column("holder_legal_status", sa.Text()),
        sa.Column("mark_text", sa.Text()),
        sa.Column("representative", sa.Text()),
        sa.Column("registration_date", sa.Date()),
        sa.Column("expiration_date", sa.Date()),
        sa.Column("nice_classes", ARRAY(sa.Text())),
        sa.Column("designated_countries", ARRAY(sa.Text())),
        sa.Column("basic_registration", sa.Text()),
        sa.Column("language", sa.Text()),
        sa.Column("vn_designated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("vn_status", sa.Text()),
        sa.Column("vn_grant_date", sa.Date()),
        sa.Column("vn_refusal_date", sa.Date()),
        sa.Column("designation_status", JSONB()),
        sa.Column("transaction_history", JSONB()),
        sa.Column("raw", JSONB()),
        sa.Column("source_url", sa.Text()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.Text()),
        sa.Column("parse_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_madrid_records_expiration_date", "madrid_records", ["expiration_date"])
    op.create_index("ix_madrid_records_vn_status", "madrid_records", ["vn_status"])
    op.create_index("ix_madrid_records_vn_grant_date", "madrid_records", ["vn_grant_date"])
    op.execute(
        "CREATE INDEX ix_madrid_records_designated_countries "
        "ON madrid_records USING gin (designated_countries)"
    )


def downgrade() -> None:
    op.drop_table("madrid_records")
