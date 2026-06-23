# Madrid Rate-Aware Fast Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Full design: `docs/superpowers/specs/2026-06-23-madrid-fast-mode-design.md` — read it before each task.

**Goal:** Add an opt-in high-throughput "fast mode" to the Madrid (WIPO) sweep that paces concurrency to WIPO's published `X-RateLimit` budget instead of AIMD-probing for a ban.

**Architecture:** Mirrors the domestic "Dead mode": a self-contained `madrid_enrich/fast_mode/` package (pure rate-feedback `controller` + threaded `runner`) reached via one `if mode=='fast'` branch in `worker/madrid_sweep.run_chunk`. The Madrid client is finished to surface `X-RateLimit-Limit` and raise on 429/Retry-After. A `mode`/`concurrency` toggle is added to `madrid_sweep_control` (migration) and `/admin/madrid`.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), RQ worker, `requests` + `ThreadPoolExecutor` (fetch), Next.js 15 (frontend).

---

## Reference files (read these — the new code mirrors them)

- `app/backend/domestic_enrich/dead_mode/controller.py` — the pure AIMD controller; Task 3 mirrors its **shape** (pure, dataclasses, `next_concurrency`) with rate-feedback **logic**.
- `app/backend/domestic_enrich/dead_mode/runner.py` — the threaded runner (one event loop per thread, fetch on threads, store via coroutines); Task 4 adapts it for Madrid.
- `app/backend/worker/domestic_sweep.py` — the `if ctl["mode"] == "dead":` delegation branch in `run_chunk` (Task 4 mirror) + the dead-mode admin tune handling.
- `app/backend/worker/madrid_sweep.py` — the Madrid sweep to modify (`run_chunk`, `_ctl`).
- `app/backend/madrid_enrich/client.py` — the client to modify (Task 1).
- The alembic migration that added `mode`/`concurrency` to `domestic_sweep_control` (find via `grep -rl "domestic_sweep_control" app/backend/alembic/versions/`) — Task 2 mirror.
- `app/backend/api/routes/` domestic-sweep endpoint + `app/frontend/.../admin/domestic` ops panel — Task 5 mirror.

## File structure

| File | Task | Responsibility |
|---|---|---|
| `app/backend/madrid_enrich/client.py` | 1 | Surface `X-RateLimit-Limit`; raise `WipoThrottledError` on 429/Retry-After. |
| `app/backend/tests/madrid_enrich/test_client_throttle.py` | 1 | Client throttle + header tests. |
| `app/backend/alembic/versions/20260623_0025_madrid_sweep_mode.py` | 2 | Add `mode`/`concurrency` to `madrid_sweep_control`. |
| `app/backend/api/db/models.py` (MadridSweepControl) | 2 | Model columns. |
| `app/backend/madrid_enrich/fast_mode/__init__.py` | 3,4 | Public surface. |
| `app/backend/madrid_enrich/fast_mode/controller.py` | 3 | Pure rate-feedback controller. |
| `app/backend/tests/madrid_enrich/test_fast_controller.py` | 3 | Controller table tests. |
| `app/backend/madrid_enrich/fast_mode/runner.py` | 4 | Threaded fetch + coroutine store. |
| `app/backend/worker/madrid_sweep.py` | 4 | `if mode=='fast'` delegation branch. |
| `app/backend/api/routes/...madrid-sweep` | 5 | Accept `mode`/`concurrency` in tune payload. |
| `app/frontend/.../admin/madrid` panel | 5 | Mode/concurrency toggle + rate display. |

---

## Task 1: Client — surface limit + raise on 429

**Files:**
- Modify: `app/backend/madrid_enrich/client.py`
- Test: `app/backend/tests/madrid_enrich/test_client_throttle.py`

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/madrid_enrich/test_client_throttle.py
import pytest
from pathlib import Path
from madrid_enrich.client import fetch_raw, WipoThrottledError


