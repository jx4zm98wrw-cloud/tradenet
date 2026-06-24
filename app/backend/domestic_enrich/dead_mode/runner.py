"""Dead-mode chunk runner — adaptive-concurrency domestic fetcher.

THREADS do only the network fetch (sync `requests`, thread-safe); the single
owning COROUTINE does all DB writes (parse + upsert + control updates) on its own
event loop, so asyncpg connections are never shared across threads (the
loop-binding trap from the boot-resume fix). Reuses the proven fetch/parse/store
primitives directly; never imports worker.domestic_sweep (one-way dependency).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import DomesticNotFound
from api.db.models import DomesticSweepControl as C
from api.settings import get_settings
from domestic_enrich.backfill import iter_domestic_appnos
from domestic_enrich.client import FetchResult, NoipBlockedError, fetch_raw
from domestic_enrich.dead_mode.controller import (
    CEILING,
    START,
    WINDOW_SIZE,
    Outcome,
    next_concurrency,
    should_give_up,
    stats_from,
)
from domestic_enrich.idmap import appno_to_vnid
from domestic_enrich.parser import parse
from domestic_enrich.store import upsert, upsert_not_found

# Mirror worker.domestic_sweep._NOT_FOUND_BACKOFF. Kept local (like _uncached /
# _cache_dir) so dead_mode never imports worker.domestic_sweep (one-way dep).
_NOT_FOUND_BACKOFF = timedelta(days=30)

# Max marks one dead-mode RQ job processes before re-enqueuing — keeps each job
# well under the worker JOB_TIMEOUT even at concurrency 1, and is > 3 windows so
# the sustained-block giveup can trigger within a single job.
DEAD_CHUNK_MARKS = 100
COOLDOWN_S = 30.0


def _cache_dir() -> Path:
    return get_settings().data_dir / "domestic_cache"


def _uncached(all_appnos: list[str], cache: Path) -> list[str]:
    cached = {p.stem for p in cache.glob("*.html")}
    return [a for a in all_appnos if appno_to_vnid(a) not in cached]


async def _recent_not_found(session: AsyncSession) -> set[str]:
    """Application numbers recorded not-published within the backoff window —
    skipped so dead mode converges instead of re-fetching the unresolvable front
    every chunk (mirrors worker.domestic_sweep._recent_not_found)."""
    cutoff = datetime.now(UTC) - _NOT_FOUND_BACKOFF
    rows = (
        (
            await session.execute(
                select(DomesticNotFound.application_number).where(DomesticNotFound.last_checked_at >= cutoff)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)


def _fetch_outcome(
    appno: str, cache: Path, http: requests.Session
) -> tuple[str, Outcome, FetchResult | None]:
    """Runs in a worker THREAD. Pure network + cache; no DB, no asyncio.
    Classifies the fetch and returns (appno, outcome, result-or-None)."""
    vnid = appno_to_vnid(appno)
    if vnid is None:
        return (appno, Outcome.FLAKY_FAIL, None)
    try:
        result = fetch_raw(vnid, cache, session=http, use_cache=True, delay=0.0)
        # HTTP 200 + skeleton: IP VIETNAM has no published detail yet. Carry the result
        # back (it holds the vnid) so the owning coroutine can negative-cache it.
        if result.outcome == "not_found":
            return (appno, Outcome.NOT_FOUND, result)
        return (appno, Outcome.SUCCESS, result)
    except NoipBlockedError:
        return (appno, Outcome.BLOCK, None)
    except Exception:  # exhausted retries / any fetch error -> flaky, retry later
        return (appno, Outcome.FLAKY_FAIL, None)


async def _ctl(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            select(C.status, C.mode, C.cap, C.processed, C.ok, C.failed, C.not_found, C.concurrency).where(
                C.id == 1
            )
        )
    ).one()
    return dict(row._mapping)


async def _set(session: AsyncSession, **vals) -> None:
    vals["updated_at"] = datetime.now(UTC)
    await session.execute(update(C).where(C.id == 1).values(**vals))
    await session.commit()


async def _store_success(session: AsyncSession, appno: str, result: FetchResult) -> None:
    """Parse + upsert one fetched mark. MAIN COROUTINE ONLY (owns the session)."""
    rec = parse(result.html)
    rec.application_number = appno
    await upsert(session, rec, result.html, result.source_url)
    await session.commit()


async def run_chunk(
    session: AsyncSession,
    *,
    enqueue_next: Callable[[], None],
    http_session: requests.Session | None = None,
) -> dict:
    """One dead-mode chunk: adaptive-concurrency fetch of up to DEAD_CHUNK_MARKS
    uncached marks, then re-enqueue while still running+dead."""
    ctl = await _ctl(session)
    if ctl["status"] != "running" or ctl["mode"] != "dead":
        return {"status": ctl["status"], "did": 0}

    cache = _cache_dir()
    all_appnos = await iter_domestic_appnos(session)
    recent_nf = await _recent_not_found(session)
    # Exclude malformed appnos (appno_to_vnid is None) so dead mode CONVERGES too —
    # they can never map to a IP VIETNAM id, so re-fetching them every chunk is wasted
    # work (and would otherwise count as failed via _fetch_outcome's None-vnid
    # branch). Mirrors worker.domestic_sweep._worklist.
    todo = [a for a in _uncached(all_appnos, cache) if a not in recent_nf and appno_to_vnid(a) is not None]
    http = http_session or requests.Session()

    concurrency = max(START, ctl["concurrency"] or START)
    window: list[Outcome] = []
    consec_block = 0
    did = 0
    loop = asyncio.get_running_loop()

    pool = ThreadPoolExecutor(max_workers=CEILING)
    try:
        i = 0
        while i < len(todo) and did < DEAD_CHUNK_MARKS:
            ctl = await _ctl(session)
            if ctl["status"] != "running" or ctl["mode"] != "dead":
                break
            if ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]:
                await _set(session, status="idle", concurrency=0, current_appno=None, next_appno=None)
                return {"status": "idle", "did": did}

            batch = todo[i : i + concurrency]
            i += len(batch)
            futures = [loop.run_in_executor(pool, _fetch_outcome, appno, cache, http) for appno in batch]
            results = await asyncio.gather(*futures)

            ok = failed = nf = 0
            for appno, outcome, result in results:
                if outcome is Outcome.SUCCESS and result is not None:
                    await _store_success(session, appno, result)
                    ok += 1
                elif outcome is Outcome.NOT_FOUND:
                    # No published detail yet — negative-cache it, never store the
                    # skeleton. Counted apart from ok/failed.
                    vnid = result.vnid if result is not None else appno_to_vnid(appno)
                    await upsert_not_found(session, appno, vnid)
                    await session.commit()
                    nf += 1
                else:
                    failed += 1
                window.append(outcome)
                did += 1
            await _set(
                session,
                processed=ctl["processed"] + ok + failed + nf,
                ok=ctl["ok"] + ok,
                failed=ctl["failed"] + failed,
                not_found=ctl["not_found"] + nf,
                current_appno=batch[-1] if batch else None,
                last_error=None,
            )

            if len(window) >= WINDOW_SIZE:
                decision = next_concurrency(concurrency, stats_from(window))
                concurrency = decision.concurrency
                window = []
                await _set(session, concurrency=concurrency)
                if decision.blocked:
                    consec_block += 1
                    if should_give_up(consec_block):
                        await _set(
                            session,
                            mode="normal",
                            status="paused",
                            concurrency=0,
                            last_error="dead mode: sustained IP VIETNAM blocks — reverted to normal + paused; cool down",
                        )
                        return {"status": "paused", "did": did}
                    await asyncio.sleep(COOLDOWN_S)
                else:
                    consec_block = 0
    finally:
        pool.shutdown(wait=False)

    # Continuation — re-enqueue while there's work and we're still running+dead.
    ctl = await _ctl(session)
    if ctl["status"] == "running" and ctl["mode"] == "dead":
        recent_nf = await _recent_not_found(session)
        remaining = [
            a for a in _uncached(all_appnos, cache) if a not in recent_nf and appno_to_vnid(a) is not None
        ]
        cap_hit = ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]
        if remaining and not cap_hit:
            enqueue_next()
        else:
            await _set(session, status="idle", concurrency=0, current_appno=None, next_appno=None)
    return {"status": ctl["status"], "did": did}
