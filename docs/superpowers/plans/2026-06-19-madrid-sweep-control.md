# Madrid Sweep Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin start / pause / resume / stop / tune the Madrid WIPO enrichment sweep from `/admin/madrid`, backed by a chunked self-re-enqueuing RQ job whose state lives in a `madrid_sweep_control` DB row.

**Architecture:** A singleton control row holds status + cadence + live counters. An RQ job on a new `madrid` queue processes up to `chunk_size` uncached IRNs per run via the existing `enrich_one`, re-reading the control row each IRN (so pause/stop/cadence edits land live), then re-enqueues itself while `status='running'`. Admin endpoints drive state transitions; the `/admin/madrid` page gains a control card.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic + RQ/Redis (backend), pytest/httpx (tests), Next.js 15 + Tailwind 4 (frontend).

**Source spec:** `docs/superpowers/specs/2026-06-19-madrid-sweep-control-design.md`

**Standing constraints:** Commit ONLY by EXPLICIT path; NEVER `git add -A`/`.`; NEVER stage the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). A GateGuard hook may block the first Edit/Write per file and first Bash — comply with the facts then retry.

**Run env (backend, from repo root):**
```
cd app/backend && source ../.venv/bin/activate && export TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm TM_REDIS_URL=redis://localhost:6380/0
```

---

## File Structure

- **Modify** `app/backend/api/db/models.py` — add `MadridSweepControl` model.
- **Modify** `app/backend/api/db/__init__.py` — re-export `MadridSweepControl`.
- **Create** `app/backend/alembic/versions/20260619_0018_madrid_sweep_control.py` — table + singleton seed.
- **Create** `app/backend/worker/madrid_sweep.py` — the chunked RQ job (`run_chunk` async core + `run_sweep_chunk` sync entry).
- **Modify** `app/backend/worker/run_worker.py` — listen on `ingest` + `madrid`.
- **Create** `app/backend/api/routes/madrid_sweep.py` — 6 admin endpoints.
- **Modify** `app/backend/api/main.py` — mount the new router.
- **Create** `app/backend/tests/test_madrid_sweep_control.py` — endpoint tests.
- **Create** `app/backend/tests/test_madrid_sweep_job.py` — job-logic tests.
- **Modify** `app/frontend/lib/api.ts` — `MadridSweepControl` type + 6 methods.
- **Modify** `app/frontend/app/(app)/admin/madrid/page.tsx` — add the control card.
- **Modify** `CLAUDE.md`, `app/README.md` — document the worker/`madrid` queue + sweep control.

---

### Task 1: `MadridSweepControl` model + migration

**Files:**
- Modify: `app/backend/api/db/models.py`
- Modify: `app/backend/api/db/__init__.py`
- Create: `app/backend/alembic/versions/20260619_0018_madrid_sweep_control.py`

**Context:** Models are SQLAlchemy 2.0 (`Mapped`/`mapped_column`), `Base` from this module. The current Alembic head is `20260618_0017` (so `down_revision = "20260618_0017"`). `env.py` runs a drift check — keep model `server_default`s identical to the migration so autogenerate sees no diff. Status is text + CHECK (mirrors the enum-as-text style used for `mark_category`).

- [ ] **Step 1: Add imports + model to `models.py`**

In the top-of-file `from sqlalchemy import (...)` block, ensure these names are present (add any missing): `CheckConstraint`, `Float`, `func`. Then append this model at the end of the file:

