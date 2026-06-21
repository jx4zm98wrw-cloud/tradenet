# Dead Mode — Concurrent Runner + Delegation (PR 3 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Build `dead_mode/runner.py` — the adaptive-concurrency domestic fetcher governed by the AIMD controller — and wire the normal sweep to delegate to it via a single `if mode == 'dead'` branch.

**Architecture:** The runner processes the uncached domestic work-list in waves. **Worker THREADS do only the network fetch** (sync `requests` via `fetch_raw`, thread-safe, no DB, no asyncio). **The single owning COROUTINE does every DB write** (parse + `upsert` + control-row updates) on its own event loop — so asyncpg connections are never shared across threads (the loop-binding trap that stalled the boot-resume in #73). After each window of fetches the AIMD controller adjusts concurrency; sustained blocks auto-revert to normal + pause. The runner imports the proven fetch/parse/store primitives directly and **never** imports `worker.domestic_sweep`.

**Tech Stack:** Python 3.13, `asyncio`, `concurrent.futures.ThreadPoolExecutor`, SQLAlchemy async, `requests`, pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-21-domestic-dead-mode-design.md` (§Architecture, §AIMD controller, §Safety valve, §Error handling — the threading/asyncpg note).

## Scope

PR 3 of 5: the runner + the delegation branch. Routes (PR 4) and frontend (PR 5) are out of scope. After this PR, setting `mode='dead'` on the control row makes the next sweep chunk run the concurrent path; default `mode='normal'` is byte-for-byte unchanged.

## Standing constraints

- **NEVER commit the rename trio**; `git add` by explicit path.
- **GateGuard**: state facts on first Edit/Write per file + first Bash; retry.
- Run from `app/backend/` with the venv. CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`.
- **The dev DB hosts the LIVE sweep.** Run ONLY the targeted tests in the steps below — never the full suite (its fixtures reset the control singleton). The runner tests seed/restore an isolated control row via a fixture and use stubs, never touching real NOIP.
- One-way dependency: `dead_mode` must NOT import `worker.domestic_sweep`.

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/domestic_enrich/dead_mode/runner.py` (new) | `run_chunk()` — wave loop, thread-pool fetch, coroutine store, AIMD window eval, cooldown, auto-revert, re-enqueue. |
| `app/backend/domestic_enrich/dead_mode/__init__.py` | Re-export `run_chunk`. |
| `app/backend/worker/domestic_sweep.py` | Add `C.mode` to `_ctl`'s select; one delegation branch in `run_chunk`. |
| `app/backend/tests/domestic_enrich/dead_mode/test_runner.py` (new) | Ramp, sustained-block→revert+pause, start-guard, re-enqueue — all stubbed (no network). |
| `app/backend/tests/domestic_enrich/dead_mode/test_delegation.py` (new) | `mode='dead'` delegates; `mode='normal'` does not. |

---

## Task 1: The concurrent runner

**Files:**
- Create: `app/backend/domestic_enrich/dead_mode/runner.py`
- Modify: `app/backend/domestic_enrich/dead_mode/__init__.py`
- Test: `app/backend/tests/domestic_enrich/dead_mode/test_runner.py`

- [ ] **Step 1: Write the runner**

`app/backend/domestic_enrich/dead_mode/runner.py`:

```python
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
from datetime import UTC, datetime
from pathlib import Path

import requests
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

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
from domestic_enrich.store import upsert

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
        return (appno, Outcome.SUCCESS, result)
    except NoipBlockedError:
        return (appno, Outcome.BLOCK, None)
    except Exception:  # exhausted retries / any fetch error -> flaky, retry later
        return (appno, Outcome.FLAKY_FAIL, None)


async def _ctl(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            select(
                C.status, C.mode, C.cap, C.processed, C.ok, C.failed, C.concurrency
            ).where(C.id == 1)
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
    todo = _uncached(all_appnos, cache)
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

            ok = failed = 0
            for appno, outcome, result in results:
                if outcome is Outcome.SUCCESS and result is not None:
                    await _store_success(session, appno, result)
                    ok += 1
                else:
                    failed += 1
                window.append(outcome)
                did += 1
            await _set(
                session,
                processed=ctl["processed"] + ok + failed,
                ok=ctl["ok"] + ok,
                failed=ctl["failed"] + failed,
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
                            last_error="dead mode: sustained NOIP blocks — reverted to normal + paused; cool down",
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
        remaining = _uncached(all_appnos, cache)
        cap_hit = ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]
        if remaining and not cap_hit:
            enqueue_next()
        else:
            await _set(session, status="idle", concurrency=0, current_appno=None, next_appno=None)
    return {"status": ctl["status"], "did": did}
```

- [ ] **Step 2: Re-export `run_chunk` from the package**

Edit `app/backend/domestic_enrich/dead_mode/__init__.py` — add the runner import and put `run_chunk` in `__all__`:

```python
from domestic_enrich.dead_mode.controller import (
    Decision,
    Outcome,
    WindowStats,
    next_concurrency,
    should_give_up,
    stats_from,
)
from domestic_enrich.dead_mode.runner import run_chunk

DEAD = "dead"
NORMAL = "normal"

__all__ = [
    "DEAD",
    "NORMAL",
    "Decision",
    "Outcome",
    "WindowStats",
    "next_concurrency",
    "run_chunk",
    "should_give_up",
    "stats_from",
]
```

- [ ] **Step 3: Write the runner tests**

`app/backend/tests/domestic_enrich/dead_mode/test_runner.py`. The fixture seeds an isolated `running`+`dead` control row and restores it; every test stubs `_fetch_outcome`/`_store_success`/`_cache_dir`/`_uncached`/`iter_domestic_appnos` so no network or real store runs. `COOLDOWN_S` is patched to 0 so block tests don't sleep.

```python
import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import domestic_enrich.dead_mode.runner as r
from api.db.models import DomesticSweepControl as C
from api.settings import get_settings
from domestic_enrich.dead_mode.controller import Outcome


@pytest_asyncio.fixture(autouse=True)
async def _seed_dead_control():
    """Seed id=1 as running+dead before each test; restore idle/normal after, so
    the dev singleton is never left in a dead/running state."""
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(
            insert(C).values(id=1, status="running", mode="dead", concurrency=0, processed=0, ok=0, failed=0)
        )
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="idle", mode="normal", concurrency=0))
        await s.commit()
    await engine.dispose()


