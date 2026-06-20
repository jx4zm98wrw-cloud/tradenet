"""Madrid sweep — chunked, self-re-enqueuing RQ job.

Replaces the hand-launched /tmp resume script. One chunk processes up to
chunk_size uncached IRNs via enrich_one, re-reading the madrid_sweep_control
row each IRN so pause/stop/cadence edits take effect live, then re-enqueues
itself on the `madrid` queue while status stays 'running'.
"""

from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import requests
from redis import Redis
from rq import Queue
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import MadridSweepControl as C
from api.db.session import async_session
from api.settings import get_settings
from madrid_enrich.backfill import iter_madrid_irns
from madrid_enrich.enrich import enrich_one

QUEUE_NAME = "madrid"
_MAX_CONSECUTIVE = 5
# RQ's default job_timeout is 180s — far shorter than one chunk (chunk_size IRNs
# × (delay + jitter) ≈ 250s at defaults). Without this, RQ kills each chunk
# mid-run before it can re-enqueue the next, silently stalling the sweep. Keep
# chunk_size × (delay + jitter) comfortably under this ceiling.
JOB_TIMEOUT = 3600  # seconds (1 hour)


def _cache_dir() -> Path:
    return get_settings().data_dir / "madrid_cache"


def _real_enqueue() -> None:
    redis = Redis.from_url(get_settings().redis_url)
    Queue(QUEUE_NAME, connection=redis).enqueue(run_sweep_chunk, job_timeout=JOB_TIMEOUT)


def _pending_count() -> int:
    """Jobs queued (not yet picked up) on this sweep's queue."""
    redis = Redis.from_url(get_settings().redis_url)
    return Queue(QUEUE_NAME, connection=redis).count


def _is_running() -> bool:
    async def _check() -> bool:
        async with async_session() as s:
            return (await s.execute(select(C.status).where(C.id == 1))).scalar_one_or_none() == "running"

    return asyncio.run(_check())


def resume_if_running() -> bool:
    """Boot-time self-heal — see worker.domestic_sweep.resume_if_running. A
    worker restart mid-chunk breaks the self-re-enqueue chain and stalls the
    sweep; on boot we re-enqueue one chunk when the queue is idle, guarded
    against spawning a second parallel chain. Returns True if it enqueued."""
    if _pending_count() > 0 or not _is_running():
        return False
    _real_enqueue()
    return True


async def _ctl(session: AsyncSession) -> dict:
    """Snapshot the control row as a plain dict (no ORM identity to expire)."""
    row = (
        await session.execute(
            select(
                C.status,
                C.cap,
                C.delay,
                C.jitter,
                C.chunk_size,
                C.processed,
                C.ok,
                C.failed,
            ).where(C.id == 1)
        )
    ).one()
    return dict(row._mapping)


async def _set(session: AsyncSession, **vals) -> None:
    vals["updated_at"] = datetime.now(UTC)
    await session.execute(update(C).where(C.id == 1).values(**vals))
    await session.commit()


async def run_chunk(
    session: AsyncSession,
    *,
    enqueue_next: Callable[[], None] = _real_enqueue,
    http_session: requests.Session | None = None,
) -> dict:
    """Process up to chunk_size uncached IRNs honoring live control state."""
    ctl = await _ctl(session)
    if ctl["status"] != "running":
        return {"status": ctl["status"], "did": 0}

    cache = _cache_dir()
    all_irns = await iter_madrid_irns(session)
    cached = {p.stem for p in cache.glob("*.html")}
    todo = [i for i in all_irns if i not in cached]

    http = http_session or requests.Session()
    streak = 0
    did = 0
    for idx, irn in enumerate(todo):
        ctl = await _ctl(session)
        if ctl["status"] != "running":
            break
        # The IRN the worker will fetch after this one (None at the chunk/work tail).
        nxt = todo[idx + 1] if idx + 1 < len(todo) else None
        if ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]:
            await _set(session, status="idle", current_irn=None, next_irn=None)
            break
        try:
            await enrich_one(session, irn, cache, http_session=http, use_cache=True)
            await session.commit()
            await _set(
                session,
                ok=ctl["ok"] + 1,
                processed=ctl["processed"] + 1,
                current_irn=irn,
                next_irn=nxt,
                last_error=None,
            )
            streak = 0
        except Exception as e:
            await session.rollback()
            streak += 1
            await _set(
                session,
                failed=ctl["failed"] + 1,
                processed=ctl["processed"] + 1,
                current_irn=irn,
                next_irn=nxt,
                last_error=str(e)[:300],
            )
        did += 1
        if streak >= _MAX_CONSECUTIVE:
            await _set(session, status="paused", last_error=f"circuit breaker: {streak} consecutive failures")
            break
        if did >= ctl["chunk_size"]:
            break
        time.sleep(ctl["delay"] + random.uniform(0, ctl["jitter"]))

    # Continuation decision.
    ctl = await _ctl(session)
    if ctl["status"] == "stopping":
        await _set(session, status="idle", current_irn=None, next_irn=None)
    elif ctl["status"] == "running":
        cached_now = {p.stem for p in cache.glob("*.html")}
        remaining = [i for i in all_irns if i not in cached_now]
        cap_hit = ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]
        if remaining and not cap_hit:
            enqueue_next()
        else:
            await _set(session, status="idle", current_irn=None, next_irn=None)
    return {"status": ctl["status"], "did": did}


def run_sweep_chunk() -> dict:
    """RQ entry point (sync) — bridges to the async core like worker.ingest."""

    async def _inner() -> dict:
        async with async_session() as s:
            return await run_chunk(s)

    return asyncio.run(_inner())