```python
class MadridSweepControl(Base):
    """Singleton (id=1) control + live state for the Madrid enrichment sweep.

    Written by the RQ job (worker.madrid_sweep) and the admin control endpoints;
    read by the /admin/madrid panel. Derived coverage counts stay on the
    /madrid-enrichment endpoint — this row is process/control state only.
    """

    __tablename__ = "madrid_sweep_control"
    __table_args__ = (
        CheckConstraint(
            "status IN ('idle','running','paused','stopping')",
            name="ck_madrid_sweep_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # always 1
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="idle")
    cap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delay: Mapped[float] = mapped_column(Float, nullable=False, server_default="8.0")
    jitter: Mapped[float] = mapped_column(Float, nullable=False, server_default="2.0")
    chunk_size: Mapped[int] = mapped_column(Integer, nullable=False, server_default="25")
    processed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    ok: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_irn: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2: Re-export from `api/db/__init__.py`**

Add `MadridSweepControl` to the `from .models import ...` line and to the `__all__` list in `app/backend/api/db/__init__.py`.

- [ ] **Step 3: Write the migration**

Create `app/backend/alembic/versions/20260619_0018_madrid_sweep_control.py`:

```python
"""madrid_sweep_control singleton control row

Revision ID: 20260619_0018
Revises: 20260618_0017
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260619_0018"
down_revision = "20260618_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "madrid_sweep_control",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="idle"),
        sa.Column("cap", sa.Integer(), nullable=True),
        sa.Column("delay", sa.Float(), nullable=False, server_default="8.0"),
        sa.Column("jitter", sa.Float(), nullable=False, server_default="2.0"),
        sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_irn", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "status IN ('idle','running','paused','stopping')",
            name="ck_madrid_sweep_status",
        ),
    )
    op.execute("INSERT INTO madrid_sweep_control (id, status) VALUES (1, 'idle')")


def downgrade() -> None:
    op.drop_table("madrid_sweep_control")
```

- [ ] **Step 4: Apply + verify**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm alembic upgrade head`
Expected: upgrade runs to `20260619_0018`. Then verify the singleton:
`TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm python -c "from sqlalchemy import create_engine,text; e=create_engine('postgresql+psycopg2://tm:tm@localhost:5435/tm'); print(e.connect().execute(text('select id,status,delay,chunk_size from madrid_sweep_control')).all())"`
Expected: `[(1, 'idle', 8.0, 25)]`.

- [ ] **Step 5: Commit**

```bash
git add app/backend/api/db/models.py app/backend/api/db/__init__.py app/backend/alembic/versions/20260619_0018_madrid_sweep_control.py
git commit -m "feat(madrid): madrid_sweep_control table + model"
```

---

### Task 2: RQ job `worker/madrid_sweep.py` + worker queue

**Files:**
- Create: `app/backend/worker/madrid_sweep.py`
- Modify: `app/backend/worker/run_worker.py`
- Test: `app/backend/tests/test_madrid_sweep_job.py`

**Context:** The job mirrors the proven `/tmp` resume loop but reads its control state from `madrid_sweep_control` each IRN. It bridges sync→async via `asyncio.run` (the worker is sync; `enrich_one`/`iter_madrid_irns` are async). Control-row writes go through `_set` (a committed `UPDATE`) so they're never rolled back with `enrich_one`'s per-IRN transaction. The cache dir is `get_settings().data_dir / "madrid_cache"` (`data_dir` resolves to the project root). `enrich_one(session, irn, cache_dir, *, http_session=..., use_cache=True)` is the existing async fetch+upsert.

- [ ] **Step 1: Write the failing job tests**

Create `app/backend/tests/test_madrid_sweep_job.py`:

```python
"""worker.madrid_sweep.run_chunk — chunk processing + control honoring.

