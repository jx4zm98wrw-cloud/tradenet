"""SQLAlchemy models for the trademark gazette database.

Design notes
------------
One `gazettes` row per uploaded PDF, one `trademarks` row per extracted section.
B-files produce both `B_domestic` (111) and `B_madrid` (116) record types in the
same `trademarks` table — the `record_type` enum distinguishes them so search
queries can filter on the schema without joining.

Nice classes (511) and Vienna codes (531) are stored both as raw text (full
fidelity) and as parsed arrays (`text[]`) for filter queries. The raw_511_text
column can exceed Excel's 32k-char limit; Postgres TEXT is unbounded so the
overflow workaround that the CSV writer uses is unnecessary here.
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GazetteType(str, enum.Enum):
    A = "A"  # Applications
    B = "B"  # Registrations


class GazetteStatus(str, enum.Enum):
    uploaded = "uploaded"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class RecordType(str, enum.Enum):
    A = "A"  # A-file application row
    B_domestic = "B_domestic"  # B-file (111) domestic registration
    B_madrid = "B_madrid"  # B-file (116) Madrid international registration


class Gazette(Base):
    __tablename__ = "gazettes"
    __table_args__ = (UniqueConstraint("sha256", name="uq_gazettes_sha256"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    gazette_type: Mapped[GazetteType] = mapped_column(
        SAEnum(GazetteType, name="gazette_type"), nullable=False
    )
    # From filename pattern A_T<n>_<YYYY>.pdf — best effort, nullable.
    issue_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    issue_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)  # absolute path on disk
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[GazetteStatus] = mapped_column(
        SAEnum(GazetteStatus, name="gazette_status"),
        nullable=False,
        default=GazetteStatus.uploaded,
        index=True,
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(255), nullable=True)  # placeholder until auth

    trademarks: Mapped[list[Trademark]] = relationship(
        "Trademark",
        back_populates="gazette",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Watchlist(Base):
    """A standing query re-run automatically on each new gazette issue.

    `query` stores the full filter set (the same shape the Search page sends to
    /api/search) so we can re-execute against future gazettes. `query_desc` is
    the human-readable summary shown on the dashboard. `total_count` and
    `new_count` are cached aggregates updated whenever the query is re-run.
    """

    __tablename__ = "watchlists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    client: Mapped[str | None] = mapped_column(String(256), nullable=True)
    matter: Mapped[str | None] = mapped_column(String(64), nullable=True)
    query: Mapped[dict] = mapped_column(JSONB, nullable=False)
    query_desc: Mapped[str | None] = mapped_column(Text, nullable=True)

    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    owner_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Trademark(Base):
    __tablename__ = "trademarks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    gazette_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("gazettes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_type: Mapped[RecordType] = mapped_column(
        SAEnum(RecordType, name="record_type"), nullable=False, index=True
    )

    # Identifiers — exactly one is non-null per row, depending on record_type.
    application_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # (210)
    certificate_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # (111)
    madrid_number: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)  # (116)

    # Dates (publication / registration / validity)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # (220)
    publication_date_441: Mapped[date | None] = mapped_column(Date, nullable=True)  # (441)
    publication_date_450: Mapped[date | None] = mapped_column(Date, nullable=True)  # (450)
    registration_date_151: Mapped[date | None] = mapped_column(Date, nullable=True)  # (151)
    renewal_date_156: Mapped[date | None] = mapped_column(Date, nullable=True)  # (156)
    expiry_date_141: Mapped[date | None] = mapped_column(Date, nullable=True)  # (141)
    expiry_date_181: Mapped[date | None] = mapped_column(Date, nullable=True)  # (181)
    validity_171: Mapped[str | None] = mapped_column(String(64), nullable=True)  # (171) e.g. "10 năm"
    validity_176: Mapped[str | None] = mapped_column(String(64), nullable=True)  # (176)

    # Derived month/year for cheap date-range filtering (mirrors CSV columns).
    month: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Classifications
    nice_classes: Mapped[list[str] | None] = mapped_column(ARRAY(String(8)), nullable=True)  # (511) parsed
    nice_total: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Total Group
    nice_group_number: Mapped[str | None] = mapped_column(Text, nullable=True)  # Group Number
    raw_511_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    vienna_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String(16)), nullable=True)  # (531) parsed
    raw_531_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Mark
    mark_sample: Mapped[str | None] = mapped_column(Text, nullable=True)  # (540) — case preserved
    mark_status: Mapped[str | None] = mapped_column(Text, nullable=True)  # (551)
    protected_colors: Mapped[str | None] = mapped_column(Text, nullable=True)  # (591)

    # Priority / related
    priority_300: Mapped[str | None] = mapped_column(Text, nullable=True)  # (300)
    related_app_641: Mapped[str | None] = mapped_column(Text, nullable=True)  # (641)
    origin_822: Mapped[str | None] = mapped_column(Text, nullable=True)
    territory_831: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Applicant / owner
    applicant_raw_731: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_raw_732: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    applicant_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_country_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)
    applicant_city: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    applicant_type: Mapped[str | None] = mapped_column(
        String(16), nullable=True, index=True
    )  # Personal | Company

    # IP Agency
    ip_agency_raw_740: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_agency: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    ip_agency_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Misc passthrough of raw marker text — handy for audit, not for query.
    extra_markers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    gazette_ref_field: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "Gazette" col: A|B
    date_combined: Mapped[str | None] = mapped_column(Text, nullable=True)  # DateCombined_441_450

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    gazette: Mapped[Gazette] = relationship("Gazette", back_populates="trademarks")
