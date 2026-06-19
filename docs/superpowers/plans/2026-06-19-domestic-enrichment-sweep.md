# Domestic Enrichment — Sweep + Control (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the domestic enrichment core (Plan A) operable as a **controllable full sweep** — a singleton control row, a chunked self-re-enqueuing RQ job on a new `domestic` queue, admin start/pause/resume/stop/config endpoints (409-guarded), and a live coverage-stats endpoint — mirroring the Madrid sweep stack 1:1.

**Architecture:** A `DomesticSweepControl` singleton (id=1) holds status + cadence + live counters. `worker/domestic_sweep.py` processes one chunk of uncached domestic application numbers via `enrich_one`, re-reading the control row each item so pause/stop/cadence edits take effect live, then re-enqueues itself while `status='running'`. `api/routes/domestic_sweep.py` exposes the state machine; `admin.py` gains a `/domestic-enrichment` coverage endpoint.

**Tech Stack:** Same as Plan A + Redis/RQ. Reference the Madrid equivalents directly — this is a structural copy with `irn`→`appno` renames and one real difference (cache/work-list key mismatch, below).

## THE one real difference from Madrid

Madrid's cache files are named by the work-list item (`<irn>.html`), so "uncached = work-list minus `{p.stem}`" works directly. **Domestic's cache files are named by VNID** (`VN4202600774.html`, the fetch id) **but the work-list is `application_number`** (`4-2026-00774`). So the uncached filter must map each appno through `appno_to_vnid`:

```python
cached_vnids = {p.stem for p in cache.glob("*.html")}
todo = [a for a in all_appnos if appno_to_vnid(a) not in cached_vnids]
```

`enrich_one(session, application_number, cache, ...)` already maps appno→VNID internally for the fetch and caches by VNID, so passing the `application_number` is correct.

## Reference (read first)

- `app/backend/worker/madrid_sweep.py`, `app/backend/api/routes/madrid_sweep.py`
- `app/backend/api/db/models.py:477` (`MadridSweepControl`), `app/backend/alembic/versions/20260619_0018_madrid_sweep_control.py`
- `app/backend/api/routes/admin.py:45` (`MadridEnrichmentStats`) / `:54` (endpoint)
- `app/backend/worker/run_worker.py`, `app/backend/api/main.py:141`
- Tests: `app/backend/tests/test_madrid_sweep_control.py`, `test_madrid_sweep_job.py`, `test_admin_madrid_stats.py`

## Standing constraints (every task)

- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` by explicit path only.
- **GateGuard**: state facts on first Edit/Write per file + first Bash; retry.
- Tests run from `app/backend/` with the project venv (`source ../.venv/bin/activate`) and `TM_DATABASE_URL[_SYNC]` env vars; CI runs `ruff check .`, `ruff format --check .`, **`alembic check`**, then pytest — every new model index must be declared in `__table_args__` (Plan A's drift bug), and new files must be ruff-formatted before commit.

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/api/db/models.py` | Add `DomesticSweepControl` (singleton id=1). |
| `app/backend/alembic/versions/20260619_0021_domestic_sweep_control.py` | Table + seed row (down_revision `20260619_0020`). |
| `app/backend/worker/domestic_sweep.py` | Chunked RQ job on the `domestic` queue. |
| `app/backend/worker/run_worker.py` | Add `domestic` to the listened queues. |
| `app/backend/api/routes/domestic_sweep.py` | Control endpoints (start/pause/resume/stop/config). |
| `app/backend/api/main.py` | Register the new router. |
| `app/backend/api/routes/admin.py` | Add `/domestic-enrichment` coverage stats. |
| `app/backend/tests/...` | Mirror the three Madrid sweep test files. |

---

## Task 1: `DomesticSweepControl` model + migration

**Files:**
- Modify: `app/backend/api/db/models.py` (add after `MadridSweepControl`)
- Create: `app/backend/alembic/versions/20260619_0021_domestic_sweep_control.py`
- Test: `app/backend/tests/domestic_enrich/test_sweep_model.py`

- [ ] **Step 1: Add the model** in `app/backend/api/db/models.py`, immediately after the `MadridSweepControl` class. (`CheckConstraint, Integer, Float, Text, DateTime, func, Mapped, mapped_column, datetime` are already imported.)