enrich_one and iter_madrid_irns are monkeypatched so the test needs no live
WIPO, no worker, and no real cache writes. Synthetic IRNs (never cached) keep
the work-list deterministic.
"""

from __future__ import annotations

import pytest
from sqlalchemy import delete, insert, select, update

from api.db.models import MadridSweepControl
import worker.madrid_sweep as ms


async def _aslist(items):
    return items


class _EmptyCache:
    """Stand-in for a Path whose .glob('*.html') yields nothing."""

    def glob(self, _pat):
        return iter(())


async def _reset(session, **vals) -> None:
    await session.execute(delete(MadridSweepControl))
    base = dict(id=1, status="running", cap=None, delay=0.0, jitter=0.0,
                chunk_size=2, processed=0, ok=0, failed=0)
    base.update(vals)
    await session.execute(insert(MadridSweepControl).values(**base))
    await session.commit()


@pytest.mark.asyncio
async def test_run_chunk_processes_chunk_and_reenqueues(db_session, monkeypatch):
    await _reset(db_session, chunk_size=2)

    async def fake_enrich(session, irn, cache, **kw):
        return None

    monkeypatch.setattr(ms, "enrich_one", fake_enrich)
    monkeypatch.setattr(ms, "iter_madrid_irns", lambda s: _aslist(["A1", "A2", "A3"]))
    monkeypatch.setattr(ms, "_cache_dir", lambda: _EmptyCache())

    calls = []
    out = await ms.run_chunk(db_session, enqueue_next=lambda: calls.append(1))

    row = (await db_session.execute(select(MadridSweepControl).where(MadridSweepControl.id == 1))).scalar_one()
    assert out["did"] == 2
    assert row.ok == 2 and row.processed == 2
    assert calls == [1]


@pytest.mark.asyncio
async def test_run_chunk_honors_pause_midchunk(db_session, monkeypatch):
    await _reset(db_session, chunk_size=10)
    seen = {"n": 0}

    async def fake_enrich(session, irn, cache, **kw):
        seen["n"] += 1
        if seen["n"] == 1:
            await session.execute(
                update(MadridSweepControl).where(MadridSweepControl.id == 1).values(status="paused")
            )
            await session.commit()
        return None

    monkeypatch.setattr(ms, "enrich_one", fake_enrich)
    monkeypatch.setattr(ms, "iter_madrid_irns", lambda s: _aslist(["A1", "A2", "A3"]))
    monkeypatch.setattr(ms, "_cache_dir", lambda: _EmptyCache())

    calls = []
    out = await ms.run_chunk(db_session, enqueue_next=lambda: calls.append(1))
    assert out["did"] == 1
    assert calls == []


@pytest.mark.asyncio
async def test_run_chunk_circuit_breaker_pauses(db_session, monkeypatch):
    await _reset(db_session, chunk_size=20)

    async def boom(session, irn, cache, **kw):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr(ms, "enrich_one", boom)
    monkeypatch.setattr(ms, "iter_madrid_irns", lambda s: _aslist([f"A{i}" for i in range(10)]))
    monkeypatch.setattr(ms, "_cache_dir", lambda: _EmptyCache())

    out = await ms.run_chunk(db_session, enqueue_next=lambda: None)
    row = (await db_session.execute(select(MadridSweepControl).where(MadridSweepControl.id == 1))).scalar_one()
    assert row.status == "paused"
    assert row.failed >= 5
    assert "circuit breaker" in (row.last_error or "")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest tests/test_madrid_sweep_job.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'worker.madrid_sweep'`.

- [ ] **Step 3: Implement the job**

Create `app/backend/worker/madrid_sweep.py`:

```python
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

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


def _cache_dir() -> Path:
    return get_settings().data_dir / "madrid_cache"


def _real_enqueue() -> None:
    redis = Redis.from_url(get_settings().redis_url)
    Queue(QUEUE_NAME, connection=redis).enqueue(run_sweep_chunk)


async def _ctl(session: AsyncSession) -> dict:
    """Snapshot the control row as a plain dict (no ORM identity to expire)."""
    row = (
        await session.execute(
            select(
                C.status, C.cap, C.delay, C.jitter, C.chunk_size,
                C.processed, C.ok, C.failed,
            ).where(C.id == 1)
        )
    ).one()
    return dict(row._mapping)


async def _set(session: AsyncSession, **vals) -> None:
    vals["updated_at"] = datetime.now(timezone.utc)
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
    for irn in todo:
        ctl = await _ctl(session)
        if ctl["status"] != "running":
            break
        if ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]:
            await _set(session, status="idle", current_irn=None)
            break
        try:
            await enrich_one(session, irn, cache, http_session=http, use_cache=True)
            await session.commit()
            await _set(session, ok=ctl["ok"] + 1, processed=ctl["processed"] + 1,
                       current_irn=irn, last_error=None)
            streak = 0
        except Exception as e:  # noqa: BLE001
            await session.rollback()
            streak += 1
            await _set(session, failed=ctl["failed"] + 1, processed=ctl["processed"] + 1,
                       current_irn=irn, last_error=str(e)[:300])
        did += 1
        if streak >= _MAX_CONSECUTIVE:
            await _set(session, status="paused",
                       last_error=f"circuit breaker: {streak} consecutive failures")
            break
        if did >= ctl["chunk_size"]:
            break
        time.sleep(ctl["delay"] + random.uniform(0, ctl["jitter"]))

    # Continuation decision.
    ctl = await _ctl(session)
    if ctl["status"] == "stopping":
        await _set(session, status="idle", current_irn=None)
    elif ctl["status"] == "running":
        cached_now = {p.stem for p in cache.glob("*.html")}
        remaining = [i for i in all_irns if i not in cached_now]
        cap_hit = ctl["cap"] is not None and ctl["processed"] >= ctl["cap"]
        if remaining and not cap_hit:
            enqueue_next()
        else:
            await _set(session, status="idle", current_irn=None)
    return {"status": ctl["status"], "did": did}


def run_sweep_chunk() -> dict:
    """RQ entry point (sync) — bridges to the async core like worker.ingest."""

    async def _inner() -> dict:
        async with async_session() as s:
            return await run_chunk(s)

    return asyncio.run(_inner())
```

- [ ] **Step 4: Wire the worker to the `madrid` queue**

In `app/backend/worker/run_worker.py`, replace:
```python
    queue = Queue("ingest", connection=redis)
    worker = Worker([queue], connection=redis)
```
with:
```python
    queues = [Queue("ingest", connection=redis), Queue("madrid", connection=redis)]
    worker = Worker(queues, connection=redis)
```
Also update the module docstring's first line to: `"""RQ worker entry point — listens on the `ingest` and `madrid` queues."""`.

- [ ] **Step 5: Run job tests to verify they pass**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest tests/test_madrid_sweep_job.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/backend/worker/madrid_sweep.py app/backend/worker/run_worker.py app/backend/tests/test_madrid_sweep_job.py
git commit -m "feat(madrid): chunked self-re-enqueuing sweep RQ job + madrid queue"
```

---

### Task 3: Control API `api/routes/madrid_sweep.py`

**Files:**
- Create: `app/backend/api/routes/madrid_sweep.py`
- Modify: `app/backend/api/main.py`
- Test: `app/backend/tests/test_madrid_sweep_control.py`

**Context:** New router, all `require_admin`. Enqueue is imported lazily inside `_enqueue_chunk` (so importing the router doesn't require redis/rq at import time, and so tests can monkeypatch it). State transitions reject illegal moves with **409**. `require_admin` is in `api/auth.py`; `get_session` from `..db`; conftest provides `authed_client` (admin) and `viewer_client` (403).

- [ ] **Step 1: Write the failing endpoint tests**

Create `app/backend/tests/test_madrid_sweep_control.py`:

```python
"""Admin Madrid-sweep control endpoints — state transitions + guards.

