"""Domestic sweep — chunked, self-re-enqueuing RQ job.

Mirrors worker.madrid_sweep. One chunk processes up to chunk_size uncached
application numbers via enrich_one, re-reading domestic_sweep_control each item
so pause/stop/cadence edits take effect live, then re-enqueues itself on the
`domestic` queue while status stays 'running'.

NOTE the cache/work-list key mismatch: cache files are named by VNID (the NOIP
fetch id) but the work-list is application_number, so the uncached filter maps
each appno through appno_to_vnid.
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

from api.db.models import DomesticSweepControl as C
from api.db.session import async_session
from api.settings import get_settings
from domestic_enrich.backfill import iter_domestic_appnos
from domestic_enrich.client import NoipBlockedError
from domestic_enrich.enrich import enrich_one
from domestic_enrich.idmap import appno_to_vnid

QUEUE_NAME = "domestic"
_MAX_CONSECUTIVE = 5
JOB_TIMEOUT = 3600  # seconds; chunk_size × (delay + jitter) must stay well under this


def _cache_dir() -> Path:
    return get_settings().data_dir / "domestic_cache"


def _real_enqueue() -> None:
    redis = Redis.from_url(get_settings().redis_url)
    Queue(QUEUE_NAME, connection=redis).enqueue(run_sweep_chunk, job_timeout=JOB_TIMEOUT)


def _pending_count() -> int:
    """Jobs queued (not yet picked up) on this sweep's queue."""
    redis = Redis.from_url(get_settings().redis_url)
    return Queue(QUEUE_NAME, connection=redis).count


def _is_running() -> bool:
    """Read the sweep status with a throwaway SYNC connection. The boot resume
    runs in the worker PARENT process; opening an async connection here binds it
    to a boot-only event loop, and RQ's forked chunk children inherit that
    pooled connection and raise "Future attached to a different loop". A sync
    check (its own NullPool engine) never touches the async pool."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    eng = create_engine(get_settings().database_url_sync, poolclass=NullPool)
    try:
        with eng.connect() as conn:
            status = conn.execute(text(f"SELECT status FROM {C.__tablename__} WHERE id = 1")).scalar()
        return status == "running"
    finally:
        eng.dispose()


def resume_if_running() -> bool:
    """Boot-time self-heal. The sweep is a self-re-enqueuing chunk chain, so a
    worker crash/restart/rebuild mid-chunk kills the in-flight job before it
    enqueues the next one — the chain breaks and the sweep stalls with
    status='running' but an empty queue. On worker boot we re-enqueue one chunk
    to continue, but ONLY when the queue is idle (no pending job), so a normal
    restart can't spawn a second parallel chain (which would double the request
    rate against the same IP). Assumes one worker per sweep queue (the
    recommended topology). Returns True if it enqueued a continuation chunk."""
    if _pending_count() > 0 or not _is_running():
        return False
    _real_enqueue()
    return True


async def _ctl(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            select(
                C.status, C.mode, C.cap, C.delay, C.jitter, C.chunk_size, C.processed, C.ok, C.failed
            ).where(C.id == 1)
        )
    ).one()
    return dict(row._mapping)


async def _set(session: AsyncSession, **vals) -> None:
    vals["updated_at"] = datetime.now(UTC)
    await session.execute(update(C).where(C.id == 1).values(**vals))
    await session.commit()


def _uncached(all_appnos: list[str], cache: Path) -> list[str]:
    cached_vnids = {p.stem for p in cache.glob("*.html")}
    return [a for a in all_appnos if appno_to_vnid(a) not in cached_vnids]


async def run_chunk(
    session: AsyncSession,
    *,
    enqueue_next: Callable[[], None] = _real_enqueue,
    http_session: requests.Session | None = None,
) -> dict:
    """Process up to chunk_size uncached application numbers honoring live control state."""
    ctl = await _ctl(session)
    if ctl["status"] != "running":
        return {"status": ctl["status"], "did": 0}

    if ctl["mode"] == "dead":
        # Dead mode is a self-contained package; delegate the whole chunk. Lazy
        # import keeps the dependency one-way (sweep -> dead_mode, no cycle).
        from domestic_enrich.dead_mode import run_chunk as run_dead_chunk

        return await run_dead_chunk(session, enqueue_next=enqueue_next, http_session=http_session)

    cache = _cache_dir()
    all_appnos = await iter_domestic_appnos(session)
    todo = _uncached(all_appnos, cache)

    http = http_session or requests.Session()
    streak = 0
    did = 0
    for idx, appno in enumerate(todo):
        ctl = await _ctl(session)
        if ctl["status"] != "running":
            break
        nxt = todo[idx + 1] if idx + 1 < len(todo) else None
        if ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]:
            await _set(session, status="idle", current_appno=None, next_appno=None)
            break
        try:
            await enrich_one(session, appno, cache, http_session=http, use_cache=True)
            await session.commit()
            await _set(
                session,
                ok=ctl["ok"] + 1,
                processed=ctl["processed"] + 1,
                current_appno=appno,
                next_appno=nxt,
                last_error=None,
            )
            streak = 0
        except NoipBlockedError as e:
            # A block / rate-limit is not transient flakiness — stop NOW rather
            # than work through the rest of the chunk and risk a hard ban. Pause
            # the whole sweep so an operator can cool down and resume slower.
            await session.rollback()
            await _set(
                session,
                status="paused",
                failed=ctl["failed"] + 1,
                current_appno=appno,
                next_appno=nxt,
                last_error=f"NOIP block (HTTP {e.status}) — paused; cool down before resuming",
            )
            break
        except Exception as e:
            await session.rollback()
            streak += 1
            await _set(
                session,
                failed=ctl["failed"] + 1,
                processed=ctl["processed"] + 1,
                current_appno=appno,
                next_appno=nxt,
                last_error=str(e)[:300],
            )
        did += 1
        if streak >= _MAX_CONSECUTIVE:
            await _set(session, status="paused", last_error=f"circuit breaker: {streak} consecutive failures")
            break
        if did >= ctl["chunk_size"]:
            break
        time.sleep(ctl["delay"] + random.uniform(0, ctl["jitter"]))

    ctl = await _ctl(session)
    if ctl["status"] == "stopping":
        await _set(session, status="idle", current_appno=None, next_appno=None)
    elif ctl["status"] == "running":
        remaining = _uncached(all_appnos, cache)
        cap_hit = ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]
        if remaining and not cap_hit:
            enqueue_next()
        else:
            await _set(session, status="idle", current_appno=None, next_appno=None)
    return {"status": ctl["status"], "did": did}


def run_sweep_chunk() -> dict:
    """RQ entry point (sync) — bridges to the async core like worker.ingest."""

    async def _inner() -> dict:
        async with async_session() as s:
            return await run_chunk(s)

    return asyncio.run(_inner())