class _Resp:
    def __init__(self, status_code, text="<html>ok</html>", headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError("raise_for_status should not run for handled 429")


class _Session:
    def __init__(self, resp):
        self._resp = resp

    def get(self, url, headers=None, timeout=None):
        return self._resp


def test_429_raises_throttled_with_retry_after(tmp_path: Path):
    sess = _Session(_Resp(429, headers={"Retry-After": "12"}))
    with pytest.raises(WipoThrottledError) as ei:
        fetch_raw("123", tmp_path, session=sess, use_cache=False)
    assert ei.value.retry_after == 12.0


def test_200_surfaces_limit_and_remaining(tmp_path: Path):
    sess = _Session(_Resp(200, headers={"X-RateLimit-Limit": "1000", "X-RateLimit-Remaining": "950"}))
    res = fetch_raw("124", tmp_path, session=sess, use_cache=False)
    assert res.rate_limit == 1000
    assert res.rate_remaining == 950
```

- [ ] **Step 2: Run → fail**

Run: `cd app/backend && ../.venv/bin/pytest tests/madrid_enrich/test_client_throttle.py -q`
Expected: FAIL — `ImportError: cannot import name 'WipoThrottledError'`.

- [ ] **Step 3: Implement** — in `app/backend/madrid_enrich/client.py`:

Add the exception + `rate_limit` field, and intercept 429 before `raise_for_status`. Replace `_http_get` + `FetchResult` + the `fetch_raw` tail:

```python
class WipoThrottledError(RuntimeError):
    """WIPO returned HTTP 429 / Retry-After. Distinct from a generic fetch
    failure: the caller should sleep `retry_after` seconds, not retry hard.
    Mirrors domestic_enrich.client.NoipBlockedError."""

    def __init__(self, retry_after: float | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(f"WIPO throttled (Retry-After {retry_after}s)")


@dataclass
class FetchResult:
    irn: str
    html: str
    source_url: str
    from_cache: bool
    rate_remaining: int | None = None
    rate_limit: int | None = None


def _retry_after_seconds(headers: dict) -> float | None:
    raw = headers.get("Retry-After")
    if not raw:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _http_get(url: str, session: requests.Session | None = None) -> tuple[str, dict]:
    s = session or requests.Session()
    resp = s.get(url, headers={"User-Agent": _UA}, timeout=30)
    if resp.status_code == 429:
        raise WipoThrottledError(_retry_after_seconds(dict(resp.headers)))
    resp.raise_for_status()
    return resp.text, dict(resp.headers)
```

Then in `fetch_raw`, after `html, headers = _http_get(...)`, set both rate fields:

```python
    rem = headers.get("X-RateLimit-Remaining")
    lim = headers.get("X-RateLimit-Limit")
    time.sleep(_MIN_DELAY_S)
    return FetchResult(
        irn=irn,
        html=html,
        source_url=url,
        from_cache=False,
        rate_remaining=int(rem) if rem and rem.isdigit() else None,
        rate_limit=int(lim) if lim and lim.isdigit() else None,
    )
```

- [ ] **Step 4: Run → pass**

Run: `cd app/backend && ../.venv/bin/pytest tests/madrid_enrich/test_client_throttle.py -q`
Expected: 2 passed.

- [ ] **Step 5: Gates + commit**

```bash
cd app/backend && ../.venv/bin/ruff format madrid_enrich/client.py tests/madrid_enrich/test_client_throttle.py \
  && ../.venv/bin/ruff check . && ../.venv/bin/mypy api worker
cd ../.. && git add app/backend/madrid_enrich/client.py app/backend/tests/madrid_enrich/test_client_throttle.py
git commit -m "feat(madrid): client surfaces X-RateLimit-Limit + raises WipoThrottledError on 429"
```

---

## Task 2: Migration — `mode` + `concurrency` on `madrid_sweep_control`

**Files:**
- Create: `app/backend/alembic/versions/20260623_0025_madrid_sweep_mode.py`
- Modify: `app/backend/api/db/models.py` (class `MadridSweepControl`)

- [ ] **Step 1: Add model columns.** In `MadridSweepControl`, mirror the domestic control's `mode`/`concurrency` columns (copy from `DomesticSweepControl` in the same file):

```python
    mode: Mapped[str] = mapped_column(String, nullable=False, server_default="normal")
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
```

- [ ] **Step 2: Generate the migration**

Run: `cd app/backend && TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm ../.venv/bin/alembic revision --autogenerate -m "madrid sweep mode"`
Then rename the generated file to `20260623_0025_madrid_sweep_mode.py` and set `down_revision = "20260623_0024"`. Confirm the upgrade adds both columns with server defaults and the downgrade drops them.

- [ ] **Step 3: Apply + verify**

Run: `cd app/backend && TM_DATABASE_URL_SYNC=... TM_DATABASE_URL=... ../.venv/bin/alembic upgrade head && ../.venv/bin/alembic check`
Expected: upgrade runs; `alembic check` → "No new upgrade operations detected."

- [ ] **Step 4: Commit**

```bash
git add app/backend/alembic/versions/20260623_0025_madrid_sweep_mode.py app/backend/api/db/models.py
git commit -m "feat(madrid): add mode/concurrency to madrid_sweep_control"
```

---

## Task 3: Pure rate-feedback controller

**Files:**
- Create: `app/backend/madrid_enrich/fast_mode/__init__.py`, `app/backend/madrid_enrich/fast_mode/controller.py`
- Test: `app/backend/tests/madrid_enrich/test_fast_controller.py`

- [ ] **Step 1: Write the failing tests**

```python
# app/backend/tests/madrid_enrich/test_fast_controller.py
from madrid_enrich.fast_mode.controller import RateWindow, next_concurrency


def test_throttle_dominates_and_pauses():
    d = next_concurrency(4, RateWindow(remaining=900, limit=1000, throttled=True))
    assert d.paused is True
    assert d.concurrency == 3  # stepped down


def test_remaining_at_or_below_floor_steps_down():
    # floor = max(50, 0.15*1000)=150
    d = next_concurrency(4, RateWindow(remaining=120, limit=1000, throttled=False))
    assert d.paused is False
    assert d.concurrency == 3


def test_healthy_remaining_probes_up():
    d = next_concurrency(2, RateWindow(remaining=800, limit=1000, throttled=False))
    assert d.concurrency == 3
    assert d.paused is False


def test_midband_holds():
    # between floor (150) and healthy (500): hold
    d = next_concurrency(3, RateWindow(remaining=300, limit=1000, throttled=False))
    assert d.concurrency == 3


def test_unknown_remaining_holds():
    d = next_concurrency(3, RateWindow(remaining=None, limit=None, throttled=False))
    assert d.concurrency == 3


def test_clamps_to_ceiling_and_floor():
    assert next_concurrency(6, RateWindow(900, 1000, False)).concurrency == 6  # ceiling
    assert next_concurrency(1, RateWindow(10, 1000, False)).concurrency == 1   # floor
```

- [ ] **Step 2: Run → fail**

Run: `cd app/backend && ../.venv/bin/pytest tests/madrid_enrich/test_fast_controller.py -q`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

`app/backend/madrid_enrich/fast_mode/__init__.py`:

```python
"""Madrid sweep "Fast mode" — rate-aware concurrency paced to WIPO's published
X-RateLimit budget. See docs/superpowers/specs/2026-06-23-madrid-fast-mode-design.md."""

from .controller import CEILING, FLOOR, START, Decision, RateWindow, next_concurrency

__all__ = ["CEILING", "FLOOR", "START", "Decision", "RateWindow", "next_concurrency"]
```

`app/backend/madrid_enrich/fast_mode/controller.py`:

```python
"""Rate-feedback concurrency controller for the Madrid sweep's "Fast mode".

Pure, no I/O. WIPO publishes its budget (X-RateLimit-Limit/Remaining), so unlike
the domestic AIMD controller we never probe for a ceiling — we pace to the given
one: step concurrency up while Remaining is healthy, down as it nears a floor,
and pause on an explicit 429/throttle. X-RateLimit-Reset is unusable (WIPO
returns a negative value), so we rely on Remaining recovering by observation.
"""

from __future__ import annotations

from dataclasses import dataclass

FLOOR = 1
CEILING = 6
START = 2

FLOOR_FRAC = 0.15  # keep Remaining above 15% of Limit
HEALTHY_FRAC = 0.50  # probe up only when Remaining >= 50% of Limit
FLOOR_ABS = 50  # absolute Remaining floor when Limit is unknown/tiny


@dataclass(frozen=True)
class RateWindow:
    """What WIPO reported over the last window of fetches."""

    remaining: int | None
    limit: int | None
    throttled: bool


@dataclass(frozen=True)
class Decision:
    concurrency: int
    paused: bool  # throttled -> caller sleeps Retry-After, then re-probes


def _remaining_floor(limit: int | None) -> int:
    if not limit:
        return FLOOR_ABS
    return max(FLOOR_ABS, int(FLOOR_FRAC * limit))


def next_concurrency(
    current: int,
    window: RateWindow,
    *,
    ceiling: int = CEILING,
    floor: int = FLOOR,
) -> Decision:
    """Decide the next concurrency from WIPO's last reported rate window.

    Priority: an explicit throttle parks paused (step down). Else, with a known
    Remaining: at/below the rate floor -> ease off; at/above the healthy band ->
    probe up; otherwise hold. Unknown Remaining -> hold. Clamped to [floor, ceiling].
    """
    if window.throttled:
        return Decision(concurrency=max(floor, current - 1), paused=True)
    if window.remaining is None:
        return Decision(concurrency=current, paused=False)
    if window.remaining <= _remaining_floor(window.limit):
        return Decision(concurrency=max(floor, current - 1), paused=False)
    if window.limit and window.remaining >= HEALTHY_FRAC * window.limit:
        return Decision(concurrency=min(ceiling, current + 1), paused=False)
    return Decision(concurrency=current, paused=False)
```

- [ ] **Step 4: Run → pass**

Run: `cd app/backend && ../.venv/bin/pytest tests/madrid_enrich/test_fast_controller.py -q`
Expected: 6 passed.

- [ ] **Step 5: Gates + commit**

```bash
cd app/backend && ../.venv/bin/ruff format madrid_enrich/fast_mode/ tests/madrid_enrich/test_fast_controller.py \
  && ../.venv/bin/ruff check . && ../.venv/bin/mypy api worker
cd ../.. && git add app/backend/madrid_enrich/fast_mode/__init__.py app/backend/madrid_enrich/fast_mode/controller.py app/backend/tests/madrid_enrich/test_fast_controller.py
git commit -m "feat(madrid): pure rate-feedback fast-mode controller"
```

---

## Task 4: Threaded runner + `run_chunk` delegation

**Files:**
- Create: `app/backend/madrid_enrich/fast_mode/runner.py`
- Modify: `app/backend/madrid_enrich/fast_mode/__init__.py`, `app/backend/worker/madrid_sweep.py`
- Test: `app/backend/tests/worker/test_madrid_sweep_mode.py`

**Read `app/backend/domestic_enrich/dead_mode/runner.py` first — `runner.py` adapts it.** Key adaptations: fetch via `madrid_enrich.client.fetch_raw` (catching `WipoThrottledError`); store via `madrid_enrich.enrich_one`; build a `RateWindow` from the window's last-seen `rate_remaining`/`rate_limit` and whether any `WipoThrottledError` fired; call `next_concurrency`; on `Decision.paused` sleep the throttle's `retry_after` (fallback to a fixed cool-down) before the next window; honor live `madrid_sweep_control` (status pause/stop, `cap`) each window; persist `concurrency` to the control row for the UI. Expose `async def run_chunk(session, *, enqueue_next=..., http_session=None) -> dict`.

- [ ] **Step 1: Write the delegation test**

```python
# app/backend/tests/worker/test_madrid_sweep_mode.py
import pytest
from worker import madrid_sweep


@pytest.mark.asyncio
async def test_run_chunk_delegates_to_fast_mode_when_mode_fast(monkeypatch, db_session_factory):
    # mode='fast' on the control row -> run_chunk delegates to fast_mode.run_chunk
    called = {}

    async def _fake_fast(session, *, enqueue_next, http_session=None):
        called["fast"] = True
        return {"status": "running", "did": 0}

    monkeypatch.setattr("madrid_enrich.fast_mode.run_chunk", _fake_fast, raising=False)
    async with db_session_factory() as s:
        await madrid_sweep._set(s, status="running", mode="fast")
        out = await madrid_sweep.run_chunk(s, enqueue_next=lambda: None)
    assert called.get("fast") is True
```

> NOTE: adapt fixture names (`db_session_factory`) to the repo's existing async test fixtures — grep `tests/` for how other `worker/test_*_sweep*.py` obtain a session. Targeted run only.

- [ ] **Step 2: Run → fail**

Run: `cd app/backend && TM_DATABASE_URL*=... ../.venv/bin/pytest tests/worker/test_madrid_sweep_mode.py -q`
Expected: FAIL (no `mode` handling / delegation).

- [ ] **Step 3: Implement runner + branch.**

Add `run_chunk` to `madrid_enrich/fast_mode/runner.py` (adapt the dead-mode runner per the notes above) and re-export it from `madrid_enrich/fast_mode/__init__.py` (`from .runner import run_chunk`). In `worker/madrid_sweep.py` `run_chunk`, after loading `ctl` (which must now select `C.mode`/`C.concurrency` — extend `_ctl`'s select list), add near the top, mirroring `worker/domestic_sweep.py`:

```python
    if ctl["mode"] == "fast":
        from madrid_enrich.fast_mode import run_chunk as run_fast_chunk

        return await run_fast_chunk(session, enqueue_next=enqueue_next, http_session=http_session)
```

Ensure `_ctl` adds `C.mode` and `C.concurrency` to its `select(...)`.

- [ ] **Step 4: Run → pass**

Run: `cd app/backend && TM_DATABASE_URL*=... ../.venv/bin/pytest tests/worker/test_madrid_sweep_mode.py tests/madrid_enrich/test_fast_controller.py -q`
Expected: pass.

- [ ] **Step 5: Gates + commit**

```bash
cd app/backend && ../.venv/bin/ruff format madrid_enrich/fast_mode/ worker/madrid_sweep.py tests/worker/test_madrid_sweep_mode.py \
  && ../.venv/bin/ruff check . && ../.venv/bin/mypy api worker
cd ../.. && git add app/backend/madrid_enrich/fast_mode/runner.py app/backend/madrid_enrich/fast_mode/__init__.py app/backend/worker/madrid_sweep.py app/backend/tests/worker/test_madrid_sweep_mode.py
git commit -m "feat(madrid): fast-mode threaded runner + run_chunk delegation"
```

---

## Task 5: Admin endpoint + `/admin/madrid` UI

**Files:**
- Modify: the Madrid sweep admin route (`grep -rl "madrid-sweep" app/backend/api/routes/`) — accept `mode` + `concurrency` in the tune payload, exactly as the domestic-sweep route does.
- Modify: the `/admin/madrid` ops panel component (`grep -rl "domestic-sweep\|Dead mode" app/frontend` to find the domestic panel to mirror) — add the mode/concurrency control row + a `rate: Remaining/Limit · req/s` readout, mirroring `/admin/domestic`.

- [ ] **Step 1: Backend** — add `mode`/`concurrency` to the madrid-sweep tune request schema + handler (copy the domestic-sweep route's mode handling verbatim, swapping the control model to `MadridSweepControl`). Add a focused route test asserting `POST .../madrid-sweep` with `{"mode":"fast"}` persists `mode='fast'`. Run it (targeted) → pass. Gates (`ruff`/`mypy`). Commit.

- [ ] **Step 2: Frontend** — mirror the domestic ops panel's dead-mode toggle into the Madrid panel: an "Enable fast mode" control that posts `mode`, a concurrency display, and the rate readout fed by the enrichment endpoint. Verify with `cd app/frontend && npx tsc --noEmit && pnpm lint` (NEVER `pnpm build` while `pnpm dev` is live). Browser-check `/admin/madrid`. Commit `feat(madrid): fast-mode toggle on /admin/madrid`.

---

## Deploy + verify (after all tasks)

1. The migration is already applied (Task 2). Rebuild the worker: `docker compose -f app/docker-compose.yml up -d --build worker-madrid` (the Madrid sweep is idle — safe).
2. On `/admin/madrid`, enable fast mode and start the sweep. Confirm: concurrency climbs toward the ceiling while `Remaining` stays high; the per-window rate readout shows `Remaining/Limit`; `madrid_records` count rises faster than normal mode; no `WipoThrottledError` storms (if WIPO 429s, the sweep pauses, not hammers).

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths only.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. Run targeted pytest only — sweep tests reset the live `madrid_sweep_control` singleton.
- Never interrupt a running Madrid sweep to deploy; it is idle now — rebuild `worker-madrid` while idle.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.

## Self-review

- **Spec coverage:** client limit+429 (Task 1 ✓), migration mode/concurrency (Task 2 ✓), pure controller (Task 3 ✓), runner + delegation branch (Task 4 ✓), API + UI (Task 5 ✓), pace-off-Remaining/no-Reset (controller logic ✓), no-auto-revert (controller has no give-up/revert — by design ✓), convergence/pause-on-throttle (controller `paused` + runner sleep ✓). All spec sections mapped.
- **Type consistency:** `RateWindow(remaining,limit,throttled)` and `Decision(concurrency,paused)` used identically in Task 3 + Task 4; `FetchResult.rate_limit`/`rate_remaining` + `WipoThrottledError.retry_after` from Task 1 consumed by Task 4's runner.
- **Placeholder scan:** runner internals are delegated to "adapt dead_mode/runner.py" rather than reproduced — intentional (it's an existing, proven 1:1 template); all novel logic (controller, client) is given in full.