Enqueue is monkeypatched to a no-op so no worker/redis is needed. The control
row is reset to idle before each test.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from api.db.models import MadridSweepControl
from api.settings import get_settings
import api.routes.madrid_sweep as routes


@pytest_asyncio.fixture(autouse=True)
async def reset_and_stub(monkeypatch):
    monkeypatch.setattr(routes, "_enqueue_chunk", lambda: None)
    engine = create_async_engine(get_settings().database_url)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        await s.execute(
            update(MadridSweepControl).where(MadridSweepControl.id == 1).values(
                status="idle", cap=None, delay=8.0, jitter=2.0, chunk_size=25,
                processed=0, ok=0, failed=0, current_irn=None, last_error=None,
            )
        )
        await s.commit()
    yield
    await engine.dispose()


@pytest.mark.asyncio
async def test_start_then_pause_resume_stop(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/admin/madrid-sweep/start", json={"cap": 50, "delay": 5})
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "running" and d["cap"] == 50 and d["delay"] == 5 and d["started_at"]

    r = await authed_client.post("/api/v1/admin/madrid-sweep/pause")
    assert r.status_code == 200 and r.json()["status"] == "paused"

    r = await authed_client.post("/api/v1/admin/madrid-sweep/resume")
    assert r.status_code == 200 and r.json()["status"] == "running"

    r = await authed_client.post("/api/v1/admin/madrid-sweep/stop")
    assert r.status_code == 200 and r.json()["status"] in ("stopping", "idle")


@pytest.mark.asyncio
async def test_illegal_transitions_conflict(authed_client: AsyncClient):
    assert (await authed_client.post("/api/v1/admin/madrid-sweep/pause")).status_code == 409
    assert (await authed_client.post("/api/v1/admin/madrid-sweep/resume")).status_code == 409
    assert (await authed_client.post("/api/v1/admin/madrid-sweep/start", json={})).status_code == 200
    assert (await authed_client.post("/api/v1/admin/madrid-sweep/start", json={})).status_code == 409


@pytest.mark.asyncio
async def test_config_updates_cadence(authed_client: AsyncClient):
    r = await authed_client.patch("/api/v1/admin/madrid-sweep/config", json={"delay": 12, "jitter": 3, "chunk_size": 40})
    assert r.status_code == 200
    d = r.json()
    assert d["delay"] == 12 and d["jitter"] == 3 and d["chunk_size"] == 40


@pytest.mark.asyncio
async def test_requires_admin(viewer_client: AsyncClient):
    assert (await viewer_client.get("/api/v1/admin/madrid-sweep")).status_code == 403
    assert (await viewer_client.post("/api/v1/admin/madrid-sweep/start", json={})).status_code == 403
```

- [ ] **Step 2: Run to verify failure**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest tests/test_madrid_sweep_control.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'api.routes.madrid_sweep'`.

- [ ] **Step 3: Implement the router**

Create `app/backend/api/routes/madrid_sweep.py`:

```python
"""Admin control for the Madrid enrichment sweep (RQ job).

State machine: idle → running → (paused ⇄ running) → stopping → idle. Every
illegal transition is a 409. Enqueueing the first/next chunk is isolated in
_enqueue_chunk so it can be monkeypatched in tests (no redis/worker needed).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import User, require_admin
from ..db import get_session
from ..db.models import MadridSweepControl

router = APIRouter(prefix="/api/v1/admin/madrid-sweep", tags=["admin"])


class SweepControlOut(BaseModel):
    status: str
    cap: int | None
    delay: float
    jitter: float
    chunk_size: int
    processed: int
    ok: int
    failed: int
    current_irn: str | None
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
    """Enqueue one sweep chunk on the `madrid` queue. Isolated for test stubbing."""
    from redis import Redis
    from rq import Queue

    from ..settings import get_settings
    from worker.madrid_sweep import QUEUE_NAME, run_sweep_chunk

    Queue(QUEUE_NAME, connection=Redis.from_url(get_settings().redis_url)).enqueue(run_sweep_chunk)


async def _row(session: AsyncSession) -> MadridSweepControl:
    return (
        await session.execute(select(MadridSweepControl).where(MadridSweepControl.id == 1))
    ).scalar_one()


def _now() -> datetime:
    return datetime.now(timezone.utc)


@router.get("", response_model=SweepControlOut)
async def get_status(
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MadridSweepControl:
    return await _row(session)


@router.post("/start", response_model=SweepControlOut)
async def start(
    body: CadenceBody,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MadridSweepControl:
    row = await _row(session)
    if row.status != "idle":
        raise HTTPException(409, f"sweep is {row.status}; stop it before starting a new run")
    row.status = "running"
    row.processed = row.ok = row.failed = 0
    row.current_irn = None
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
) -> MadridSweepControl:
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
) -> MadridSweepControl:
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
) -> MadridSweepControl:
    row = await _row(session)
    if row.status not in ("running", "paused"):
        raise HTTPException(409, f"sweep is {row.status}; nothing to stop")
    # Paused → no chunk in flight, go idle immediately. Running → 'stopping';
    # the job converts it to 'idle' at its next per-IRN status check.
    row.status = "idle" if row.status == "paused" else "stopping"
    row.current_irn = None
    row.updated_at = _now()
    await session.commit()
    return row


@router.patch("/config", response_model=SweepControlOut)
async def config(
    body: CadenceBody,
    _: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> MadridSweepControl:
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

- [ ] **Step 4: Mount the router in `api/main.py`**

In `app/backend/api/main.py`, add `madrid_sweep` to the `from .routes import (...)` block (alongside `admin`, `stats`, …) and add `app.include_router(madrid_sweep.router)` next to the other `include_router` calls (e.g. right after `app.include_router(admin.router)`).

- [ ] **Step 5: Run endpoint tests to verify they pass**

Run: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest tests/test_madrid_sweep_control.py -v`
Expected: PASS (4 tests).

- [ ] **Step 6: Full suite + commit**

Run: `pytest -q -p no:warnings` (same env). Expected: all green.
```bash
git add app/backend/api/routes/madrid_sweep.py app/backend/api/main.py app/backend/tests/test_madrid_sweep_control.py
git commit -m "feat(madrid): admin sweep-control endpoints (start/pause/resume/stop/config)"
```

---

### Task 4: Frontend API client

**Files:**
- Modify: `app/frontend/lib/api.ts`

**Context:** Add a type + 6 methods. Mirror the existing JSON-body POST pattern already in this file (e.g. `createWatchlist`, which does `json<T>(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })`). Read that method first and copy its exact header/body shape.

- [ ] **Step 1: Add the type** (near `MadridEnrichmentStats`):

```ts
export type MadridSweepControl = {
  status: "idle" | "running" | "paused" | "stopping";
  cap: number | null;
  delay: number;
  jitter: number;
  chunk_size: number;
  processed: number;
  ok: number;
  failed: number;
  current_irn: string | null;
  last_error: string | null;
  started_at: string | null;
  updated_at: string;
};

export type SweepCadence = { cap?: number | null; delay?: number; jitter?: number; chunk_size?: number };
```

- [ ] **Step 2: Add the methods** inside the `api` object (after `adminMadridStats`):

```ts
  madridSweepStatus: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep`),
  madridSweepStart: (body: SweepCadence) =>
    json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/start`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
  madridSweepPause: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/pause`, { method: "POST" }),
  madridSweepResume: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/resume`, { method: "POST" }),
  madridSweepStop: () => json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/stop`, { method: "POST" }),
  madridSweepConfig: (body: SweepCadence) =>
    json<MadridSweepControl>(`/api/v1/admin/madrid-sweep/config`, {
      method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    }),
