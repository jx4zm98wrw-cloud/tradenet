# Dead Mode — Package + Schema Implementation Plan (PR 2 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Create the self-contained `domestic_enrich/dead_mode/` package (relocating the already-built AIMD controller into it) and add the `mode`/`concurrency` columns to `domestic_sweep_control` — the home + data for the dead-chunk runner that lands in PR 3. No runtime behavior change yet.

**Architecture:** `dead_mode/` becomes the package that owns all dead-mode logic; PR 1's `domestic_enrich/aimd.py` moves in as `dead_mode/controller.py`. The `domestic_sweep_control` singleton gains `mode` (`'normal'`/`'dead'`, default `'normal'`) and `concurrency` (int, default 0). Nothing reads them yet — the delegation + runner are PR 3.

**Tech Stack:** Python 3.13, SQLAlchemy 2 (`Mapped`/`mapped_column`), Alembic, pytest.

**Spec:** `docs/superpowers/specs/2026-06-21-domestic-dead-mode-design.md` (§"Module boundary", §"Schema").

## Scope

PR 2 of 5: package skeleton + schema only. Do NOT add the runner, the delegation branch, the routes, or the frontend. After this PR, `mode`/`concurrency` exist and default to a no-op (`'normal'`/0), so behavior is unchanged.

## Standing constraints

- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` by explicit path.
- **GateGuard**: state facts on first Edit/Write per file + first Bash; retry.
- Run from `app/backend/` with the venv (`source ../.venv/bin/activate`). CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. **A new model index/constraint MUST be declared in `__table_args__` to satisfy `alembic check`** (the GIN-index drift lesson). The `mode` CHECK constraint must exist in BOTH the model and the migration, same name.
- **The dev DB hosts the live sweep.** Run only the targeted tests below, not the full suite (the sweep-test fixtures reset the `domestic_sweep_control` singleton). The schema test below uses `flush` only (no commit) so it can't disturb the live row.

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/domestic_enrich/dead_mode/__init__.py` (new) | Package public API: `DEAD`/`NORMAL` constants + re-export the controller symbols (and `run_chunk` later). |
| `app/backend/domestic_enrich/dead_mode/controller.py` (moved from `aimd.py`) | The AIMD controller — unchanged content, new home. |
| `app/backend/tests/domestic_enrich/dead_mode/__init__.py` (new) | Test package marker. |
| `app/backend/tests/domestic_enrich/dead_mode/test_controller.py` (moved from `test_aimd.py`) | Controller tests with the updated import path. |
| `app/backend/api/db/models.py` | `mode` + `concurrency` columns + the `mode` CHECK on `DomesticSweepControl`. |
| `app/backend/alembic/versions/20260621_0022_dead_mode_columns.py` (new) | Add the two columns + the CHECK. |
| `app/backend/tests/domestic_enrich/dead_mode/test_schema.py` (new) | Columns exist with correct defaults + a dead/concurrency roundtrip. |

---

## Task 1: Create the `dead_mode/` package (relocate the controller)

**Files:**
- Create dir + `__init__.py`: `app/backend/domestic_enrich/dead_mode/`
- Move: `app/backend/domestic_enrich/aimd.py` → `app/backend/domestic_enrich/dead_mode/controller.py`
- Move: `app/backend/tests/domestic_enrich/test_aimd.py` → `app/backend/tests/domestic_enrich/dead_mode/test_controller.py`

- [ ] **Step 1: Confirm nothing imports `aimd` except its test**

Run: `cd app/backend && grep -rn "domestic_enrich.aimd\|from domestic_enrich import aimd\|import aimd" --include='*.py' . | grep -v __pycache__`
Expected: only `tests/domestic_enrich/test_aimd.py`. (If anything else appears, STOP — the move would break it.)

- [ ] **Step 2: Create the package dirs + git-move the controller and its test**

```bash
cd app/backend
mkdir -p domestic_enrich/dead_mode tests/domestic_enrich/dead_mode
git mv domestic_enrich/aimd.py domestic_enrich/dead_mode/controller.py
git mv tests/domestic_enrich/test_aimd.py tests/domestic_enrich/dead_mode/test_controller.py
: > tests/domestic_enrich/dead_mode/__init__.py
```

- [ ] **Step 3: Update the test's import path**

In `app/backend/tests/domestic_enrich/dead_mode/test_controller.py`, change the import:

```python
from domestic_enrich.dead_mode.controller import (
    CEILING,
    FLOOR,
    START,
    Decision,
    Outcome,
    WindowStats,
    next_concurrency,
    should_give_up,
    stats_from,
)
```
(Only the module path changes — `domestic_enrich.aimd` → `domestic_enrich.dead_mode.controller`. The symbol list is unchanged.)

- [ ] **Step 4: Write the package `__init__.py`**

`app/backend/domestic_enrich/dead_mode/__init__.py`:

```python
"""Domestic sweep "Dead mode" — self-contained adaptive max-throughput package.

The normal sweep (worker.domestic_sweep) delegates to this package via a single
`if mode == 'dead'` branch; nothing here imports back into worker.domestic_sweep
(one-way dependency, no cycle). Public surface: the mode constants, the AIMD
controller, and run_chunk() (added with the runner in PR 3).
"""

from domestic_enrich.dead_mode.controller import (
    Decision,
    Outcome,
    WindowStats,
    next_concurrency,
    should_give_up,
    stats_from,
)

DEAD = "dead"
NORMAL = "normal"

__all__ = [
    "DEAD",
    "NORMAL",
    "Decision",
    "Outcome",
    "WindowStats",
    "next_concurrency",
    "should_give_up",
    "stats_from",
]
```

- [ ] **Step 5: Run the relocated controller tests + import check**

