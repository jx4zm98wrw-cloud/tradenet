"""Admin control for the domestic enrichment sweep (RQ job).

State machine: idle → running → (paused ⇄ running) → idle (stop). Every illegal
transition is a 409. Enqueueing the first/next chunk is isolated in
_enqueue_chunk so it can be monkeypatched in tests (no redis/worker needed).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, require_admin
from ..db import get_session
from ..db.models import DomesticSweepControl

router = APIRouter(prefix="/api/v1/admin/domestic-sweep", tags=["admin"])


class SweepControlOut(BaseModel):
    status: str
    cap: int | None
    delay: float
    jitter: float
    chunk_size: int
    processed: int
    ok: int
    failed: int
    current_appno: str | None
    next_appno: str | None
    last_error: str | None
    started_at: datetime | None
    updated_at: datetime

    model_config = {"from_attributes": True}


class CadenceBody(BaseModel):
    cap: int | None = None
    delay: float | None = None
    jitter: float | None = None
    chunk_size: int | None = None


def _enqueue_chunk() -> None:
    from redis import Redis
    from rq import Queue

    from worker.domestic_sweep import JOB_TIMEOUT, QUEUE_NAME, run_sweep_chunk

    from ..settings import get_settings

    Queue(QUEUE_NAME, connection=Redis.from_url(get_settings().redis_url)).enqueue(
        run_sweep_chunk, job_timeout=JOB_TIMEOUT
    )


async def _row(session: AsyncSession) -> DomesticSweepControl:
    return (
        await session.execute(select(DomesticSweepControl).where(DomesticSweepControl.id == 1))
    ).scalar_one()


def _now() -> datetime:
    return datetime.now(UTC)


@router.get("", response_model=SweepControlOut)
async def get_status(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticSweepControl:
    return await _row(session)


@router.post("/start", response_model=SweepControlOut)
async def start(
    body: CadenceBody,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticSweepControl:
    row = await _row(session)
    if row.status != "idle":
        raise HTTPException(409, f"sweep is {row.status}; stop it before starting a new run")
    row.status = "running"
    row.processed = row.ok = row.failed = 0
    row.current_appno = None
    row.next_appno = None
    row.last_error = None
    row.started_at = _now()
    if body.cap is not None:
        row.cap = body.cap
    if body.delay is not None:
        row.delay = body.delay
    if body.jitter is not None:
        row.jitter = body.jitter
    if body.chunk_size is not None:
        row.chunk_size = body.chunk_size
    row.updated_at = _now()
    await session.commit()
    _enqueue_chunk()
    return await _row(session)


@router.post("/pause", response_model=SweepControlOut)
async def pause(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticSweepControl:
    row = await _row(session)
    if row.status != "running":
        raise HTTPException(409, f"sweep is {row.status}; only a running sweep can be paused")
    row.status = "paused"
    row.updated_at = _now()
    await session.commit()
    return row


@router.post("/resume", response_model=SweepControlOut)
async def resume(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticSweepControl:
    row = await _row(session)
    if row.status != "paused":
        raise HTTPException(409, f"sweep is {row.status}; only a paused sweep can be resumed")
    row.status = "running"
    row.updated_at = _now()
    await session.commit()
    _enqueue_chunk()
    return await _row(session)


@router.post("/stop", response_model=SweepControlOut)
async def stop(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticSweepControl:
    row = await _row(session)
    if row.status not in ("running", "paused"):
        raise HTTPException(409, f"sweep is {row.status}; nothing to stop")
    row.status = "idle"
    row.current_appno = None
    row.next_appno = None
    row.updated_at = _now()
    await session.commit()
    return row


@router.patch("/config", response_model=SweepControlOut)
async def config(
    body: CadenceBody,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticSweepControl:
    row = await _row(session)
    if body.cap is not None:
        row.cap = body.cap
    if body.delay is not None:
        row.delay = body.delay
    if body.jitter is not None:
        row.jitter = body.jitter
    if body.chunk_size is not None:
        row.chunk_size = body.chunk_size
    row.updated_at = _now()
    await session.commit()
    return row
