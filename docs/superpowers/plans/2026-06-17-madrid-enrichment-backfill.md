# Madrid Enrichment — Backfill CLI (Plan 2 of 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]` checkboxes.

**Goal:** A polite, resumable backfill that enriches Madrid IRNs from WIPO — pilot mode (`--limit 100`) to validate the parser at volume, then full sweep over all ~4,439 distinct Madrid IRNs — with rate-limit rails and a circuit breaker so we never get blocked.

**Architecture:** Testable logic in `madrid_enrich/backfill.py` (IRN selection, circuit breaker, the run loop), driven by a thin `scripts/enrich_madrid.py` CLI. Reuses `enrich_one()` from Plan 1. Tests mock the enrich call — **no live WIPO during the build**; the live pilot is a separate, explicit run after the code is green.

**Tech Stack:** Python 3.13, SQLAlchemy 2 async, argparse, pytest. Builds on Plan 1's `madrid_enrich` package.

**Spec:** `docs/superpowers/specs/2026-06-17-madrid-wipo-enrichment-design.md` §6–7. **Depends on:** Plan 1 (branch `madrid-enrichment`).

---

## File Structure
- `app/backend/madrid_enrich/backfill.py` — **create**: `iter_madrid_irns`, `CircuitBreaker`, `BackfillResult`, `run_backfill`.
- `app/backend/scripts/enrich_madrid.py` — **create**: argparse CLI wiring an async session → `run_backfill`.
- `app/backend/tests/madrid_enrich/test_backfill.py` — **create**: tests (mocked enrich).

---

## Task 1: IRN selection — `iter_madrid_irns`

**Files:** Create `app/backend/madrid_enrich/backfill.py`; test `tests/madrid_enrich/test_backfill.py`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from madrid_enrich.backfill import iter_madrid_irns
```

The assertion that matters: only IRNs of rows with `mark_category IN ('madrid_registration','madrid_renewal')` come back, de-duplicated, as `lineage_key`; domestic rows are excluded. **Adapt row construction to the codebase** — `Trademark` needs a valid `gazette_id` FK and likely other non-null fields. Inspect how the suite already builds rows: `grep -rn "Trademark(\|Gazette(" app/backend/tests`. Use the same factory/fixture. Sketch:

```python
@pytest.mark.asyncio
async def test_iter_madrid_irns_returns_distinct_madrid_only(db_session):
    g = await _make_gazette(db_session)  # however the suite makes one
    db_session.add_all([
        # madrid_renewal: madrid_number only -> mark_category derives to madrid_renewal
        Trademark(gazette_id=g.id, record_type="B_madrid", madrid_number="1266721"),
        # domestic_registration: certificate + application -> excluded
        Trademark(gazette_id=g.id, record_type="B_domestic",
                  certificate_number="4-2025-1", application_number="4-2025-1"),
    ])
    await db_session.flush()
    irns = await iter_madrid_irns(db_session)
    assert "1266721" in irns
    assert "4-2025-1" not in irns