```bash
cd app/backend && source ../.venv/bin/activate
python -m pytest tests/domestic_enrich/dead_mode/test_controller.py -v
python -c "from domestic_enrich.dead_mode import DEAD, NORMAL, next_concurrency; print(DEAD, NORMAL, next_concurrency.__name__)"
```
Expected: 12 tests PASS; the import prints `dead normal next_concurrency`.

- [ ] **Step 6: Lint + commit**

```bash
cd app/backend && source ../.venv/bin/activate
ruff format domestic_enrich/dead_mode/ tests/domestic_enrich/dead_mode/ && ruff check domestic_enrich/dead_mode/ tests/domestic_enrich/dead_mode/
```
Then:
```bash
git add app/backend/domestic_enrich/dead_mode/ app/backend/tests/domestic_enrich/dead_mode/
git commit -m "$(printf 'refactor(dead-mode): relocate AIMD controller into dead_mode/ package\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```
(The `git mv` is recorded as a rename; the old `aimd.py` paths are gone.)

---

## Task 2: `mode` + `concurrency` schema

**Files:**
- Modify: `app/backend/api/db/models.py` (`DomesticSweepControl`)
- Create: `app/backend/alembic/versions/20260621_0022_dead_mode_columns.py`
- Test: `app/backend/tests/domestic_enrich/dead_mode/test_schema.py`

- [ ] **Step 1: Add the columns + CHECK to the model**

In `app/backend/api/db/models.py`, in `class DomesticSweepControl`:

(a) extend `__table_args__` with the mode CHECK:
```python
    __table_args__ = (
        CheckConstraint(
            "status IN ('idle','running','paused','stopping')",
            name="ck_domestic_sweep_status",
        ),
        CheckConstraint(
            "mode IN ('normal','dead')",
            name="ck_domestic_sweep_mode",
        ),
    )
```

(b) add the two columns immediately after the `failed` column:
```python
    mode: Mapped[str] = mapped_column(Text, nullable=False, server_default="normal")
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
```

- [ ] **Step 2: Create the migration**

`app/backend/alembic/versions/20260621_0022_dead_mode_columns.py`:

```python
"""dead_mode columns on domestic_sweep_control (mode, concurrency)

Revision ID: 20260621_0022
Revises: 20260619_0021
Create Date: 2026-06-21
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "20260621_0022"
down_revision: str | None = "20260619_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "domestic_sweep_control",
        sa.Column("mode", sa.Text(), nullable=False, server_default="normal"),
    )
    op.add_column(
        "domestic_sweep_control",
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_check_constraint(
        "ck_domestic_sweep_mode", "domestic_sweep_control", "mode IN ('normal','dead')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_domestic_sweep_mode", "domestic_sweep_control", type_="check")
    op.drop_column("domestic_sweep_control", "concurrency")
    op.drop_column("domestic_sweep_control", "mode")
```

- [ ] **Step 3: Apply + drift check**

```bash
cd app/backend && source ../.venv/bin/activate
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic upgrade head
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic check
```
Expected: `Running upgrade 20260619_0021 -> 20260621_0022`, then `No new upgrade operations detected.` (The existing live singleton row is backfilled `mode='normal'`, `concurrency=0` — harmless, it was effectively normal already.)

- [ ] **Step 4: Write the schema test (flush only — must not disturb the live row)**

`app/backend/tests/domestic_enrich/dead_mode/test_schema.py`:

```python
import pytest
from sqlalchemy import select

from api.db.models import DomesticSweepControl as C


@pytest.mark.asyncio
async def test_dead_mode_columns_exist_with_defaults(db_session):
    # The singleton carries the new columns; existing row backfilled to normal/0.
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert row.mode in ("normal", "dead")
    assert isinstance(row.concurrency, int)


@pytest.mark.asyncio
async def test_can_set_dead_and_concurrency(db_session):
    # flush (NOT commit) so the live dev singleton is never actually mutated.
    row = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    row.mode = "dead"
    row.concurrency = 4
    await db_session.flush()
    again = (await db_session.execute(select(C).where(C.id == 1))).scalar_one()
    assert again.mode == "dead"
    assert again.concurrency == 4
```

- [ ] **Step 5: Run targeted tests + gates**

```bash
cd app/backend && source ../.venv/bin/activate
python -m pytest tests/domestic_enrich/dead_mode/ -v
ruff check . && ruff format --check . && mypy api worker
```
Expected: all pass; ruff clean; mypy `Success`. (Do NOT run the full suite — it resets the live sweep singleton.)

- [ ] **Step 6: Commit**

```bash
git add app/backend/api/db/models.py \
        app/backend/alembic/versions/20260621_0022_dead_mode_columns.py \
        app/backend/tests/domestic_enrich/dead_mode/test_schema.py
git commit -m "$(printf 'feat(dead-mode): mode + concurrency columns on domestic_sweep_control\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage** (§"Module boundary" + §"Schema"):
- `dead_mode/` package created; controller relocated as `controller.py`; `__init__` exposes `DEAD`/`NORMAL` + controller (and later `run_chunk`) → Task 1. ✅
- `mode` (CHECK normal/dead, default normal) + `concurrency` (default 0) columns → Task 2. ✅
- One-way dependency preserved: `__init__` imports only `controller`; nothing imports `worker.domestic_sweep`. ✅
- Deferred (correctly): the runner, the delegation branch, route exposure, frontend — PRs 3-5.

**Placeholder scan:** none — every step has exact code/commands.

**Type/consistency:** the relocated `controller.py` keeps the exact symbol names PR 3 imports (`next_concurrency`, `Outcome`, `WindowStats`, `should_give_up`, `stats_from`, constants); `mode`/`concurrency` column names match the migration and the spec; the `ck_domestic_sweep_mode` CHECK name is identical in model and migration (no `alembic check` drift).
