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
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class GazetteType(enum.StrEnum):
    A = "A"  # Applications
    B = "B"  # Registrations


class GazetteStatus(enum.StrEnum):
    uploaded = "uploaded"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class RecordType(enum.StrEnum):
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
    # Per-matter similarity weight overrides (keys: phonetic/visual/class/vienna).
    # NULL → use tm_similarity.DEFAULT_WEIGHTS. Applied when ranking similar
    # marks in this matter's context. See tm_similarity.resolve_weights.
    weights: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

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

    # Composite/extension indexes that can't be expressed via mapped_column(index=True).
    # The two array-GIN indexes power "contains any of …" queries in /search.
    # The two trigram-GIN indexes power ILIKE '%q%' substring search on
    # applicant_name + mark_sample (requires the pg_trgm extension; see
    # migration 20260527_0009).
    __table_args__ = (
        # Speeds /admin/domestic-enrichment's COUNT(DISTINCT application_number)
        # per mark_category: pre-sorted (mark_category, application_number) lets
        # the GroupAggregate stream instead of seq-scan + disk-sort (~850ms ->
        # ~tens of ms at 219k domestic rows). Partial: matches the endpoint's
        # `application_number IS NOT NULL` filter.
        Index(
            "ix_trademarks_markcat_appno",
            "mark_category",
            "application_number",
            postgresql_where=text("application_number IS NOT NULL"),
        ),
        Index(
            "ix_trademarks_nice_classes_gin",
            "nice_classes",
            postgresql_using="gin",
        ),
        Index(
            "ix_trademarks_vienna_codes_gin",
            "vienna_codes",
            postgresql_using="gin",
        ),
        Index(
            "ix_trademarks_applicant_name_trgm",
            "applicant_name",
            postgresql_using="gin",
            postgresql_ops={"applicant_name": "gin_trgm_ops"},
            postgresql_where=text("applicant_name IS NOT NULL"),
        ),
        Index(
            "ix_trademarks_mark_sample_trgm",
            "mark_sample",
            postgresql_using="gin",
            postgresql_ops={"mark_sample": "gin_trgm_ops"},
            postgresql_where=text("mark_sample IS NOT NULL"),
        ),
    )

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
    # Derived classification + lifecycle identity — STORED generated columns
    # (migration 20260617_0015). Pure functions of the (210/111/116) signs above,
    # so they can never drift. Computed(persisted=True) marks them generated, so
    # the ORM reads them and excludes them from INSERT/UPDATE. Indexed in the
    # migration and excluded from alembic drift-check in env.py (Postgres
    # normalises the stored expression vs this string).
    mark_category: Mapped[str] = mapped_column(
        Text,
        Computed(
            "CASE WHEN nullif(application_number,'') IS NOT NULL AND nullif(certificate_number,'') IS NULL "
            "AND nullif(madrid_number,'') IS NULL THEN 'domestic_application' "
            "WHEN nullif(application_number,'') IS NOT NULL AND nullif(certificate_number,'') IS NOT NULL "
            "THEN 'domestic_registration' "
            "WHEN nullif(certificate_number,'') IS NOT NULL AND nullif(application_number,'') IS NULL "
            "AND nullif(madrid_number,'') IS NULL THEN 'madrid_registration' "
            "WHEN nullif(madrid_number,'') IS NOT NULL AND nullif(certificate_number,'') IS NULL "
            "AND nullif(application_number,'') IS NULL THEN 'madrid_renewal' ELSE 'unknown' END",
            persisted=True,
        ),
    )
    lineage_key: Mapped[str | None] = mapped_column(
        Text,
        Computed(
            "COALESCE(nullif(application_number,''), nullif(certificate_number,''), nullif(madrid_number,''))",
            persisted=True,
        ),
    )

    # Dates (publication / registration / validity)
    submission_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # (220)
    publication_date_441: Mapped[date | None] = mapped_column(Date, nullable=True)  # (441)
    publication_date_450: Mapped[date | None] = mapped_column(Date, nullable=True)  # (450)
    registration_date_151: Mapped[date | None] = mapped_column(Date, nullable=True)  # (151)
    vn_grant_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, index=True
    )  # unified VN grant date (domestic grant_date | Madrid vn_grant_date); NULL = not granted
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
    mark_name: Mapped[str | None] = mapped_column(
        Text, nullable=True, index=True
    )  # resolved display name (mark_sample|domestic.mark_text|madrid.mark_text); NULL = figurative
    mark_status: Mapped[str | None] = mapped_column(Text, nullable=True)  # (551)
    protected_colors: Mapped[str | None] = mapped_column(Text, nullable=True)  # (591)
    # Path to the extracted logo PNG, relative to the static root.
    # Populated by the worker once the image extractor has run (Phase 2);
    # remains NULL for rows ingested before image extraction.
    logo_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_phash: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # precomputed hex pHash for the similarity engine (no index — loaded per-row, never queried by)
    logo_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    """'figurative' | 'wordmark' | NULL — specimen routing for the visual axis (Track 1)."""

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

    # Denormalized clean entity names (Phase 2 of entity canonicalization).
    # Resolved by scripts/backfill_entity_clean.py from the trusted source by
    # deterministic identifier (IP VIETNAM→WIPO→gazette). *_clean is the trusted
    # display name; *_norm is norm(*_clean) — the dashboard's GROUP BY key,
    # indexed so /overview groups at any DB size without a per-query join.
    applicant_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_norm: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    representative_clean: Mapped[str | None] = mapped_column(Text, nullable=True)
    representative_norm: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    ip_agency_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Misc passthrough of raw marker text — handy for audit, not for query.
    extra_markers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    gazette_ref_field: Mapped[str | None] = mapped_column(String(8), nullable=True)  # "Gazette" col: A|B
    date_combined: Mapped[str | None] = mapped_column(Text, nullable=True)  # DateCombined_441_450

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    gazette: Mapped[Gazette] = relationship("Gazette", back_populates="trademarks")


