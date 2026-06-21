# Dead Mode — Control API (PR 4 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Expose `mode` through the domestic-sweep admin API — `start` accepts it (defaulting to `normal`), `config` flips it live, and `SweepControlOut` returns `mode` + `concurrency` so the panel can read dead-mode state.

**Architecture:** Pure additive changes to `api/routes/domestic_sweep.py`. `CadenceBody` gains a validated `mode` field (`Literal["normal","dead"]`); `start` sets it (default `normal`) and resets `concurrency=0`; `config` flips it live (resetting `concurrency=0` when returning to `normal`). The state-machine guards are unchanged.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async, pytest + httpx.

**Spec:** `docs/superpowers/specs/2026-06-21-domestic-dead-mode-design.md` (§Control surface).

## Scope

PR 4 of 5: backend control API only. No frontend (PR 5). No runner/schema changes (PRs 2-3 shipped them). After this PR, an admin can start in dead mode or flip live, and the GET endpoint reports `mode`/`concurrency`.

## Standing constraints

- **NEVER commit the rename trio**; `git add` by explicit path.
- **GateGuard**: state facts on first Edit/Write per file + first Bash; retry.
- Run from `app/backend/` with the venv. CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`.
- **The dev DB hosts the LIVE sweep.** The route tests reset the control singleton (existing `reset_and_stub` fixture) — run ONLY `tests/domestic_enrich/test_sweep_control.py` here, never the full suite. **The controller will restart the live sweep after these tests** (outside this plan).

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/api/routes/domestic_sweep.py` | `SweepControlOut` +`mode`/`concurrency`; `CadenceBody` +`mode`; `start`/`config` handle `mode`. |
| `app/backend/tests/domestic_enrich/test_sweep_control.py` | Extend the reset fixture + add mode tests. |

---

## Task 1: Surface `mode` through the API

**Files:**
- Modify: `app/backend/api/routes/domestic_sweep.py`

- [ ] **Step 1: Import `Literal`**

At the top of `app/backend/api/routes/domestic_sweep.py`, add the `typing` import (after `from __future__ import annotations`):

```python
from typing import Literal
```

- [ ] **Step 2: Add `mode` + `concurrency` to `SweepControlOut`**

In `SweepControlOut`, add these two fields immediately after `failed: int` (before `current_appno`):

```python
    mode: str
    concurrency: int
```

- [ ] **Step 3: Add a validated `mode` to `CadenceBody`**

In `CadenceBody`, add (after `chunk_size`):

```python
    mode: Literal["normal", "dead"] | None = None
```
(Pydantic rejects any other value with a 422 automatically.)

- [ ] **Step 4: Handle `mode` in `start`**

In `start`, immediately after the `row.started_at = _now()` line (before the `if body.cap is not None:` block), add:

```python
    row.mode = body.mode or "normal"
    row.concurrency = 0
```
(A fresh run defaults to `normal` unless the caller asks for `dead`; `concurrency` always resets at start.)

- [ ] **Step 5: Handle the live `mode` flip in `config`**

In `config`, immediately after the `if body.chunk_size is not None:` block (before `row.updated_at = _now()`), add:

```python
    if body.mode is not None:
        row.mode = body.mode
        if body.mode == "normal":
            row.concurrency = 0
```
(Flipping back to `normal` zeroes the displayed concurrency; the runner owns it while `dead`.)

- [ ] **Step 6: Lint + typecheck**

```bash
cd app/backend && source ../.venv/bin/activate
ruff format api/routes/domestic_sweep.py && ruff check . && mypy api worker
```
Expected: ruff clean; mypy `Success`.

- [ ] **Step 7: Commit**

```bash
git add app/backend/api/routes/domestic_sweep.py
git commit -m "$(printf 'feat(dead-mode): expose mode via domestic-sweep API (start + live config flip)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Tests

**Files:**
- Modify: `app/backend/tests/domestic_enrich/test_sweep_control.py`

- [ ] **Step 1: Reset `mode`/`concurrency` in the fixture**

In `test_sweep_control.py`, in the `reset_and_stub` fixture's `.values(...)` call, add two keys (alongside the existing ones, e.g. after `last_error=None,`):

```python
                mode="normal",
                concurrency=0,
```

- [ ] **Step 2: Append the mode tests**

Add these tests to the end of `app/backend/tests/domestic_enrich/test_sweep_control.py`:

```python
@pytest.mark.asyncio
async def test_get_status_includes_mode_and_concurrency(authed_client: AsyncClient):
    r = await authed_client.get("/api/v1/admin/domestic-sweep")
    assert r.status_code == 200
    d = r.json()
    assert d["mode"] == "normal"
    assert d["concurrency"] == 0


@pytest.mark.asyncio
async def test_start_in_dead_mode(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/admin/domestic-sweep/start", json={"mode": "dead"})
    assert r.status_code == 200
    assert r.json()["mode"] == "dead"


@pytest.mark.asyncio
async def test_start_defaults_to_normal(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/admin/domestic-sweep/start", json={})
    assert r.status_code == 200
    assert r.json()["mode"] == "normal"


@pytest.mark.asyncio
async def test_config_flips_mode_live(authed_client: AsyncClient):
    await authed_client.post("/api/v1/admin/domestic-sweep/start", json={})
    r = await authed_client.patch("/api/v1/admin/domestic-sweep/config", json={"mode": "dead"})
    assert r.status_code == 200
    assert r.json()["mode"] == "dead"
    # flip back -> normal, concurrency reset
    r2 = await authed_client.patch("/api/v1/admin/domestic-sweep/config", json={"mode": "normal"})
    assert r2.json()["mode"] == "normal"
    assert r2.json()["concurrency"] == 0


@pytest.mark.asyncio
async def test_invalid_mode_rejected(authed_client: AsyncClient):
    r = await authed_client.post("/api/v1/admin/domestic-sweep/start", json={"mode": "turbo"})
    assert r.status_code == 422
```

- [ ] **Step 3: Run the route tests**

```bash
cd app/backend && source ../.venv/bin/activate
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
python -m pytest tests/domestic_enrich/test_sweep_control.py -v
```
Expected: all pass (existing + 5 new).

- [ ] **Step 4: Final gates**

```bash
cd app/backend && source ../.venv/bin/activate
ruff check . && ruff format --check . && mypy api worker
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic check
```
Expected: ruff clean; mypy `Success`; `No new upgrade operations detected.`

- [ ] **Step 5: Commit**

```bash
git add app/backend/tests/domestic_enrich/test_sweep_control.py
git commit -m "$(printf 'test(dead-mode): mode via start + live config flip + 422 on invalid\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage** (§Control surface):
- `start`/`config` accept `mode` → Steps 4-5. ✅
- Live flip → `config` mode handling. ✅
- `SweepControlOut` gains `mode` + `concurrency` → Step 2. ✅
- Invalid mode guarded → `Literal` → 422 test. ✅
- State-machine 409 guards unchanged → untouched. ✅

**Placeholder scan:** none.

**Type/consistency:** `mode` is `Literal["normal","dead"]` in the body and `str` in the output (the DB CHECK + Literal both enforce the domain); `concurrency` is `int` matching the model column; field names match `DomesticSweepControl` (`mode`, `concurrency`) so `from_attributes` serialization works.
