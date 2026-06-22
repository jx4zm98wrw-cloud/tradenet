"""Gazette routes — upload PDFs, list status, overview analytics."""

import hashlib
import re
import uuid
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .._filename import parse_filename_meta
from ..auth import User, require_admin, require_role
from ..db import Gazette, GazetteStatus, Trademark, get_session
from ..db.models import MadridRecord, UserRole
from ..rate_limit import limiter
from ..schemas import (
    CountryCount,
    Coverage,
    GazetteListOut,
    GazetteOut,
    GazetteOverviewOut,
    GazetteYearSummaryRow,
    MissingIssue,
    NamedCount,
    PerYearStreams,
    StatusBreakdown,
    StreamTotals,
    TopApplicants,
    TopRepresentatives,
)
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/gazettes", tags=["gazettes"])

# Domestic = applications + registrations; Madrid = registrations + renewals.
# These are the ONLY classifier — never `record_type` (which mislabels
# 111-only madrid_registration rows as B_domestic).
_DOMESTIC_CATEGORIES = ("domestic_application", "domestic_registration")
_MADRID_CATEGORIES = ("madrid_registration", "madrid_renewal")

# NOIP gazettes ship ~24 issues/year (2 per month). Used for coverage math.
_EXPECTED_ISSUES_PER_YEAR = 24
_MAX_MISSING_LISTED = 50

# Leading Vietnamese law-firm legal prefix, stripped before grouping domestic
# representatives. INTERIM (see TODO below).
_REP_PREFIX_RE = re.compile(r"^công ty (luật )?(tnhh|cổ phần) ")
_WS_RE = re.compile(r"\s+")
# First digit-run or comma — Madrid `representative` concatenates the firm name
# with its postal address; we trim at that boundary. INTERIM.
_MADRID_REP_TRIM_RE = re.compile(r"[,]|\d")


def _normalize_rep(raw: str) -> str:
    """INTERIM domestic-representative normalization: casefold, collapse
    whitespace, strip a leading `Công ty (Luật) TNHH|Cổ phần` legal prefix.

    TODO(task_057fcd61): full canonicalization — cluster near-duplicate firm
    variants (punctuation/casing/whitespace drift) to a stored canonical key.
    """
    s = _WS_RE.sub(" ", raw).strip().casefold()
    s = _REP_PREFIX_RE.sub("", s)
    return s.strip()


def _trim_madrid_rep(raw: str) -> str:
    """INTERIM Madrid-representative trim: take the firm name up to the first
    digit-run / address token, casefolded + whitespace-collapsed.

    TODO(task_057fcd61): full canonicalization.
    """
    head = _MADRID_REP_TRIM_RE.split(raw, maxsplit=1)[0]
    return _WS_RE.sub(" ", head).strip().casefold()


def _get_upload_limit() -> str:
    return get_settings().rate_limit_upload


def _gazette_out(g: Gazette) -> GazetteOut:
    """GazetteOut. The OCR metrics (`ocr_confidence`, `flagged_row_count`,
    `needs_review`) are left at their schema defaults (None / None / False)
    until a real OCR pipeline lands and the worker populates them per row.

    The previous implementation derived md5-based pseudo-random values from
    the gazette's sha256, which the admin UI then rendered as
    `OCR confidence 0.83 — N rows flagged for review`. A reviewer would
    treat that as actionable QA data — but the numbers were fabricated.
    Showing nothing is more honest than showing a fake number.
    """
    out = GazetteOut.model_validate(g)
    out.ocr_confidence = None
    out.flagged_row_count = None
    out.needs_review = False
    return out


