"""domestic_records table + indexes.

Revision ID: 20260619_0020
Revises: 20260619_0019
Create Date: 2026-06-19
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

from alembic import op

revision: str = "20260619_0020"
down_revision: str | None = "20260619_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domestic_records",
        sa.Column("application_number", sa.Text(), primary_key=True),
        sa.Column("mark_text", sa.Text()),
        sa.Column("mark_type", sa.Text()),
        sa.Column("applicant_name", sa.Text()),
        sa.Column("applicant_address", sa.Text()),
        sa.Column("representative", sa.Text()),
        sa.Column("colors", sa.Text()),
        sa.Column("nice_classes", ARRAY(sa.Text())),
        sa.Column("goods_services", JSONB()),
        sa.Column("vienna_codes", ARRAY(sa.Text())),
        sa.Column("status_code", sa.Text()),
        sa.Column("filing_date", sa.Date()),
        sa.Column("publication_no", sa.Text()),
        sa.Column("publication_date", sa.Date()),
        sa.Column("grant_date", sa.Date()),
        sa.Column("expiry_date", sa.Date()),
        sa.Column("logo_url", sa.Text()),
        sa.Column("timeline", JSONB()),
        sa.Column("raw", JSONB()),
        sa.Column("source_url", sa.Text()),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("content_hash", sa.Text()),
        sa.Column("parse_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_domestic_records_status_code", "domestic_records", ["status_code"])
    op.create_index("ix_domestic_records_expiry_date", "domestic_records", ["expiry_date"])
    op.execute(
        "CREATE INDEX ix_domestic_records_vienna_codes "
        "ON domestic_records USING gin (vienna_codes)"
    )


def downgrade() -> None:
    op.drop_table("domestic_records")