def _stub_common(monkeypatch, tmp_path, appnos):
    async def fake_iter(_session):
        return appnos

    monkeypatch.setattr(r, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(r, "_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(r, "_uncached", lambda all_, _cache: list(all_))
    monkeypatch.setattr(r, "COOLDOWN_S", 0.0)


@pytest.mark.asyncio
async def test_returns_immediately_when_not_dead(db_session, tmp_path, monkeypatch):
    await db_session.execute(update(C).where(C.id == 1).values(mode="normal"))
    await db_session.commit()
    monkeypatch.setattr(r, "_cache_dir", lambda: tmp_path)
    res = await r.run_chunk(db_session, enqueue_next=lambda: None)
    assert res["did"] == 0


@pytest.mark.asyncio
async def test_processes_successes_and_ramps_concurrency(db_session, tmp_path, monkeypatch):
    appnos = [f"4-2026-{n:05d}" for n in range(60)]
    _stub_common(monkeypatch, tmp_path, appnos)

    def fake_fetch(appno, _cache, _http):
        return (appno, Outcome.SUCCESS, object())

    stored: list[str] = []

    async def fake_store(_session, appno, _result):
        stored.append(appno)

    monkeypatch.setattr(r, "_fetch_outcome", fake_fetch)
    monkeypatch.setattr(r, "_store_success", fake_store)

    res = await r.run_chunk(db_session, enqueue_next=lambda: None)

    assert res["did"] == 60
    assert len(stored) == 60
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    # 60 clean marks = 3 windows of +1 each from START=2 -> ended above START.
    assert row.concurrency > 2
    assert row.ok == 60 and row.failed == 0


@pytest.mark.asyncio
async def test_sustained_blocks_revert_to_normal_and_pause(db_session, tmp_path, monkeypatch):
    appnos = [f"4-2026-{n:05d}" for n in range(80)]
    _stub_common(monkeypatch, tmp_path, appnos)

    def fake_block(appno, _cache, _http):
        return (appno, Outcome.BLOCK, None)

    monkeypatch.setattr(r, "_fetch_outcome", fake_block)

    enq: list[int] = []
    res = await r.run_chunk(db_session, enqueue_next=lambda: enq.append(1))

    assert res["status"] == "paused"
    assert enq == []  # gave up — did NOT re-enqueue
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert row.mode == "normal"
    assert row.status == "paused"
    assert "block" in (row.last_error or "").lower()


@pytest.mark.asyncio
async def test_reenqueues_when_work_remains(db_session, tmp_path, monkeypatch):
    # 100 marks (== DEAD_CHUNK_MARKS) all succeed, but the work-list is longer,
    # so after the chunk caps out it must re-enqueue.
    appnos = [f"4-2026-{n:05d}" for n in range(200)]
    _stub_common(monkeypatch, tmp_path, appnos)
    monkeypatch.setattr(r, "_fetch_outcome", lambda a, c, h: (a, Outcome.SUCCESS, object()))

    async def fake_store(_s, _a, _r):
        return None

    monkeypatch.setattr(r, "_store_success", fake_store)

    enq: list[int] = []
    res = await r.run_chunk(db_session, enqueue_next=lambda: enq.append(1))
    assert res["did"] == r.DEAD_CHUNK_MARKS  # bounded per job
    assert enq == [1]  # more remain -> re-enqueued
```

- [ ] **Step 4: Run the runner tests**

```bash
cd app/backend && source ../.venv/bin/activate
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -m pytest tests/domestic_enrich/dead_mode/test_runner.py -v
```
Expected: 4 tests PASS.

- [ ] **Step 5: Lint + typecheck**

```bash
cd app/backend && source ../.venv/bin/activate
ruff format domestic_enrich/dead_mode/ tests/domestic_enrich/dead_mode/test_runner.py
ruff check . && python -m mypy domestic_enrich/dead_mode/runner.py
```
Expected: ruff clean; mypy `Success`.

- [ ] **Step 6: Commit**

```bash
git add app/backend/domestic_enrich/dead_mode/runner.py \
        app/backend/domestic_enrich/dead_mode/__init__.py \
        app/backend/tests/domestic_enrich/dead_mode/test_runner.py
git commit -m "$(printf 'feat(dead-mode): adaptive-concurrency runner (threads fetch, coroutine stores)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Delegate to the runner from the normal sweep

**Files:**
- Modify: `app/backend/worker/domestic_sweep.py`
- Test: `app/backend/tests/domestic_enrich/dead_mode/test_delegation.py`

- [ ] **Step 1: Add `C.mode` to `_ctl`'s select**

In `app/backend/worker/domestic_sweep.py`, `_ctl`'s select currently lists `C.status, C.cap, C.delay, C.jitter, C.chunk_size, C.processed, C.ok, C.failed`. Add `C.mode`:

```python
async def _ctl(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            select(
                C.status, C.mode, C.cap, C.delay, C.jitter, C.chunk_size, C.processed, C.ok, C.failed
            ).where(C.id == 1)
        )
    ).one()
    return dict(row._mapping)
```

- [ ] **Step 2: Add the single delegation branch in `run_chunk`**

In `worker/domestic_sweep.py`, immediately after the existing status guard in `run_chunk` (`if ctl["status"] != "running": return ...`), insert:

```python
    if ctl["mode"] == "dead":
        # Dead mode is a self-contained package; delegate the whole chunk. Lazy
        # import keeps the dependency one-way (sweep -> dead_mode, no cycle).
        from domestic_enrich.dead_mode import run_chunk as run_dead_chunk

        return await run_dead_chunk(session, enqueue_next=enqueue_next, http_session=http_session)
```

The existing normal-path code below it is unchanged.

- [ ] **Step 3: Write the delegation test**

`app/backend/tests/domestic_enrich/dead_mode/test_delegation.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy import delete, insert, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import worker.domestic_sweep as ds
from api.db.models import DomesticSweepControl as C
from api.settings import get_settings


@pytest_asyncio.fixture(autouse=True)
async def _seed_control():
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="running", mode="normal", concurrency=0))
        await s.commit()
    yield
    async with Session() as s:
        await s.execute(delete(C))
        await s.execute(insert(C).values(id=1, status="idle", mode="normal", concurrency=0))
        await s.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_dead_mode_delegates_to_dead_runner(db_session, monkeypatch):
    await db_session.execute(update(C).where(C.id == 1).values(mode="dead"))
    await db_session.commit()

    called = {}

    async def fake_dead(session, *, enqueue_next, http_session=None):
        called["yes"] = True
        return {"status": "running", "did": 7}

    # The sweep lazily imports `from domestic_enrich.dead_mode import run_chunk`,
    # so patch the name on that package.
    import domestic_enrich.dead_mode as dm

    monkeypatch.setattr(dm, "run_chunk", fake_dead)

    res = await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert called.get("yes") is True
    assert res == {"status": "running", "did": 7}


@pytest.mark.asyncio
async def test_normal_mode_does_not_delegate(db_session, monkeypatch):
    # mode stays 'normal'; stub the normal path's work-list so it doesn't hit network.
    async def fake_iter(_s):
        return []

    monkeypatch.setattr(ds, "iter_domestic_appnos", fake_iter)

    import domestic_enrich.dead_mode as dm

    def _boom(*a, **k):
        raise AssertionError("dead runner must NOT be called in normal mode")

    monkeypatch.setattr(dm, "run_chunk", _boom)

    res = await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert res["did"] == 0  # empty work-list, normal path, no delegation
```

- [ ] **Step 4: Run the delegation tests + gates**

```bash
cd app/backend && source ../.venv/bin/activate
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -m pytest tests/domestic_enrich/dead_mode/ -v
ruff check . && ruff format --check . && mypy api worker
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic check
```
Expected: all dead_mode tests pass; ruff clean; mypy `Success`; `No new upgrade operations detected.` (Do NOT run the full suite — it resets the live sweep singleton.)

- [ ] **Step 5: Commit**

```bash
git add app/backend/worker/domestic_sweep.py app/backend/tests/domestic_enrich/dead_mode/test_delegation.py
git commit -m "$(printf 'feat(dead-mode): delegate the chunk to dead_mode.run_chunk when mode=dead\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage:**
- Threads fetch / coroutine stores (asyncpg-safe) → `_fetch_outcome` (thread) + `_store_success`/`_set` (coroutine). ✅
- AIMD window eval + concurrency persisted → `next_concurrency` at `WINDOW_SIZE`, written via `_set(concurrency=…)`. ✅
- Cooldown on block + sustained-block auto-revert+pause → `should_give_up` → `mode='normal'`/`status='paused'`. ✅
- Live `mode`/`status`/`cap` honored mid-chunk → per-wave `_ctl` re-read. ✅
- One-way dependency / single delegation point → lazy import in `domestic_sweep.run_chunk`; runner imports no `worker.*`. ✅
- Bounded per-job (`DEAD_CHUNK_MARKS`) + re-enqueue → covered by `test_reenqueues_when_work_remains`. ✅

**Placeholder scan:** none.

**Type/consistency:** runner imports `CEILING/START/WINDOW_SIZE/Outcome/next_concurrency/should_give_up/stats_from` (exact names from `controller.py`); `fetch_raw(...delay=0.0)`, `parse(html)`, `upsert(session, rec, raw_html, source_url)` match the real signatures; `_ctl` adds `mode` consistently in runner and sweep; delegation reads `ctl["mode"]` which the sweep's `_ctl` now selects.

**Known simplifications (intentional, first working version):** wave model (each wave waits for its slowest fetch — some parallelism lost on a very flaky mark; a continuous-semaphore model is a future optimization); per-chunk window/consec_block state is in-memory (only `concurrency` persists across chunks — fine because `DEAD_CHUNK_MARKS=100 > 3 windows`, so giveup still triggers within a job).