```

- [ ] **Step 2: Run → fail** (`ModuleNotFoundError: madrid_enrich.backfill`).

- [ ] **Step 3: Implement** `backfill.py`:

```python
"""Polite, resumable WIPO backfill over Madrid IRNs."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Trademark

_MADRID_CATEGORIES = ("madrid_registration", "madrid_renewal")


async def iter_madrid_irns(session: AsyncSession) -> list[str]:
    """Distinct WIPO IRNs (= trademarks.lineage_key) for Madrid rows."""
    rows = (
        await session.execute(
            select(Trademark.lineage_key)
            .where(Trademark.mark_category.in_(_MADRID_CATEGORIES))
            .where(Trademark.lineage_key.is_not(None))
            .distinct()
        )
    ).scalars().all()
    return [r for r in rows if r]
```

- [ ] **Step 4: Run → pass. Lint** (`ruff format/check`, `mypy`) — commit at end of Task 3.

---

## Task 2: Circuit breaker

**Files:** Modify `backfill.py`; tests in `test_backfill.py`.

- [ ] **Step 1: Write the failing test**

```python
from madrid_enrich.backfill import CircuitBreaker


def test_circuit_breaker_trips_after_consecutive_failures():
    cb = CircuitBreaker(max_consecutive=3)
    cb.record_failure(); cb.record_failure()
    assert cb.tripped is False
    cb.record_failure()
    assert cb.tripped is True


def test_circuit_breaker_resets_on_success():
    cb = CircuitBreaker(max_consecutive=3)
    cb.record_failure(); cb.record_failure()
    cb.record_success()
    cb.record_failure(); cb.record_failure()
    assert cb.tripped is False
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** in `backfill.py`:

```python
class CircuitBreaker:
    """Trips after N consecutive failures so a WIPO outage / rate-block halts
    the batch instead of hammering. Any success resets the streak."""

    def __init__(self, max_consecutive: int = 5) -> None:
        self.max_consecutive = max_consecutive
        self._streak = 0

    @property
    def tripped(self) -> bool:
        return self._streak >= self.max_consecutive

    def record_failure(self) -> None:
        self._streak += 1

    def record_success(self) -> None:
        self._streak = 0
```

- [ ] **Step 4: Run → pass. Lint.**

---

## Task 3: The run loop — `run_backfill`

**Files:** Modify `backfill.py`; tests.

- [ ] **Step 1: Write the failing test** (mocks enrich — no network)

```python
import madrid_enrich.backfill as bf
from madrid_enrich.backfill import BackfillResult, run_backfill


async def _async_return(value):
    return value


@pytest.mark.asyncio
async def test_run_backfill_respects_limit_and_counts(db_session, tmp_path, monkeypatch):
    calls = []

    async def fake_enrich(session, irn, cache_dir, **kw):
        calls.append(irn)
        return True

    monkeypatch.setattr(bf, "enrich_one", fake_enrich)
    monkeypatch.setattr(bf, "iter_madrid_irns", lambda s: _async_return(["a", "b", "c", "d", "e"]))

    res = await run_backfill(db_session, cache_dir=tmp_path, limit=3, delay=0.0)
    assert isinstance(res, BackfillResult)
    assert res.attempted == 3 and res.written == 3
    assert calls == ["a", "b", "c"]


@pytest.mark.asyncio
async def test_run_backfill_circuit_breaks(db_session, tmp_path, monkeypatch):
    async def boom(session, irn, cache_dir, **kw):
        raise RuntimeError("WIPO 429")

    monkeypatch.setattr(bf, "enrich_one", boom)
    monkeypatch.setattr(bf, "iter_madrid_irns", lambda s: _async_return(list("abcdefghij")))

    res = await run_backfill(db_session, cache_dir=tmp_path, max_consecutive=3, delay=0.0)
    assert res.failed == 3 and res.circuit_broke is True
    assert res.attempted == 3
```

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement** in `backfill.py`:

```python
import asyncio
import logging
import random
from dataclasses import dataclass
from pathlib import Path

from .enrich import enrich_one  # referenced via module attr so tests can monkeypatch

log = logging.getLogger("madrid.backfill")


@dataclass
class BackfillResult:
    attempted: int = 0
    written: int = 0
    skipped: int = 0
    failed: int = 0
    circuit_broke: bool = False


async def run_backfill(
    session: AsyncSession,
    *,
    cache_dir: Path,
    limit: int | None = None,
    delay: float = 3.0,
    jitter: float = 1.0,
    max_consecutive: int = 5,
    daily_cap: int | None = None,
    force: bool = False,
    progress_every: int = 25,
) -> BackfillResult:
    """Enrich Madrid IRNs politely. Resumable: enrich_one() skips records whose
    content is unchanged (content_hash), so re-running is cheap. `limit` caps the
    count (pilot mode); `daily_cap` is a hard self-imposed network ceiling."""
    irns = await iter_madrid_irns(session)
    if limit is not None:
        irns = irns[:limit]

    res = BackfillResult()
    cb = CircuitBreaker(max_consecutive=max_consecutive)
    for irn in irns:
        if cb.tripped:
            res.circuit_broke = True
            log.warning("circuit breaker tripped after %d consecutive failures — halting", max_consecutive)
            break
        if daily_cap is not None and res.attempted >= daily_cap:
            log.info("daily cap %d reached — stopping", daily_cap)
            break
        res.attempted += 1
        try:
            wrote = await enrich_one(session, irn, cache_dir=cache_dir, use_cache=not force)
            await session.commit()
            cb.record_success()
            if wrote:
                res.written += 1
            else:
                res.skipped += 1
        except Exception as exc:  # noqa: BLE001 — one bad IRN must not kill the batch
            await session.rollback()
            res.failed += 1
            cb.record_failure()
            log.warning("enrich failed for IRN %s: %s", irn, exc)
        if res.attempted % progress_every == 0:
            log.info("progress: %d attempted (%d written, %d skipped, %d failed)",
                     res.attempted, res.written, res.skipped, res.failed)
        if delay:
            await asyncio.sleep(delay + random.uniform(0, jitter))  # noqa: S311 — jitter, not crypto
    return res
```

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Lint + commit (Tasks 1–3)**

```bash
cd app/backend && ruff format madrid_enrich/backfill.py tests/madrid_enrich/test_backfill.py \
  && ruff check madrid_enrich/backfill.py && mypy madrid_enrich/backfill.py
git add app/backend/madrid_enrich/backfill.py app/backend/tests/madrid_enrich/test_backfill.py
git commit -m "feat(madrid): resumable backfill loop with circuit breaker"
```

---

## Task 4: CLI — `scripts/enrich_madrid.py`

**Files:** Create `app/backend/scripts/enrich_madrid.py`.

> Match the codebase's async-session construction: `cat app/backend/scripts/smoke_ingest.py` and `grep -rn "async_session\|async_sessionmaker\|get_session\|data_dir" app/backend/api`. Use the same factory below (names may differ — this is the only file that touches them).

- [ ] **Step 1: Implement the CLI**

```python
"""Backfill WIPO Madrid enrichment for the Madrid IRNs in the DB.

