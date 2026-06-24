# Search Grant-Status Filter — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Full design: `docs/superpowers/specs/2026-06-24-search-grant-status-design.md` — read it before each task.

**Goal:** Make the Search "Granted" filter mean registration status across domestic + Madrid (fix its Madrid-only under-count), rename "Granted in VN" → "Granted", and remove the redundant "Protected in VN" facet.

**Architecture:** Denormalized `trademarks.vn_grant_date` (nullable date), resolved from the trusted source via an idempotent backfill (mirrors `backfill_entity_clean.py`), so search faceting is a single indexed predicate — no per-query join. Search filter + facet read the column; the frontend renames one facet and drops another.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), Next.js 15 + React (frontend).

---

## Reference points (read these)

- `app/backend/api/db/models.py` — `Trademark` (`:140`, table `trademarks`), `MadridRecord` (`:306`; has `vn_status` `:339` + `vn_grant_date` `:340`), `DomesticRecord` (`:363`; has `grant_date`).
- `app/backend/scripts/backfill_entity_clean.py` — the idempotent backfill pattern (recompute-and-compare + version guard) to mirror.
- `app/backend/api/routes/_filters.py` — builds the search `where` list (`vn_status`, `grant_date_from/to` params already declared `:8–10`).
- `app/backend/api/routes/search.py` — the search route + facet counts (`vn_status` param `:174`, `grant_date_from/to` `:175–176`).
- `app/frontend/components/search/filter-rail.tsx` — the facet sidebar (renders "Granted in VN" + the designated-jurisdiction "Protected in VN" facets).
- `app/frontend/app/(app)/search/page.tsx` — filter state + chips; `designated_country === "VN"` ⇒ "Protected in VN" (`:434`, `:502`); `vn_status` chip (`:421–425`).

---

## Task 1: Migration + backfill for `trademarks.vn_grant_date`

**Files:** Modify `app/backend/api/db/models.py` (`Trademark`); Create `app/backend/alembic/versions/20260624_0027_trademarks_vn_grant_date.py`, `app/backend/scripts/backfill_vn_grant.py`; Test `app/backend/tests/test_backfill_vn_grant.py`.

- [ ] **Step 1: Model column.** In `Trademark` (`models.py`), add alongside the other mapped columns:

```python
    vn_grant_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
```

(`date` + `Date` are already imported in this module.)

- [ ] **Step 2: Migration.** From `app/backend` with the venv + `TM_DATABASE_URL*` env:
```
../.venv/bin/alembic revision --autogenerate -m "trademarks vn_grant_date"
```
Rename the generated file to `20260624_0027_trademarks_vn_grant_date.py`, set `down_revision = "20260623_0026"`, and confirm it adds the `vn_grant_date` column + the `ix_trademarks_vn_grant_date` index (and only that). Apply: `../.venv/bin/alembic upgrade head && ../.venv/bin/alembic check` → "No new upgrade operations detected."

- [ ] **Step 3: Write the failing backfill test**

```python
# tests/test_backfill_vn_grant.py
import pytest
from datetime import date
from sqlalchemy import select
from api.db.models import Trademark
from scripts.backfill_vn_grant import backfill_vn_grant

@pytest.mark.asyncio
async def test_backfill_resolves_grant_date(db_session, seed_marks):
    # seed_marks inserts:
    #  - domestic mark appno "4-2024-00001" + domestic_records.grant_date=2024-12-09
    #  - madrid mark lineage_key "1500001" + madrid_records.vn_status="granted", vn_grant_date=2023-01-02
    #  - domestic mark appno "4-2024-00002" with NO domestic_records row (ungranted)
    await seed_marks()
    async with db_session() as s:
        n1 = await backfill_vn_grant(s); await s.commit()
        rows = {t.application_number or t.lineage_key: t.vn_grant_date
                for t in (await s.execute(select(Trademark))).scalars()}
    assert rows["4-2024-00001"] == date(2024, 12, 9)
    assert rows["1500001"] == date(2023, 1, 2)
    assert rows["4-2024-00002"] is None
    async with db_session() as s:
        n2 = await backfill_vn_grant(s); await s.commit()  # idempotent
    assert n2 == 0
```