class MadridRecord(Base):
    """WIPO Madrid Monitor record, one row per International Registration Number.

    Hybrid storage: promoted scalar/array columns for the fields we filter or
    display, plus JSONB for the nested designation-status / transaction-history
    and the full parsed `raw` payload (never lose data; re-derive without
    re-fetching). Soft-linked to trademarks via `irn = trademarks.lineage_key`.
    """

    __tablename__ = "madrid_records"

    irn: Mapped[str] = mapped_column(Text, primary_key=True)

    holder_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    holder_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    holder_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    holder_legal_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    mark_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    representative: Mapped[str | None] = mapped_column(Text, nullable=True)

    registration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    nice_classes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    # Per-class full goods & services text from WIPO, keyed by Nice class
    # ({"33": "Alcoholic beverages …"}). The gazette only prints a bare class
    # list for Madrid marks, so this is the only source of the full wording.
    goods_services: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    designated_countries: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    basic_registration: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)

    vn_designated: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    vn_status: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    vn_grant_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    vn_refusal_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    designation_status: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    transaction_history: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (
        Index(
            "ix_madrid_records_designated_countries",
            "designated_countries",
            postgresql_using="gin",
        ),
    )


class DomesticRecord(Base):
    """IP VIETNAM domestic trademark detail, one row per application.

    Soft-linked to trademarks via `application_number = trademarks.application_number`.
    Hybrid storage: promoted scalar/array columns for display/filter, JSONB for
    nested goods/timeline + the parsed `raw` payload (re-derive without re-fetch).
    """

    __tablename__ = "domestic_records"

    application_number: Mapped[str] = mapped_column(Text, primary_key=True)

    mark_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    mark_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    applicant_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    representative: Mapped[str | None] = mapped_column(Text, nullable=True)
    colors: Mapped[str | None] = mapped_column(Text, nullable=True)

    nice_classes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    goods_services: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    vienna_codes: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)

    status_code: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    publication_no: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    grant_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)

    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    timeline: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    content_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    parse_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))

    __table_args__ = (
        Index(
            "ix_domestic_records_vienna_codes",
            "vienna_codes",
            postgresql_using="gin",
        ),
    )


class DomesticNotFound(Base):
    """Negative cache for domestic application numbers IP VIETNAM has no published
    detail for yet (HTTP 200 + skeleton page, no `product-form-label` marker).

    A definitive "not published yet", not flakiness — stable across dozens of
    attempts. Recording it lets the sweep skip the mark for a backoff window so
    it can't re-retry the same unresolvable marks every chunk (the stably-ordered
    front of the work-list, which was tripping the circuit breaker). After the
    window the sweep re-checks, picking the mark up once IP VIETNAM publishes it.
    """

    __tablename__ = "domestic_not_found"

    application_number: Mapped[str] = mapped_column(Text, primary_key=True)
    vnid: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    check_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))


class UserRole(enum.StrEnum):
    """RBAC roles. Sorted from most privileged to least.

    - admin   — full access; can create users, reprocess gazettes, see audit
    - editor  — can create/modify watchlists, upload gazettes
    - viewer  — read-only access to search/marks/today; cannot mutate
    """

    admin = "admin"
    editor = "editor"
    viewer = "viewer"


