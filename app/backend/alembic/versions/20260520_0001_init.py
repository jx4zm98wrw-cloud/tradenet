"""init: gazettes + trademarks

Revision ID: 20260520_0001
Revises:
Create Date: 2026-05-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "20260520_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Define enums and create them once here; pass create_type=False to the column
    # references below so SQLAlchemy doesn't try to CREATE TYPE a second time.
    gazette_type = postgresql.ENUM("A", "B", name="gazette_type", create_type=False)
    gazette_status = postgresql.ENUM(
        "uploaded", "processing", "completed", "failed",
        name="gazette_status", create_type=False,
    )
    record_type = postgresql.ENUM(
        "A", "B_domestic", "B_madrid", name="record_type", create_type=False,
    )
    op.execute("CREATE TYPE gazette_type AS ENUM ('A', 'B')")
    op.execute("CREATE TYPE gazette_status AS ENUM ('uploaded', 'processing', 'completed', 'failed')")
    op.execute("CREATE TYPE record_type AS ENUM ('A', 'B_domestic', 'B_madrid')")

    op.create_table(
        "gazettes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("gazette_type", gazette_type, nullable=False),
        sa.Column("issue_year", sa.Integer(), nullable=True),
        sa.Column("issue_number", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", gazette_status, nullable=False, server_default="uploaded"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.String(255), nullable=True),
        sa.UniqueConstraint("sha256", name="uq_gazettes_sha256"),
    )
    op.create_index("ix_gazettes_sha256", "gazettes", ["sha256"])
    op.create_index("ix_gazettes_status", "gazettes", ["status"])
    op.create_index("ix_gazettes_issue_year", "gazettes", ["issue_year"])

    op.create_table(
        "trademarks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gazette_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", record_type, nullable=False),
        sa.Column("application_number", sa.String(64), nullable=True),
        sa.Column("certificate_number", sa.String(64), nullable=True),
        sa.Column("madrid_number", sa.String(64), nullable=True),
        sa.Column("submission_date", sa.Date(), nullable=True),
        sa.Column("publication_date_441", sa.Date(), nullable=True),
        sa.Column("publication_date_450", sa.Date(), nullable=True),
        sa.Column("registration_date_151", sa.Date(), nullable=True),
        sa.Column("renewal_date_156", sa.Date(), nullable=True),
        sa.Column("expiry_date_141", sa.Date(), nullable=True),
        sa.Column("expiry_date_181", sa.Date(), nullable=True),
        sa.Column("validity_171", sa.String(64), nullable=True),
        sa.Column("validity_176", sa.String(64), nullable=True),
        sa.Column("month", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("nice_classes", postgresql.ARRAY(sa.String(8)), nullable=True),
        sa.Column("nice_total", sa.Integer(), nullable=True),
        sa.Column("nice_group_number", sa.String(32), nullable=True),
        sa.Column("raw_511_text", sa.Text(), nullable=True),
        sa.Column("vienna_codes", postgresql.ARRAY(sa.String(16)), nullable=True),
        sa.Column("raw_531_text", sa.Text(), nullable=True),
        sa.Column("mark_sample", sa.Text(), nullable=True),
        sa.Column("mark_status", sa.Text(), nullable=True),
        sa.Column("protected_colors", sa.Text(), nullable=True),
        sa.Column("priority_300", sa.Text(), nullable=True),
        sa.Column("related_app_641", sa.Text(), nullable=True),
        sa.Column("origin_822", sa.Text(), nullable=True),
        sa.Column("territory_831", sa.Text(), nullable=True),
        sa.Column("applicant_raw_731", sa.Text(), nullable=True),
        sa.Column("owner_raw_732", sa.Text(), nullable=True),
        sa.Column("applicant_name", sa.Text(), nullable=True),
        sa.Column("applicant_address", sa.Text(), nullable=True),
        sa.Column("applicant_country_code", sa.String(2), nullable=True),
        sa.Column("applicant_city", sa.String(128), nullable=True),
        sa.Column("applicant_type", sa.String(16), nullable=True),
        sa.Column("ip_agency_raw_740", sa.Text(), nullable=True),
        sa.Column("ip_agency", sa.String(64), nullable=True),
        sa.Column("ip_agency_status", sa.String(64), nullable=True),
        sa.Column("extra_markers", postgresql.JSONB(), nullable=True),
        sa.Column("gazette_ref_field", sa.String(8), nullable=True),
        sa.Column("date_combined", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["gazette_id"], ["gazettes.id"], ondelete="CASCADE"),
    )

    op.create_index("ix_trademarks_gazette_id", "trademarks", ["gazette_id"])
    op.create_index("ix_trademarks_record_type", "trademarks", ["record_type"])
    op.create_index("ix_trademarks_application_number", "trademarks", ["application_number"])
    op.create_index("ix_trademarks_certificate_number", "trademarks", ["certificate_number"])
    op.create_index("ix_trademarks_madrid_number", "trademarks", ["madrid_number"])
    op.create_index("ix_trademarks_country_code", "trademarks", ["applicant_country_code"])
    op.create_index("ix_trademarks_city", "trademarks", ["applicant_city"])
    op.create_index("ix_trademarks_applicant_type", "trademarks", ["applicant_type"])
    op.create_index("ix_trademarks_applicant_name", "trademarks", ["applicant_name"])
    op.create_index("ix_trademarks_ip_agency", "trademarks", ["ip_agency"])
    op.create_index("ix_trademarks_month", "trademarks", ["month"])
    op.create_index("ix_trademarks_year", "trademarks", ["year"])
    # GIN index on nice_classes for `WHERE '35' = ANY(nice_classes)` filters.
    op.execute("CREATE INDEX ix_trademarks_nice_classes_gin ON trademarks USING GIN (nice_classes)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_trademarks_nice_classes_gin")
    op.drop_table("trademarks")
    op.drop_table("gazettes")
    postgresql.ENUM(name="record_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="gazette_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="gazette_type").drop(op.get_bind(), checkfirst=True)