@router.post("", response_model=GazetteOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(_get_upload_limit)
async def upload_gazette(
    request: Request,  # required for slowapi
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    # Admins + editors can upload; viewers cannot (read-only role).
    # Ingest spins up worker jobs, image extraction, and DB writes — mutating
    # operations should never be reachable by viewer accounts.
    user: User = Depends(require_role(UserRole.admin, UserRole.editor)),
) -> GazetteOut:
    """Upload a PDF — stores on disk, persists a Gazette row, enqueues ingest.

    Returns the persisted Gazette (status='uploaded'). The actual extraction
    runs asynchronously via the RQ worker; clients poll GET /api/gazettes for
    status transitions to 'processing' / 'completed' / 'failed'.

    Idempotent on sha256 — if the same file content already exists, returns the
    existing row.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only .pdf uploads are accepted.")

    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = settings.max_upload_bytes

    # Stream to disk under a temp name, hashing as we go. Enforce the size cap
    # while streaming so a malicious client can't exhaust disk before we react.
    tmp_id = uuid.uuid4().hex
    tmp_path = settings.upload_dir / f"{tmp_id}.pdf.part"
    sha = hashlib.sha256()
    size = 0
    first_chunk: bytes | None = None
    try:
        with tmp_path.open("wb") as out:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                if first_chunk is None:
                    first_chunk = chunk[:8]
                sha.update(chunk)
                size += len(chunk)
                if size > max_bytes:
                    tmp_path.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"File exceeds {max_bytes // (1024 * 1024)} MB upload limit",
                    )
                out.write(chunk)
    finally:
        await file.close()

    # Magic-byte check — PDFs start with "%PDF-". Cheap defense vs. polyglot
    # files dressed up with a .pdf extension.
    if not first_chunk or not first_chunk.startswith(b"%PDF-"):
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(400, "File does not appear to be a PDF (missing %PDF- header)")

    digest = sha.hexdigest()

    # Dedup check by sha256.
    existing = (await session.execute(select(Gazette).where(Gazette.sha256 == digest))).scalar_one_or_none()
    if existing is not None:
        tmp_path.unlink(missing_ok=True)
        return _gazette_out(existing)

    # Final filename uses the original name (preserved verbatim).
    safe_name = Path(file.filename).name
    final_path = settings.upload_dir / f"{digest[:16]}_{safe_name}"
    tmp_path.rename(final_path)

    gazette_type, issue_num, issue_year = parse_filename_meta(safe_name)
    g = Gazette(
        id=uuid.uuid4(),
        filename=safe_name,
        sha256=digest,
        gazette_type=gazette_type,
        issue_year=issue_year,
        issue_number=issue_num,
        storage_path=str(final_path),
        size_bytes=size,
        status=GazetteStatus.uploaded,
        uploaded_by=user.id,
    )
    session.add(g)
    await session.commit()
    await session.refresh(g)

    # Enqueue ingest. If Redis isn't reachable we still return 201 — the row is
    # there in status='uploaded' and can be re-queued.
    #
    # Retry policy: 3 attempts (1 initial + 2 retries) with 10-minute backoff.
    # Catches transient failures (transient Postgres unavailability, Redis
    # hiccup mid-job, image extractor OOM on a single page). After 3 failed
    # attempts the job moves to RQ's "failed" registry where it's retained
    # for forensics; an operator can re-queue manually from /admin/gazettes
    # or run `rq requeue --queue ingest <job_id>`.
    #
    # The 3600s job_timeout caps a single attempt's wall time — long enough
    # for the largest gazette in the corpus (B_T4 at ~10 min wall time on
    # commodity hardware), short enough to free the worker if a job hangs.
    try:
        from redis import Redis
        from rq import Queue, Retry

        redis = Redis.from_url(settings.redis_url)
        Queue("ingest", connection=redis).enqueue(
            "worker.ingest.ingest_pdf",
            str(g.id),
            job_timeout=3600,
            retry=Retry(max=2, interval=[600, 1800]),  # 10 min, then 30 min
            failure_ttl=86400 * 7,  # keep failed jobs for 7 days for forensics
            result_ttl=86400,  # keep results 1 day (mainly for debugging)
        )
    except Exception:
        # Surface in error_message but don't fail the upload.
        g.error_message = "Redis unavailable; ingest not enqueued"
        session.add(g)
        await session.commit()
        await session.refresh(g)

    return _gazette_out(g)


@router.get("", response_model=GazetteListOut | list[GazetteYearSummaryRow])
async def list_gazettes(
    status_filter: GazetteStatus | None = None,
    year: int | None = Query(None, description="Filter to a single issue_year."),
    gazette_type: str | None = Query(None, description="Filter by gazette type (A/B)."),
    status: str | None = Query(None, description="Filter by gazette status."),
    summary: Literal["years"] | None = Query(
        None,
        description="When 'years', return per-year {year, issue_count, marks, flagged} "
        "rows for the accordion headers instead of the paginated row list.",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    # Admin-only — this endpoint feeds /admin/gazettes, exposes per-issue
    # OCR confidence, error messages, raw filenames, and processing
    # internals. Defense-in-depth alongside the client-side gate.
    _admin: User = Depends(require_admin),
) -> GazetteListOut | list[GazetteYearSummaryRow]:
    # Resolve the optional `status` (string) filter on top of the legacy
    # `status_filter` (enum) param — both narrow the same column; coalesce.
    status_val = status_filter
    if status is not None:
        try:
            status_val = GazetteStatus(status)
        except ValueError as exc:
            raise HTTPException(422, f"Invalid status: {status!r}") from exc

    type_val: str | None = None
    if gazette_type is not None:
        type_val = gazette_type.upper()
        if type_val not in ("A", "B"):
            raise HTTPException(422, f"Invalid gazette_type: {gazette_type!r}")

    def _apply_filters(stmt):
        if status_val is not None:
            stmt = stmt.where(Gazette.status == status_val)
        if year is not None:
            stmt = stmt.where(Gazette.issue_year == year)
        if type_val is not None:
            stmt = stmt.where(Gazette.gazette_type == type_val)
        return stmt

    # --- Years-summary mode: one row per issue_year for the accordion. -------
    if summary == "years":
        marks_per_gazette = (
            select(
                Trademark.gazette_id.label("gid"),
                func.count().label("marks"),
            )
            .group_by(Trademark.gazette_id)
            .subquery()
        )
        sq = (
            select(
                Gazette.issue_year.label("year"),
                func.count(distinct(Gazette.id)).label("issue_count"),
                func.coalesce(func.sum(marks_per_gazette.c.marks), 0).label("marks"),
            )
            .select_from(Gazette)
            .outerjoin(marks_per_gazette, marks_per_gazette.c.gid == Gazette.id)
            .where(Gazette.issue_year.is_not(None))
        )
        sq = _apply_filters(sq).group_by(Gazette.issue_year).order_by(Gazette.issue_year.desc())
        rows = (await session.execute(sq)).all()
        return [
            GazetteYearSummaryRow(
                year=row.year,
                issue_count=row.issue_count,
                marks=int(row.marks),
                # No real review pipeline yet — see StatusBreakdown.flagged.
                flagged=0,
            )
            for row in rows
        ]

    # --- Default mode: paginated row list (unchanged shape). ----------------
    q = _apply_filters(select(Gazette)).order_by(Gazette.uploaded_at.desc()).limit(limit).offset(offset)
    cq = _apply_filters(select(func.count()).select_from(Gazette))
    items = (await session.execute(q)).scalars().all()
    total = (await session.execute(cq)).scalar_one()
    return GazetteListOut(
        items=[_gazette_out(g) for g in items],
        total=total,
    )


@router.get("/overview", response_model=GazetteOverviewOut)
async def gazette_overview(
    session: AsyncSession = Depends(get_session),
    # Admin-only — same gate as list_gazettes; aggregates per-issue internals.
    _admin: User = Depends(require_admin),
) -> GazetteOverviewOut:
    """Read-only analytics for /admin/gazettes — all derived live from the DB.

    Every Domestic/Madrid split keys off `trademarks.mark_category` (the
    generated column), NEVER `record_type`.
    """

    # --- Per-year × stream counts (join trademarks→gazettes on gazette_id) ---
    def _stream(cat: str):
        return func.count().filter(Trademark.mark_category == cat)

    per_year_rows = (
        await session.execute(
            select(
                Gazette.issue_year.label("year"),
                _stream("domestic_application").label("applications"),
                _stream("domestic_registration").label("domestic_registrations"),
                _stream("madrid_registration").label("madrid_registrations"),
                _stream("madrid_renewal").label("madrid_renewals"),
            )
            .join(Trademark, Trademark.gazette_id == Gazette.id)
            .where(Gazette.issue_year.is_not(None))
            .group_by(Gazette.issue_year)
            .order_by(Gazette.issue_year)
        )
    ).all()
    per_year = [
        PerYearStreams(
            year=row.year,
            applications=row.applications,
            domestic_registrations=row.domestic_registrations,
            madrid_registrations=row.madrid_registrations,
            madrid_renewals=row.madrid_renewals,
        )
        for row in per_year_rows
    ]

    totals = StreamTotals(
        applications=sum(r.applications for r in per_year),
        domestic_registrations=sum(r.domestic_registrations for r in per_year),
        madrid_registrations=sum(r.madrid_registrations for r in per_year),
        madrid_renewals=sum(r.madrid_renewals for r in per_year),
        total=sum(
            r.applications + r.domestic_registrations + r.madrid_registrations + r.madrid_renewals
            for r in per_year
        ),
    )

    # --- Status breakdown -----------------------------------------------------
    status_rows = (await session.execute(select(Gazette.status, func.count()).group_by(Gazette.status))).all()
    status_counts = {str(s): n for s, n in status_rows}
    status_breakdown = StatusBreakdown(
        completed=status_counts.get("completed", 0),
        processing=status_counts.get("processing", 0),
        failed=status_counts.get("failed", 0),
        uploaded=status_counts.get("uploaded", 0),
        flagged=0,  # No review pipeline yet (needs_review hardcoded False).
    )

    # --- Coverage: distinct (issue_year, issue_number) present vs expected ----
    present_rows = (
        await session.execute(
            select(Gazette.issue_year, Gazette.issue_number, Gazette.gazette_type)
            .where(Gazette.issue_year.is_not(None))
            .where(Gazette.issue_number.is_not(None))
            .distinct()
        )
    ).all()
    present_pairs = {(y, n) for y, n, _ in present_rows}
    present = len(present_pairs)
    if present_pairs:
        years = {y for y, _ in present_pairs}
        min_y, max_y = min(years), max(years)
        expected = (max_y - min_y + 1) * _EXPECTED_ISSUES_PER_YEAR
        type_by_year = {y: t for y, _, t in present_rows}
        missing: list[MissingIssue] = []
        for yr in range(min_y, max_y + 1):
            for issue in range(1, _EXPECTED_ISSUES_PER_YEAR + 1):
                if (yr, issue) not in present_pairs:
                    missing.append(
                        MissingIssue(
                            year=yr,
                            issue_number=issue,
                            gazette_type=str(type_by_year[yr]) if yr in type_by_year else None,
                        )
                    )
                    if len(missing) >= _MAX_MISSING_LISTED:
                        break
            if len(missing) >= _MAX_MISSING_LISTED:
                break
    else:
        expected = 0
        missing = []
    coverage = Coverage(present=present, expected=expected, missing=missing)

    # --- Madrid origin: top-8 holder countries -------------------------------
    origin_rows = (
        await session.execute(
            select(MadridRecord.holder_country, func.count())
            .where(MadridRecord.holder_country.is_not(None))
            .group_by(MadridRecord.holder_country)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    madrid_origin = [CountryCount(country=c, n=n) for c, n in origin_rows]

    # --- Top applicants (domestic from trademarks; madrid from madrid_records)
    dom_app_rows = (
        await session.execute(
            select(Trademark.applicant_name, func.count())
            .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            .where(Trademark.applicant_name.is_not(None))
            .group_by(Trademark.applicant_name)
            .order_by(func.count().desc())
            .limit(6)
        )
    ).all()
    mad_app_rows = (
        await session.execute(
            select(MadridRecord.holder_name, func.count())
            .where(MadridRecord.holder_name.is_not(None))
            .group_by(MadridRecord.holder_name)
            .order_by(func.count().desc())
            .limit(6)
        )
    ).all()
    top_applicants = TopApplicants(
        domestic=[NamedCount(name=n, n=c) for n, c in dom_app_rows],
        madrid=[NamedCount(name=n, n=c) for n, c in mad_app_rows],
    )

    # --- Top representatives (INTERIM normalization — task_057fcd61) ----------
    dom_rep_raw = (
        (
            await session.execute(
                select(Trademark.ip_agency_raw_740)
                .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
                .where(Trademark.ip_agency_raw_740.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    dom_rep_counts: dict[str, int] = {}
    for raw in dom_rep_raw:
        if raw is None:
            continue
        key = _normalize_rep(raw)
        if key:
            dom_rep_counts[key] = dom_rep_counts.get(key, 0) + 1

    mad_rep_raw = (
        (
            await session.execute(
                select(MadridRecord.representative).where(MadridRecord.representative.is_not(None))
            )
        )
        .scalars()
        .all()
    )
    mad_rep_counts: dict[str, int] = {}
    for raw in mad_rep_raw:
        if raw is None:
            continue
        key = _trim_madrid_rep(raw)
        if key:
            mad_rep_counts[key] = mad_rep_counts.get(key, 0) + 1

    def _top6(counts: dict[str, int]) -> list[NamedCount]:
        ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
        return [NamedCount(name=name, n=n) for name, n in ordered]

    top_representatives = TopRepresentatives(
        domestic=_top6(dom_rep_counts),
        madrid=_top6(mad_rep_counts),
        approximate=True,
    )

    return GazetteOverviewOut(
        per_year=per_year,
        totals=totals,
        status_breakdown=status_breakdown,
        coverage=coverage,
        madrid_origin=madrid_origin,
        top_applicants=top_applicants,
        top_representatives=top_representatives,
    )


@router.get("/{gazette_id}", response_model=GazetteOut)
async def get_gazette(
    gazette_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    # Admin-only for the same reasons as list_gazettes.
    _admin: User = Depends(require_admin),
) -> GazetteOut:
    g = await session.get(Gazette, gazette_id)
    if g is None:
        raise HTTPException(404, "Gazette not found")
    return _gazette_out(g)
