"""Gazette routes — upload PDFs, list status."""

import hashlib
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .._filename import parse_filename_meta
from ..auth import User, require_user
from ..db import Gazette, GazetteStatus, get_session
from ..rate_limit import limiter
from ..schemas import GazetteListOut, GazetteOut
from ..settings import get_settings

router = APIRouter(prefix="/api/v1/gazettes", tags=["gazettes"])


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
    user: User = Depends(require_user),
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
    try:
        from redis import Redis
        from rq import Queue

        redis = Redis.from_url(settings.redis_url)
        Queue("ingest", connection=redis).enqueue(
            "worker.ingest.ingest_pdf",
            str(g.id),
            job_timeout=3600,
        )
    except Exception:
        # Surface in error_message but don't fail the upload.
        g.error_message = "Redis unavailable; ingest not enqueued"
        session.add(g)
        await session.commit()
        await session.refresh(g)

    return _gazette_out(g)


@router.get("", response_model=GazetteListOut)
async def list_gazettes(
    status_filter: GazetteStatus | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> GazetteListOut:
    q = select(Gazette)
    cq = select(func.count()).select_from(Gazette)
    if status_filter is not None:
        q = q.where(Gazette.status == status_filter)
        cq = cq.where(Gazette.status == status_filter)
    q = q.order_by(Gazette.uploaded_at.desc()).limit(limit).offset(offset)
    items = (await session.execute(q)).scalars().all()
    total = (await session.execute(cq)).scalar_one()
    return GazetteListOut(
        items=[_gazette_out(g) for g in items],
        total=total,
    )


@router.get("/{gazette_id}", response_model=GazetteOut)
async def get_gazette(gazette_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> GazetteOut:
    g = await session.get(Gazette, gazette_id)
    if g is None:
        raise HTTPException(404, "Gazette not found")
    return _gazette_out(g)