```

- [ ] **Step 3: Type-check + commit**

Run: `cd app/frontend && pnpm tsc --noEmit` → no errors.
```bash
git add app/frontend/lib/api.ts
git commit -m "feat(madrid): sweep-control API client methods + types"
```

---

### Task 5: Frontend control card on `/admin/madrid`

**Files:**
- Modify: `app/frontend/app/(app)/admin/madrid/page.tsx`

**Context:** Add a `SweepControlCard` component below the page header and above the stats. It fetches `api.madridSweepStatus()`, polls every 3s, and renders: status badge, action buttons (enabled per state), editable cadence inputs + Apply, and live `processed · ok · failed` / current IRN / last error. Reuse `Card`, `Button`, `Pill` from `@/components/ui` (already imported in the file) and `formatNumber` from `@/lib/format`.

- [ ] **Step 1: Add the component + render it**

In `app/frontend/app/(app)/admin/madrid/page.tsx`:

1. Extend the import from `@/lib/api` to also bring in the type:
   `import { api, type MadridEnrichmentStats, type MadridSweepControl } from "@/lib/api";`
2. Render `<SweepControlCard />` inside the page's main `<div className="max-w-container ...">`, immediately after the header block and before the progress-bar `Card`.
3. Append this component to the file:

```tsx
function SweepControlCard() {
  const [s, setS] = React.useState<MadridSweepControl | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<{ cap: string; delay: string; jitter: string; chunk_size: string }>({
    cap: "", delay: "", jitter: "", chunk_size: "",
  });

  const load = React.useCallback(async (silent = false) => {
    try {
      const next = await api.madridSweepStatus();
      setS(next);
      setErr(null);
      if (!silent) {
        setForm({
          cap: next.cap?.toString() ?? "",
          delay: next.delay.toString(),
          jitter: next.jitter.toString(),
          chunk_size: next.chunk_size.toString(),
        });
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load sweep status");
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);
  React.useEffect(() => {
    const id = setInterval(() => load(true), 3000);
    return () => clearInterval(id);
  }, [load]);

  async function act(fn: () => Promise<MadridSweepControl>) {
    setBusy(true);
    setErr(null);
    try {
      setS(await fn());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  const cadence = () => ({
    cap: form.cap.trim() === "" ? null : Number(form.cap),
    delay: Number(form.delay),
    jitter: Number(form.jitter),
    chunk_size: Number(form.chunk_size),
  });

  if (!s) return null;
  const tone = s.status === "running" ? "ok" : s.status === "paused" ? "warn" : "mute";
  const can = (st: string[]) => st.includes(s.status) && !busy;

  return (
    <Card>
      <div className="px-4 py-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">Sweep control</span>
            <Pill tone={tone as "ok" | "warn" | "mute"} size="sm">{s.status}</Pill>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="primary" disabled={!can(["idle"])} onClick={() => act(() => api.madridSweepStart(cadence()))}>Start</Button>
            <Button variant="ghost" disabled={!can(["running"])} onClick={() => act(api.madridSweepPause)}>Pause</Button>
            <Button variant="ghost" disabled={!can(["paused"])} onClick={() => act(api.madridSweepResume)}>Resume</Button>
            <Button variant="ghost" disabled={!can(["running", "paused"])} onClick={() => act(api.madridSweepStop)}>Stop</Button>
          </div>
        </div>

        <div className="flex items-end gap-2 flex-wrap">
          {(["cap", "delay", "jitter", "chunk_size"] as const).map((k) => (
            <label key={k} className="text-[11px] text-mute font-mono">
              <div className="uppercase tracking-[0.08em]">{k}</div>
              <input
                className="mt-1 w-20 rounded border border-line bg-paper px-2 py-1 text-[13px] text-ink"
                value={form[k]}
                onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
              />
            </label>
          ))}
          <Button variant="ghost" disabled={busy} onClick={() => act(() => api.madridSweepConfig(cadence()))}>Apply</Button>
        </div>

        <div className="text-[12px] text-mute">
          this run: <span className="font-mono text-ink">{formatNumber(s.processed)}</span> processed ·{" "}
          <span className="font-mono text-ok">{formatNumber(s.ok)}</span> ok ·{" "}
          <span className="font-mono text-rose-600">{formatNumber(s.failed)}</span> failed
          {s.current_irn ? <> · current <span className="font-mono text-ink">{s.current_irn}</span></> : null}
        </div>
        {s.last_error ? <div className="text-[12px] text-rose-600 truncate" title={s.last_error}>last error: {s.last_error}</div> : null}
        {err ? <div className="text-[12px] text-rose-600">{err}</div> : null}
      </div>
    </Card>
  );
}
```

Note: if `Pill`'s `tone` prop does not accept `"warn"`/`"mute"`/`"ok"`, open `app/frontend/components/ui` to find the allowed tones and map accordingly (the gazettes page uses `tone="warn"`, `tone="ok"`, `tone="mute"`, so these exist).

- [ ] **Step 2: Type-check + lint**

Run: `cd app/frontend && pnpm tsc --noEmit && pnpm exec next lint --file "app/(app)/admin/madrid/page.tsx"`
Expected: no type errors; `✔ No ESLint warnings or errors`.

- [ ] **Step 3: Commit**

```bash
git add "app/frontend/app/(app)/admin/madrid/page.tsx"
git commit -m "feat(madrid): sweep control card on the admin panel"
```

---

### Task 6: Docs + cutover

**Files:**
- Modify: `CLAUDE.md`
- Modify: `app/README.md`
- Modify: `docs/superpowers/specs/2026-06-19-madrid-sweep-control-design.md`

**Context:** Record the new control surface + the worker/`madrid` queue requirement. DO NOT touch repo-root `README.md` (rename trio) — `app/README.md` and `CLAUDE.md` are different files and safe.

- [ ] **Step 1: CLAUDE.md** — in the `madrid_enrich/` tree comment (the lines added for the admin progress view), append one continuation block (keep the `│   │   │` tree prefix + alignment):

```
│   │   │                           Sweep is a controllable RQ job on the
│   │   │                           `madrid` queue; admin start/pause/resume/
│   │   │                           stop/tune at /api/v1/admin/madrid-sweep
│   │   │                           (worker must be running).
```

- [ ] **Step 2: app/README.md** — near the worker/run instructions, add:

```
The RQ worker (`python -m worker.run_worker`) serves the `ingest` and `madrid`
queues. The `madrid` queue runs the Madrid enrichment sweep; the worker must be
running for the /admin/madrid sweep controls (start/pause/resume/stop) to act.
```
(If no worker section exists, add it under the dev-stack run steps.)

- [ ] **Step 3: Flip the spec status** in `docs/superpowers/specs/2026-06-19-madrid-sweep-control-design.md`:
`**Status:** Approved for planning · 2026-06-19` → `**Status:** Implemented · 2026-06-19`

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md app/README.md docs/superpowers/specs/2026-06-19-madrid-sweep-control-design.md
git commit -m "docs(madrid): document sweep control module + madrid queue"
```

---

## Final verification (after all tasks)

- [ ] Backend suite green: `cd app/backend && source ../.venv/bin/activate && TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm pytest -q -p no:warnings`
- [ ] Frontend clean: `cd app/frontend && pnpm tsc --noEmit && pnpm lint` (only pre-existing warnings in unrelated files).
- [ ] **Cutover:** stop the hand-launched `/tmp/madrid_resume.py` sweep (`pkill -f madrid_resume.py`) so the RQ job is the single controller. Start the worker (`python -m worker.run_worker`), then drive Start/Pause/Resume/Stop from `/admin/madrid` and confirm the live counters move and pause/resume work.
- [ ] `git status` still shows the rename trio modified-but-unstaged.
