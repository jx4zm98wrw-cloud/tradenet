"""Gazette routes — upload PDFs, list status."""
from __future__ import annotations
import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import Gazette, GazetteStatus, GazetteType, get_session
from ..schemas import GazetteListOut, GazetteOut
from ..settings import get_settings


router = APIRouter(prefix="/api/gazettes", tags=["gazettes"])


def _gazette_out(g: Gazette) -> GazetteOut:
    """GazetteOut with mocked OCR metrics. Deterministic per sha256 so a
    given gazette consistently flags or doesn't across reloads. Until the
    real OCR pipeline lands, ~1 in 4 gazettes gets a "needs review" warning."""
    h = int(g.sha256[:8], 16) if g.sha256 else 0
    confidence = round(0.78 + (h % 220) / 1000.0, 2)  # 0.78–1.00
    flagged = (h % 50) if confidence < 0.85 else 0    # only flag below threshold
    needs_review = flagged > 0
    out = GazetteOut.model_validate(g)
    out.ocr_confidence = confidence
    out.flagged_row_count = flagged
    out.needs_review = needs_review
    return out


def _parse_filename_meta(filename: str) -> tuple[GazetteType, Optional[int], Optional[int]]:
    import re
    m = re.match(r"^([ABab])_T(\d+)_(\d{4})", filename)
    letter = filename[:1].upper() if filename else "A"
    gtype = GazetteType.B if letter == "B" else GazetteType.A
    if m:
        return gtype, int(m.group(2)), int(m.group(3))
    return gtype, None, None


@router.post("", response_model=GazetteOut, status_code=status.HTTP_201_CREATED)
async def upload_gazette(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
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

    # Stream to disk under a temp name, hashing as we go.
    tmp_id = uuid.uuid4().hex
    tmp_path = settings.upload_dir / f"{tmp_id}.pdf.part"
    sha = hashlib.sha256()
    size = 0
    try:
        with tmp_path.open("wb") as out:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                sha.update(chunk)
                size += len(chunk)
                out.write(chunk)
    finally:
        await file.close()

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

    gazette_type, issue_num, issue_year = _parse_filename_meta(safe_name)
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
            "worker.ingest.ingest_pdf", str(g.id), job_timeout=3600,
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
    status_filter: Optional[GazetteStatus] = None,
    limit: int = 50,
    offset: int = 0,
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