> Adapt `db_session` / `seed_marks` to the repo's real async-session + seeding fixtures (grep `tests/` for how trademarks/domestic_records/madrid_records are inserted).

- [ ] **Step 4: Run → fail** — `../.venv/bin/pytest tests/test_backfill_vn_grant.py -q` → ImportError.

- [ ] **Step 5: Implement `scripts/backfill_vn_grant.py`** (mirror `backfill_entity_clean.py`'s structure). Core resolver:

```python
"""Backfill trademarks.vn_grant_date from the trusted source (idempotent).

Domestic marks ← domestic_records.grant_date (by application_number).
Madrid marks   ← madrid_records.vn_grant_date when vn_status='granted' (by lineage_key=irn).
Re-run after a fresh ingest/enrichment (the ingest worker does not populate it)."""
from __future__ import annotations
import asyncio, logging, os
from datetime import date
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from api.db.models import Trademark, DomesticRecord, MadridRecord

VN_GRANT_VERSION = 1
_DOMESTIC = ("domestic_application", "domestic_registration")
log = logging.getLogger("backfill.vn_grant")

async def _resolve(session: AsyncSession) -> tuple[dict[str, date], dict[str, date]]:
    dom = dict((await session.execute(
        select(DomesticRecord.application_number, DomesticRecord.grant_date)
        .where(DomesticRecord.grant_date.is_not(None))
    )).all())
    mad = dict((await session.execute(
        select(MadridRecord.irn, MadridRecord.vn_grant_date)
        .where(MadridRecord.vn_status == "granted")
        .where(MadridRecord.vn_grant_date.is_not(None))
    )).all())
    return dom, mad

async def backfill_vn_grant(session: AsyncSession) -> int:
    dom, mad = await _resolve(session)
    changed = 0
    marks = (await session.execute(
        select(Trademark.id, Trademark.mark_category, Trademark.application_number,
               Trademark.lineage_key, Trademark.vn_grant_date)
    )).all()
    for tid, cat, appno, lineage, current in marks:
        want = dom.get(appno) if cat in _DOMESTIC else mad.get(lineage)
        if want != current:
            await session.execute(update(Trademark).where(Trademark.id == tid).values(vn_grant_date=want))
            changed += 1
    return changed

async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        n = await backfill_vn_grant(s); await s.commit()
    await engine.dispose()
    log.info("DONE: vn_grant_date set on %d marks (version %d)", n, VN_GRANT_VERSION)
    print({"updated": n})

if __name__ == "__main__":
    asyncio.run(_main())
```

> Confirm `MadridRecord` exposes `irn` + `vn_grant_date` + `vn_status` (it does per models.py); if the Madrid grant field is named differently, adjust to the real attribute and NOTE it.

- [ ] **Step 6: Run → pass** — `../.venv/bin/pytest tests/test_backfill_vn_grant.py -q` → pass.

- [ ] **Step 7: Run the backfill on the live DB** (deploy step): from `app/backend` with env, `../.venv/bin/python -m scripts.backfill_vn_grant` → prints `{updated: ~119630}`.

- [ ] **Step 8: Gates + commit**

```bash
cd app/backend && ../.venv/bin/ruff format api/db/models.py alembic/versions/20260624_0027_trademarks_vn_grant_date.py scripts/backfill_vn_grant.py tests/test_backfill_vn_grant.py \
  && ../.venv/bin/ruff check . && ../.venv/bin/mypy api worker && ../.venv/bin/alembic check
cd ../.. && git add app/backend/api/db/models.py app/backend/alembic/versions/20260624_0027_trademarks_vn_grant_date.py app/backend/scripts/backfill_vn_grant.py app/backend/tests/test_backfill_vn_grant.py
git commit -m "feat(search): trademarks.vn_grant_date column + idempotent backfill"
```

---

## Task 2: Backend search — Granted filter on `vn_grant_date`; drop Protected-in-VN

**Files:** Modify `app/backend/api/routes/_filters.py`, `app/backend/api/routes/search.py`; Test `app/backend/tests/test_search_granted.py`.

- [ ] **Step 1: Write the failing test** — seed two domestic marks (one with `vn_grant_date`, one without), assert `granted=true` returns only the granted one and the facet count is 1:

```python
# tests/test_search_granted.py
import pytest

@pytest.mark.asyncio
async def test_granted_filter_and_facet(client, seed_marks):
    # seed: "4-2024-1" vn_grant_date=2024-12-09 ; "4-2024-2" vn_grant_date=None
    await seed_marks()
    r = await client.get("/api/v1/search", params={"granted": "true"})
    appnos = {h["application_number"] for h in r.json()["results"]}
    assert appnos == {"4-2024-1"}
    assert r.json()["facets"]["granted"] == 1   # match the real facet payload shape
```

> Adapt `client`/`seed_marks` + the response keys (`results`/`facets`/`granted`) to the route's actual shape — read `search.py` for the response model + facet field names first.

- [ ] **Step 2: Run → fail.**

- [ ] **Step 3: Implement.**
  - In `_filters.py`, where the `where` list is built, add: when the granted flag is set, `where.append(Trademark.vn_grant_date.is_not(None))`; wire `grant_date_from`/`grant_date_to` to `Trademark.vn_grant_date >= / <=`. Replace any old `vn_status`-via-`MadridRecord` granted handling with this column predicate. Use a clean `granted: bool | None` param (the design's preference); keep `vn_status="granted"` as an alias only if the route already depends on it.
  - In `search.py`, the facet aggregation: compute the **"granted"** facet as `count where Trademark.vn_grant_date IS NOT NULL` over the current filter set (replacing the Madrid-only number).
  - **Remove** the designated-jurisdiction / `protected_in_vn` filter param + facet (the `designated_country == "VN"` "Protected in VN" path) from `_filters.py` + `search.py`. Read first: if `designated_country` also filters non-VN Madrid designations, keep that and remove only the VN-protected facet/label; if it is VN-only here, drop the param entirely.

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Gates + commit** (`ruff` + `mypy`, targeted pytest). `git add` the two route files + test. `git commit -m "feat(search): Granted filter on vn_grant_date; remove redundant Protected-in-VN facet"`.

---

## Task 3: Frontend — rename "Granted in VN" → "Granted"; remove "Protected in VN"

**Files:** Modify `app/frontend/components/search/filter-rail.tsx`, `app/frontend/app/(app)/search/page.tsx`, `app/frontend/lib/api.ts` (types/params if needed).

- [ ] **Step 1:** In `filter-rail.tsx`, rename the facet label **"Granted in VN" → "Granted"** and ensure it toggles the `granted` param matching Task 2. Its count comes from the `granted` facet in the search payload.
- [ ] **Step 2:** Remove the **"DESIGNATED JURISDICTION → Protected in VN"** facet block from `filter-rail.tsx`. In `page.tsx`, remove the `designated_country === "VN"` → "Protected in VN" chip (`:434`, `:502`) and any `designated_country` wiring that only served the VN-protected facet (leave non-VN designation handling if it exists).
- [ ] **Step 3:** Update `lib/api.ts` search params/types to match Task 2 (`granted`; drop the VN-protected param).
- [ ] **Step 4: Verify** — `cd app/frontend && npx tsc --noEmit && pnpm lint` (NEVER `pnpm build` while `pnpm dev` is live). Browser-check `/search`: "Granted" shows ~119,630 and filters correctly; no "Protected in VN" facet.
- [ ] **Step 5: Commit** — `git add` the changed frontend files; `git commit -m "feat(search): rename Granted facet + drop Protected-in-VN"`.

---

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest` (targeted pytest — sweep tests reset the live singleton). Migration `0027` chains off `20260623_0026`.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.
- PR `feat(search): grant-status filter (fix+rename Granted, drop Protected-in-VN)`. Re-run `backfill_vn_grant` after future ingests.

## Self-review

- **Spec coverage:** denormalized `vn_grant_date` + migration + backfill (Task 1 ✓); Granted filter/facet on the column (Task 2 ✓); remove Protected-in-VN (Task 2 + 3 ✓); rename frontend facet (Task 3 ✓); idempotent backfill + re-run note (Task 1 ✓). All mapped.
- **Type consistency:** `backfill_vn_grant(session) -> int` (Task 1) used by deploy step + test; the `granted` param/facet name is consistent across Task 2 (backend) and Task 3 (frontend).
- **Placeholders:** backfill resolver + column given in full; route/frontend edits cite exact lines to modify; the route's response/param shapes are flagged to read before editing.