```python
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
    current_appno: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_appno: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2: Create the migration** `app/backend/alembic/versions/20260619_0021_domestic_sweep_control.py`:

```python
"""domestic_sweep_control singleton control row

Revision ID: 20260619_0021
Revises: 20260619_0020
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260619_0021"
down_revision = "20260619_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "domestic_sweep_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="idle"),
        sa.Column("cap", sa.Integer(), nullable=True),
        sa.Column("delay", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("jitter", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_appno", sa.Text(), nullable=True),
        sa.Column("next_appno", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('idle','running','paused','stopping')",
            name="ck_domestic_sweep_status",
        ),
    )
    op.execute("INSERT INTO domestic_sweep_control (id, status) VALUES (1, 'idle')")


def downgrade() -> None:
    op.drop_table("domestic_sweep_control")
```

- [ ] **Step 3: Apply + verify no drift**

```bash
cd app/backend && source ../.venv/bin/activate
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic upgrade head
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic check
```
Expected: `Running upgrade 20260619_0020 -> 20260619_0021`, then `No new upgrade operations detected.`

- [ ] **Step 4: Write the test** `app/backend/tests/domestic_enrich/test_sweep_model.py`:

```python
import pytest
from sqlalchemy import select

from api.db.models import DomesticSweepControl


@pytest.mark.asyncio
async def test_singleton_seed_row_exists(db_session):
    row = (await db_session.execute(
        select(DomesticSweepControl).where(DomesticSweepControl.id == 1)
    )).scalar_one()
    assert row.status == "idle"
    assert row.chunk_size == 25
    assert row.processed == 0
```
> If the test DB is built fresh from migrations, the seed INSERT runs and id=1 exists. Confirm against how `tests/test_madrid_sweep_control.py` obtains its seed row; if that test seeds the row itself in a fixture, do the same here.

- [ ] **Step 5: Run** `python -m pytest tests/domestic_enrich/test_sweep_model.py -v` → PASS. **Format + lint:** `ruff format api/db/models.py alembic/versions/20260619_0021_domestic_sweep_control.py tests/domestic_enrich/test_sweep_model.py && ruff check .`

- [ ] **Step 6: Commit**

```bash
git add app/backend/api/db/models.py \
        app/backend/alembic/versions/20260619_0021_domestic_sweep_control.py \
        app/backend/tests/domestic_enrich/test_sweep_model.py
git commit -m "$(printf 'feat(domestic): domestic_sweep_control singleton model + migration\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Sweep RQ job + queue registration

**Files:**
- Create: `app/backend/worker/domestic_sweep.py`
- Modify: `app/backend/worker/run_worker.py`
- Test: `app/backend/tests/domestic_enrich/test_sweep_job.py`

- [ ] **Step 1: Write the failing test** `app/backend/tests/domestic_enrich/test_sweep_job.py` (mirror `tests/test_madrid_sweep_job.py`; monkeypatch `enrich_one`, `iter_domestic_appnos`, `_cache_dir`, and pass a no-op `enqueue_next`):

```python
import pytest
from sqlalchemy import select, update

import worker.domestic_sweep as ds
from api.db.models import DomesticSweepControl as C


async def _set_running(session, **vals):
    await session.execute(update(C).where(C.id == 1).values(status="running", **vals))
    await session.commit()


@pytest.mark.asyncio
async def test_chunk_processes_uncached_and_stops_at_chunk_size(db_session, tmp_path, monkeypatch):
    await _set_running(db_session, chunk_size=2, delay=0.0, jitter=0.0)

    async def fake_iter(session):
        return ["4-2026-00001", "4-2026-00002", "4-2026-00003"]

    seen = []

    async def fake_enrich(session, appno, cache, *, http_session=None, use_cache=True):
        seen.append(appno)
        return True

    monkeypatch.setattr(ds, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(ds, "enrich_one", fake_enrich)
    monkeypatch.setattr(ds, "_cache_dir", lambda: tmp_path)

    enq = []
    res = await ds.run_chunk(db_session, enqueue_next=lambda: enq.append(1))

    assert res["did"] == 2                       # stopped at chunk_size
    assert seen == ["4-2026-00001", "4-2026-00002"]
    assert enq == [1]                            # more remain → re-enqueued
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert row.processed == 2
    assert row.current_appno == "4-2026-00002"


@pytest.mark.asyncio
async def test_chunk_noop_when_not_running(db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(ds, "_cache_dir", lambda: tmp_path)
    res = await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert res["did"] == 0


@pytest.mark.asyncio
async def test_uncached_filter_uses_vnid_mapping(db_session, tmp_path, monkeypatch):
    # A cache file named by VNID must mark the matching application_number as done.
    (tmp_path / "VN4202600001.html").write_text("x", encoding="utf-8")
    await _set_running(db_session, chunk_size=10, delay=0.0, jitter=0.0)

    async def fake_iter(session):
        return ["4-2026-00001", "4-2026-00002"]  # first is already cached (VN4202600001)

    seen = []

    async def fake_enrich(session, appno, cache, *, http_session=None, use_cache=True):
        seen.append(appno)
        return True

    monkeypatch.setattr(ds, "iter_domestic_appnos", fake_iter)
    monkeypatch.setattr(ds, "enrich_one", fake_enrich)
    monkeypatch.setattr(ds, "_cache_dir", lambda: tmp_path)

    await ds.run_chunk(db_session, enqueue_next=lambda: None)
    assert seen == ["4-2026-00002"]              # the cached one was skipped
```
> Confirm `db_session` provides the seed control row; if not, insert `DomesticSweepControl(id=1, status="idle")` in an autouse fixture mirroring the Madrid sweep-job test.

- [ ] **Step 2: Run, confirm FAIL, then implement** `app/backend/worker/domestic_sweep.py` (copy `worker/madrid_sweep.py`; rename `irn`→`appno`, queue `domestic`, cache `domestic_cache`, and APPLY the VNID-mapping uncached filter):

```python
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


async def _ctl(session: AsyncSession) -> dict:
    row = (
        await session.execute(
            select(C.status, C.cap, C.delay, C.jitter, C.chunk_size, C.processed, C.ok, C.failed).where(C.id == 1)
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
```

- [ ] **Step 3: Register the `domestic` queue** in `app/backend/worker/run_worker.py`. Change the queues line and the module docstring:

```python
    queues = [Queue("ingest", connection=redis), Queue("madrid", connection=redis), Queue("domestic", connection=redis)]
```
And update the docstring's first line to: `"""RQ worker entry point — listens on the `ingest`, `madrid` and `domestic` queues."""`

- [ ] **Step 4: Run** `python -m pytest tests/domestic_enrich/test_sweep_job.py -v` → PASS (3 tests). **Format + lint** the two new/changed worker files + test.

- [ ] **Step 5: Commit**

```bash
git add app/backend/worker/domestic_sweep.py app/backend/worker/run_worker.py app/backend/tests/domestic_enrich/test_sweep_job.py
git commit -m "$(printf 'feat(domestic): chunked self-re-enqueuing sweep job on the domestic queue\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Control API + router registration

**Files:**
- Create: `app/backend/api/routes/domestic_sweep.py`
- Modify: `app/backend/api/main.py` (import + include the router)
- Test: `app/backend/tests/domestic_enrich/test_sweep_control.py`

- [ ] **Step 1: Write the failing endpoint test** `app/backend/tests/domestic_enrich/test_sweep_control.py` (mirror `tests/test_madrid_sweep_control.py`; copy its admin-client fixture + `_enqueue_chunk` monkeypatch, swapping the URL prefix to `/api/v1/admin/domestic-sweep` and the model to `DomesticSweepControl`). Cover: GET status; start (idle→running, enqueues); start again → 409; pause (running→paused); pause when idle → 409; resume (paused→running); stop (→idle); config patch persists cadence. INSPECT `tests/test_madrid_sweep_control.py` for the exact fixture wiring (auth + enqueue stub) before writing.

- [ ] **Step 2: Run, confirm FAIL, then implement** `app/backend/api/routes/domestic_sweep.py` (copy `api/routes/madrid_sweep.py`; rename prefix, model, `irn`→`appno`, and point `_enqueue_chunk` at `worker.domestic_sweep`):

```python
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
    return (await session.execute(select(DomesticSweepControl).where(DomesticSweepControl.id == 1))).scalar_one()


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
```

- [ ] **Step 2b: Register the router** in `app/backend/api/main.py`: add `domestic_sweep` to the routes import block (near line 29, alongside `madrid_sweep`) and add `app.include_router(domestic_sweep.router)` immediately after the `madrid_sweep.router` include (line 141).

- [ ] **Step 3: Run** `python -m pytest tests/domestic_enrich/test_sweep_control.py -v` → PASS. **Format + lint** the new route file + main.py + test.

- [ ] **Step 4: Commit**

```bash
git add app/backend/api/routes/domestic_sweep.py app/backend/api/main.py app/backend/tests/domestic_enrich/test_sweep_control.py
git commit -m "$(printf 'feat(domestic): sweep control API (start/pause/resume/stop/config, 409-guarded)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: Coverage stats endpoint

**Files:**
- Modify: `app/backend/api/routes/admin.py` (add `/domestic-enrichment`)
- Test: `app/backend/tests/domestic_enrich/test_admin_stats.py`

- [ ] **Step 1: Write the failing test** `app/backend/tests/domestic_enrich/test_admin_stats.py` (mirror `tests/test_admin_madrid_stats.py`: seed a couple of `Trademark` rows with `mark_category in (domestic_application, domestic_registration)` + an `application_number`, and a couple of `DomesticRecord` rows — one with a `grant_date`, then GET `/api/v1/admin/domestic-enrichment` as admin and assert `unique_appnos`, `validated`, `remaining`, `by_category`, `granted`). INSPECT `tests/test_admin_madrid_stats.py` for the admin-client fixture + seeding helpers.

- [ ] **Step 2: Implement** in `app/backend/api/routes/admin.py`. Add near the Madrid constant: `_DOMESTIC_CATEGORIES = ("domestic_application", "domestic_registration")`. Add the response model next to `MadridEnrichmentStats`:

```python
class DomesticEnrichmentStats(BaseModel):
    unique_appnos: int
    validated: int
    remaining: int
    pct_complete: float  # 0.0–1.0
    granted: int
    by_category: dict[str, int]
```

And the endpoint (mirror `madrid_enrichment`; "granted" = `DomesticRecord.grant_date IS NOT NULL`, matching Plan A's derive rule). Import `DomesticRecord` alongside `MadridRecord` in admin.py:

```python
@router.get("/domestic-enrichment", response_model=DomesticEnrichmentStats)
async def domestic_enrichment(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DomesticEnrichmentStats:
    """Live domestic-enrichment coverage, derived from the DB at request time.

    unique_appnos = distinct domestic application_numbers (= the sweep work-list);
    validated = domestic_records rows; remaining = unique - validated.
    """
    unique_appnos = (
        await session.execute(
            select(func.count(distinct(Trademark.application_number)))
            .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            .where(Trademark.application_number.is_not(None))
        )
    ).scalar_one()
    cat_rows = (
        await session.execute(
            select(Trademark.mark_category, func.count(distinct(Trademark.application_number)))
            .where(Trademark.mark_category.in_(_DOMESTIC_CATEGORIES))
            .where(Trademark.application_number.is_not(None))
            .group_by(Trademark.mark_category)
        )
    ).all()
    by_category = {c: n for c, n in cat_rows}
    for c in _DOMESTIC_CATEGORIES:
        by_category.setdefault(c, 0)
    validated = (await session.execute(select(func.count()).select_from(DomesticRecord))).scalar_one()
    granted = (
        await session.execute(
            select(func.count()).select_from(DomesticRecord).where(DomesticRecord.grant_date.is_not(None))
        )
    ).scalar_one()
    return DomesticEnrichmentStats(
        unique_appnos=unique_appnos,
        validated=validated,
        remaining=max(unique_appnos - validated, 0),
        pct_complete=(validated / unique_appnos) if unique_appnos else 0.0,
        granted=granted,
        by_category=by_category,
    )
```

- [ ] **Step 3: Run** `python -m pytest tests/domestic_enrich/test_admin_stats.py -v` → PASS. **Format + lint.**

- [ ] **Step 4: Commit**

```bash
git add app/backend/api/routes/admin.py app/backend/tests/domestic_enrich/test_admin_stats.py
git commit -m "$(printf 'feat(domestic): /domestic-enrichment coverage stats endpoint\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: Full-suite green + drift check + docs sync

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Full backend suite + drift + lint (the three CI gates):**

```bash
cd app/backend && source ../.venv/bin/activate
ruff check . && ruff format --check .
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic check
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm python -m pytest -q
```
Expected: ruff clean, `No new upgrade operations detected.`, all tests pass.

- [ ] **Step 2: Docs sync.** In `CLAUDE.md`, extend the `domestic_enrich/` description (from Plan A) to note the controllable sweep is now live: admin start/pause/resume/stop/tune at `/api/v1/admin/domestic-sweep`, coverage at `/api/v1/admin/domestic-enrichment`, RQ job on the `domestic` queue (worker must run). Mirror the wording the file uses for the Madrid sweep. Note Plan C (frontend `/admin/domestic` panel + detail block) is the remaining piece.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "$(printf 'docs(domestic): record controllable sweep + control endpoints\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage** (§Sweep, §Control API + admin panel stats, §Error handling, §queue):
- `domestic_sweep_control` table + model → Task 1. ✅
- Chunked self-re-enqueuing job, cap/pause/stop/circuit-breaker, `domestic` queue → Task 2. ✅
- Control endpoints (start/pause/resume/stop/config, 409) → Task 3. ✅
- `/domestic-enrichment` coverage stats → Task 4. ✅
- Queue registration in `run_worker.py` + router in `main.py` → Tasks 2, 3. ✅
- **Admin panel UI** (`/admin/domestic` page) → **Plan C** (frontend), out of scope here. ✅

**Type/name consistency:** `DomesticSweepControl` columns (`current_appno`/`next_appno`) match across model (T1), job (T2), route `SweepControlOut` (T3). `iter_domestic_appnos`/`enrich_one`/`appno_to_vnid` are the Plan-A names. `_uncached` is used in both the chunk loop and the continuation check.

**The cache/work-list key-mismatch** (VNID cache vs appno work-list) is handled once in `_uncached()` and covered by `test_uncached_filter_uses_vnid_mapping`. This is the one place this plan diverges from a pure Madrid copy.

**CI gotchas carried from Plan A:** the control table has only a CheckConstraint (no GIN index to declare), ruff-format new files before commit, and run `alembic check` locally (Task 1 Step 3, Task 5 Step 1).