class User(Base):
    """Application user. Email + bcrypt-hashed password + RBAC role.

    No external IdP for v1 — local password auth signs HS256 JWTs with the
    same TM_SECRET_KEY used elsewhere in the app. Future: SSO via OAuth/OIDC
    can land as an alternative login path without changing the User schema.
    """

    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("email", name="uq_users_email"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    # bcrypt hash — passlib produces "$2b$..." prefix; ~60 chars.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), nullable=False, default=UserRole.viewer, index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Token revocation: incrementing counter so refresh tokens issued before
    # a logout/password-change are rejected. Stored as Postgres BIGINT so we
    # never wrap (default 0 = no revocations yet).
    token_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class TmNameIndex(Base):
    """IP VIETNAM wordmark reference table — see migration 0011 for the full rationale.

    Out-of-band index from the IP VIETNAM applicant-name extract, keyed by
    application number, used by `scripts/enrich_mark_samples.py` to fill
    missing `mark_sample` values in `trademarks`. Not linked by FK to
    `gazettes` — the CSV has no per-PDF provenance and many of its rows
    are for filings we'll never see in gazettes we ingest. This table is
    therefore *not* part of the application's hot-path query surface; the
    ORM mapping exists only so `alembic check` sees a corresponding model
    for the migration-created table.

    The trigram + date indexes are declared in the migration itself
    (CREATE INDEX) rather than via SQLAlchemy `Index()` because they use
    Postgres-specific opclasses (`gin_trgm_ops`) that aren't first-class
    in SQLAlchemy's index API. `alembic check` is willing to ignore index
    diffs that look like raw-SQL-only constructs, but for safety we keep
    the model's Index() declarations matching the migration shape.
    """

    __tablename__ = "tm_name_index"
    __table_args__ = (
        # Trigram GIN to make this table usable for fuzzy search across the
        # full ~770k mark corpus down the road. The opclass is set in the
        # migration; SQLAlchemy here just records the column it covers so
        # autogenerate sees the index exists.
        Index(
            "ix_tm_name_index_mark_trgm",
            "mark_sample",
            postgresql_using="gin",
            postgresql_ops={"mark_sample": "gin_trgm_ops"},
        ),
        Index("ix_tm_name_index_submission_date", "submission_date"),
    )

    application_number: Mapped[str] = mapped_column(String(64), primary_key=True)
    submission_date: Mapped[date | None] = mapped_column(Date)
    mark_sample: Mapped[str] = mapped_column(Text, nullable=False)


class MadridSweepControl(Base):
    """Singleton (id=1) control + live state for the Madrid enrichment sweep.

    Written by the RQ job (worker.madrid_sweep) and the admin control endpoints;
    read by the /admin/madrid panel. Derived coverage counts stay on the
    /madrid-enrichment endpoint — this row is process/control state only.
    """

    __tablename__ = "madrid_sweep_control"
    __table_args__ = (
        CheckConstraint(
            "status IN ('idle','running','paused','stopping')",
            name="ck_madrid_sweep_status",
        ),
        CheckConstraint(
            "mode IN ('normal','fast')",
            name="ck_madrid_sweep_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="idle")
    cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delay: Mapped[float] = mapped_column(Float, nullable=False, server_default="8.0")
    jitter: Mapped[float] = mapped_column(Float, nullable=False, server_default="2.0")
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="25")
    processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="normal")
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_irn: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_irn: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class DomesticSweepControl(Base):
    """Singleton (id=1) control + live state for the domestic enrichment sweep.

    Written by the RQ job (worker.domestic_sweep) and the admin control
    endpoints; read by the /admin/domestic panel. Derived coverage counts stay
    on the /domestic-enrichment endpoint — this row is process/control state only.
    """

    __tablename__ = "domestic_sweep_control"
    __table_args__ = (
        CheckConstraint(
            "status IN ('idle','running','paused','stopping')",
            name="ck_domestic_sweep_status",
        ),
        CheckConstraint(
            "mode IN ('normal','dead')",
            name="ck_domestic_sweep_mode",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="idle")
    cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delay: Mapped[float] = mapped_column(Float, nullable=False, server_default="5.0")
    jitter: Mapped[float] = mapped_column(Float, nullable=False, server_default="2.0")
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="25")
    processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Definitive negatives recorded this run (IP VIETNAM 200 + skeleton). Tracked apart
    # from `failed` so the de-wedged sweep is observable: ok + not_found climb
    # while failed stays flat once the not-published front is being recorded.
    not_found: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="normal")
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_appno: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_appno: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
