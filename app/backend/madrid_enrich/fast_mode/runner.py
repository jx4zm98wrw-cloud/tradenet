"""Fast-mode chunk runner — rate-aware concurrent Madrid (WIPO) fetcher.

Adapts domestic_enrich.dead_mode.runner: THREADS do only the network fetch (sync
`requests`, thread-safe) which warms the on-disk cache and surfaces WIPO's
X-RateLimit headers; the single owning COROUTINE does all DB writes (store via
`enrich_one`, which re-reads the now-cached HTML — no second network call — plus
control updates) on its own event loop, so asyncpg connections are never shared
across threads.

Unlike dead mode's AIMD probe, concurrency is paced to WIPO's *published* budget:
each window of completed fetches builds a `RateWindow` from the last-seen
`rate_remaining`/`rate_limit` (and whether any `WipoThrottledError` fired) and the
pure `next_concurrency` controller decides the next concurrency. An explicit 429
parks the runner: it sleeps `Retry-After` (or `COOLDOWN_S`) before the next window.

Never imports worker.madrid_sweep (one-way dependency).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import requests
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import MadridSweepControl as C
from api.settings import get_settings
from madrid_enrich.backfill import iter_madrid_irns
from madrid_enrich.client import FetchResult, WipoThrottledError, fetch_raw
from madrid_enrich.enrich import enrich_one
from madrid_enrich.fast_mode.controller import (
    CEILING,
    FLOOR,
    START,
    RateWindow,
    next_concurrency,
)

# Marks one fast-mode RQ job processes before re-enqueuing — keeps each job well
# under the worker JOB_TIMEOUT even at concurrency 1, and is several windows so
# the controller can adapt within a single job.
FAST_CHUNK_MARKS = 100
# Completed fetches per controller window — how often we re-read the rate budget
# and re-decide concurrency.
WINDOW_SIZE = 10
# Cool-down when WIPO throttles but gives no Retry-After header.
COOLDOWN_S = 30.0


def _cache_dir() -> Path:
    return get_settings().data_dir / "madrid_cache"


def _uncached(all_irns: list[str], cache: Path) -> list[str]:
    cached = {p.stem for p in cache.glob("*.html")}
    return [i for i in all_irns if i not in cached]


def _fetch(irn: str, cache: Path, http: requests.Session) -> tuple[str, FetchResult | None, float | None]:
    """Runs in a worker THREAD. Pure network + cache; no DB, no asyncio. Warms the
    cache and returns (irn, result-or-None, retry_after). A WipoThrottledError
    yields retry_after (a float or None) signalling a throttle — the window pauses
    for that long; a successful fetch yields (result, None); any other error yields
    (None, None) (counts as a failed store attempt downstream)."""
    try:
        result = fetch_raw(irn, cache, session=http, use_cache=True)
        return (irn, result, None)
    except WipoThrottledError as e:
        # retry_after may be None; the sentinel below distinguishes throttle-without-
        # header from "no throttle" via the separate `throttled` flag the caller sets.
        return (irn, None, e.retry_after if e.retry_after is not None else -1.0)
    except Exception:
        return (irn, None, None)


async def _ctl(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            select(
                C.status,
                C.mode,
                C.cap,
                C.processed,
                C.ok,
                C.failed,
                C.concurrency,
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
    enqueue_next: Callable[[], None],
    http_session: requests.Session | None = None,
) -> dict:
    """One fast-mode chunk: rate-paced concurrent fetch of up to FAST_CHUNK_MARKS
    uncached IRNs, then re-enqueue while still running+fast."""
    ctl = await _ctl(session)
    if ctl["status"] != "running" or ctl["mode"] != "fast":
        return {"status": ctl["status"], "did": 0}

    cache = _cache_dir()
    all_irns = await iter_madrid_irns(session)
    todo = _uncached(all_irns, cache)
    http = http_session or requests.Session()

    concurrency = min(CEILING, max(FLOOR, ctl["concurrency"] or START))
    # Last-seen rate budget + whether a throttle fired this window.
    last_remaining: int | None = None
    last_limit: int | None = None
    last_retry_after: float | None = None
    throttled_this_window = False
    in_window = 0
    did = 0
    loop = asyncio.get_running_loop()

    pool = ThreadPoolExecutor(max_workers=CEILING)
    try:
        i = 0
        while i < len(todo) and did < FAST_CHUNK_MARKS:
            ctl = await _ctl(session)
            if ctl["status"] != "running" or ctl["mode"] != "fast":
                break
            if ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]:
                await _set(session, status="idle", concurrency=0, current_irn=None, next_irn=None)
                return {"status": "idle", "did": did}

            batch = todo[i : i + concurrency]
            i += len(batch)
            futures = [loop.run_in_executor(pool, _fetch, irn, cache, http) for irn in batch]
            results = await asyncio.gather(*futures)

            ok = failed = 0
            for irn, result, retry_after in results:
                if retry_after is not None:
                    # A throttle fired. -1.0 is the "no Retry-After header" sentinel;
                    # keep the largest real retry_after seen this window.
                    throttled_this_window = True
                    if retry_after >= 0.0 and (last_retry_after is None or retry_after > last_retry_after):
                        last_retry_after = retry_after
                if result is not None:
                    # Store via enrich_one (re-reads the now-cached HTML — no second
                    # network call). Surface this window's rate budget.
                    last_remaining = result.rate_remaining
                    last_limit = result.rate_limit
                    try:
                        await enrich_one(session, irn, cache, http_session=http, use_cache=True)
                        await session.commit()
                        ok += 1
                    except Exception as e:
                        await session.rollback()
                        failed += 1
                        await _set(session, last_error=str(e)[:300])
                else:
                    failed += 1
                in_window += 1
                did += 1
            await _set(
                session,
                processed=ctl["processed"] + ok + failed,
                ok=ctl["ok"] + ok,
                failed=ctl["failed"] + failed,
                current_irn=batch[-1] if batch else None,
                last_error=None if not throttled_this_window else ctl.get("last_error"),
            )

            if in_window >= WINDOW_SIZE or throttled_this_window:
                decision = next_concurrency(
                    concurrency,
                    RateWindow(
                        remaining=last_remaining,
                        limit=last_limit,
                        throttled=throttled_this_window,
                    ),
                )
                concurrency = decision.concurrency
                await _set(session, concurrency=concurrency)
                if decision.paused:
                    await asyncio.sleep(last_retry_after if last_retry_after is not None else COOLDOWN_S)
                in_window = 0
                throttled_this_window = False
                last_retry_after = None
    finally:
        pool.shutdown(wait=False)

    # Continuation — re-enqueue while there's work and we're still running+fast.
    ctl = await _ctl(session)
    if ctl["status"] == "running" and ctl["mode"] == "fast":
        remaining = _uncached(all_irns, cache)
        cap_hit = ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]
        if remaining and not cap_hit:
            enqueue_next()
        else:
            await _set(session, status="idle", concurrency=0, current_irn=None, next_irn=None)
    return {"status": ctl["status"], "did": did}