Pilot 100:   python -m scripts.enrich_madrid --limit 100
Full sweep:  python -m scripts.enrich_madrid
Re-fetch:    python -m scripts.enrich_madrid --force --limit 50

Politeness: ~`--delay` s between live fetches (+ jitter), a circuit breaker on
consecutive failures, and an optional `--daily-cap`. Resumable — unchanged
records are skipped via content hash, so re-runs are cheap.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from api.db.session import async_session  # adjust to the project's factory
from api.settings import get_settings
from madrid_enrich.backfill import run_backfill


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="WIPO Madrid enrichment backfill")
    p.add_argument("--limit", type=int, default=None, help="cap IRNs (pilot mode)")
    p.add_argument("--delay", type=float, default=3.0, help="seconds between live fetches")
    p.add_argument("--jitter", type=float, default=1.0)
    p.add_argument("--daily-cap", type=int, default=None, help="hard network ceiling")
    p.add_argument("--max-consecutive", type=int, default=5, help="circuit-breaker threshold")
    p.add_argument("--force", action="store_true", help="ignore raw-HTML cache, re-fetch")
    p.add_argument("--cache-dir", type=Path, default=None)
    return p.parse_args()


async def _main() -> None:
    args = _parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cache_dir = args.cache_dir or (get_settings().data_dir / "madrid_cache")
    async with async_session() as session:
        res = await run_backfill(
            session, cache_dir=cache_dir, limit=args.limit, delay=args.delay,
            jitter=args.jitter, daily_cap=args.daily_cap,
            max_consecutive=args.max_consecutive, force=args.force,
        )
    logging.getLogger("madrid.backfill").info(
        "DONE: attempted=%d written=%d skipped=%d failed=%d circuit_broke=%s",
        res.attempted, res.written, res.skipped, res.failed, res.circuit_broke,
    )


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 2: Smoke-check imports + help** (no network):

```bash
cd app/backend && python -m scripts.enrich_madrid --help
```
Expected: argparse help prints, exit 0. If `async_session` / `data_dir` names differ, fix the imports here to match the codebase.

- [ ] **Step 3: Lint + commit**

```bash
cd app/backend && ruff format scripts/enrich_madrid.py && ruff check scripts/enrich_madrid.py && mypy scripts/enrich_madrid.py
git add app/backend/scripts/enrich_madrid.py
git commit -m "feat(madrid): backfill CLI (pilot --limit / full sweep)"
```

---

## Task 5: Full-suite gate + docs

- [ ] **Step 1: Whole backend suite green** (both URLs use password `tm`)

```bash
cd app/backend
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -m pytest tests/ -q
```
Expected: all pass (Plan 1's 180 + the new backfill tests).

- [ ] **Step 2: Doc** — add to `app/README.md` dev-workflow a one-liner:

```
Backfill WIPO Madrid data: `cd app/backend && python -m scripts.enrich_madrid --limit 100`  (pilot; drop --limit for full sweep)
```

- [ ] **Step 3: Commit**

```bash
git add app/README.md
git commit -m "docs(madrid): backfill CLI usage"
```

---

## Out of scope (later plans)
- **Worker auto-enrich hook** → Plan 2b (sync-worker / async-`enrich_one` bridge).
- **Refresh scheduling** (status-aware TTL) → Plan 4. `run_backfill` is refresh-ready (skips unchanged, accepts `daily_cap`).

## Self-Review
- **Spec coverage:** pilot→full §7 → `--limit` (Task 3/4) ✓; politeness rails §6 (delay+jitter, circuit breaker, daily cap, resume-via-content-hash) → Tasks 2–3 ✓; distinct-IRN selection → Task 1 ✓. Worker hook + refresh explicitly deferred.
- **Placeholders:** none — full code + commands; adaptation points (test factories, session factory) called out with the exact grep to resolve them.
- **Type consistency:** `iter_madrid_irns(session) -> list[str]`; `CircuitBreaker(max_consecutive=)`; `run_backfill(session, *, cache_dir, limit, delay, jitter, max_consecutive, daily_cap, force, progress_every) -> BackfillResult` consistent across Tasks 1–4; `enrich_one` referenced via module attribute so the Task 3 monkeypatch works.
- **No live WIPO in tests** — `enrich_one`/`iter_madrid_irns` monkeypatched; the real pilot is a separate explicit step.
