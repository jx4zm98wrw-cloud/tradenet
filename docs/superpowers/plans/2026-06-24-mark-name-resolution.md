# Resolved Mark Name Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. Full design: `docs/superpowers/specs/2026-06-24-mark-name-resolution-design.md` — read it before each task.

**Goal:** Stop ~172k domestic marks showing the applicant as their name — resolve a denormalized `trademarks.mark_name` (mark_sample → domestic.mark_text → madrid.mark_text → NULL) that every surface reads, with `markDisplay` showing "(figurative mark)" when empty.

**Architecture:** Mirrors `vn_grant_date` — a denormalized column + idempotent backfill; `TrademarkOut` serializes it so all consumers get it; `markDisplay` uses it (no applicant fallback). No per-payload joins.

**Tech Stack:** FastAPI + SQLAlchemy async + Alembic (backend), Next.js 15 + React (frontend).

---

## Reference points (read these)

- `app/backend/scripts/backfill_vn_grant.py` — the exact idempotent-backfill pattern to mirror (resolver maps + recompute-and-compare + `_main`).
- `app/backend/api/db/models.py` — `Trademark` (table `trademarks`), `DomesticRecord.mark_text`, `MadridRecord.mark_text` (`irn`), `mark_category`/`application_number`/`lineage_key`/`mark_sample`.
- `app/backend/api/schemas.py` — `TrademarkOut` (add `mark_name`); confirm it's `model_validate`'d from the ORM `Trademark` so the new attribute serializes automatically.
- `app/frontend/lib/mark-display.ts:88` — `markDisplay(mark, wordmarkOverride?)`; read its return shape (name/initials) before editing.
- `app/frontend/lib/api.ts` — the Trademark/search-result TS type (add `mark_name`).
- Call sites that benefit (no change needed beyond the helper): `components/search/results-grid.tsx:28`, `results-table.tsx:40`, `cmdk.tsx:158`, `marks/[id]/page.tsx:177`.

---

## Task 1: Migration + backfill for `trademarks.mark_name`

**Files:** Modify `app/backend/api/db/models.py`; Create `app/backend/alembic/versions/20260624_0028_trademarks_mark_name.py`, `app/backend/scripts/backfill_mark_name.py`; Test `app/backend/tests/test_backfill_mark_name.py`.

- [ ] **Step 1: Model column.** In `Trademark`, add:

```python
    mark_name: Mapped[str | None] = mapped_column(Text, nullable=True, index=True)
```

(`Text` is already imported in this module.)

- [ ] **Step 2: Migration.** From `app/backend` (venv + `TM_DATABASE_URL*`): `../.venv/bin/alembic revision --autogenerate -m "trademarks mark_name"`. Rename to `20260624_0028_trademarks_mark_name.py`, set `down_revision = "20260624_0027"`, confirm it adds the `mark_name` column + `ix_trademarks_mark_name` (only that). `../.venv/bin/alembic upgrade head && ../.venv/bin/alembic check` → "No new upgrade operations detected."

- [ ] **Step 3: Write the failing backfill test**

```python
# tests/test_backfill_mark_name.py
import pytest
from sqlalchemy import select
from api.db.models import Trademark
from scripts.backfill_mark_name import backfill_mark_name

@pytest.mark.asyncio
async def test_backfill_resolves_mark_name(db_session, seed_marks):
    # seed_marks inserts:
    #  - domestic "4-2024-1" mark_sample="Taseko"                              -> "Taseko"
    #  - domestic "4-2024-2" mark_sample="" + domestic_records.mark_text="TRADAGUI" -> "TRADAGUI"
    #  - madrid   lineage "1500001" mark_sample="" + madrid_records.mark_text="LANDSTORM" -> "LANDSTORM"
    #  - domestic "4-2024-3" mark_sample="" + no domestic_records                  -> None (figurative)
    await seed_marks()
    async with db_session() as s:
        n1 = await backfill_mark_name(s); await s.commit()
        rows = {(t.application_number or t.lineage_key): t.mark_name
                for t in (await s.execute(select(Trademark))).scalars()}
    assert rows["4-2024-1"] == "Taseko"
    assert rows["4-2024-2"] == "TRADAGUI"
    assert rows["1500001"] == "LANDSTORM"
    assert rows["4-2024-3"] is None
    async with db_session() as s:
        assert await backfill_mark_name(s) == 0  # idempotent
```

> Adapt `db_session`/`seed_marks` to the repo's real async-session + seeding fixtures (grep `tests/`; `tests/test_backfill_vn_grant.py` shows the seeding shape).

- [ ] **Step 4: Run → fail** — `cd app/backend && ../.venv/bin/pytest tests/test_backfill_mark_name.py -q` → ImportError.

- [ ] **Step 5: Implement `scripts/backfill_mark_name.py`** (mirror `backfill_vn_grant.py`):

```python
"""Backfill trademarks.mark_name from the trusted sources (idempotent).

Resolution: mark_sample -> domestic_records.mark_text (domestic) | madrid_records.mark_text
(madrid) -> NULL. Re-run after a fresh ingest/enrichment (the ingest worker does not
populate it)."""
from __future__ import annotations
import asyncio, logging, os
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from api.db.models import Trademark, DomesticRecord, MadridRecord

MARK_NAME_VERSION = 1
_DOMESTIC = ("domestic_application", "domestic_registration")
log = logging.getLogger("backfill.mark_name")


def _clean(s: str | None) -> str | None:
    s = (s or "").strip()
    return s or None


async def backfill_mark_name(session: AsyncSession) -> int:
    dom = {a: t for a, t in (await session.execute(
        select(DomesticRecord.application_number, DomesticRecord.mark_text))).all()}
    mad = {i: t for i, t in (await session.execute(
        select(MadridRecord.irn, MadridRecord.mark_text))).all()}
    changed = 0
    marks = (await session.execute(
        select(Trademark.id, Trademark.mark_category, Trademark.application_number,
               Trademark.lineage_key, Trademark.mark_sample, Trademark.mark_name)
    )).all()
    for tid, cat, appno, lineage, sample, current in marks:
        want = _clean(sample)
        if want is None:
            want = _clean(dom.get(appno)) if cat in _DOMESTIC else _clean(mad.get(lineage))
        if want != current:
            await session.execute(update(Trademark).where(Trademark.id == tid).values(mark_name=want))
            changed += 1
    return changed


async def _main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = create_async_engine(os.environ["TM_DATABASE_URL"])
    async with async_sessionmaker(engine, expire_on_commit=False)() as s:
        n = await backfill_mark_name(s); await s.commit()
    await engine.dispose()
    log.info("DONE: mark_name set on %d marks (version %d)", n, MARK_NAME_VERSION)
    print({"updated": n})


if __name__ == "__main__":
    asyncio.run(_main())
```

- [ ] **Step 6: Run → pass.**

- [ ] **Step 7: Run on live DB** (deploy): `cd app/backend && ../.venv/bin/python -m scripts.backfill_mark_name` → `{updated: ~210000}` (most marks get a name; ~6k stay NULL).

- [ ] **Step 8: Gates + commit** — `ruff format` the 4 files, `ruff check . && mypy api worker && alembic check`. `git add app/backend/api/db/models.py app/backend/alembic/versions/20260624_0028_trademarks_mark_name.py app/backend/scripts/backfill_mark_name.py app/backend/tests/test_backfill_mark_name.py && git commit -m "feat(marks): trademarks.mark_name column + idempotent backfill"`.

---

## Task 2: Serialize `mark_name` on `TrademarkOut`

**Files:** Modify `app/backend/api/schemas.py`; Test `app/backend/tests/test_search_mark_name.py`.

- [ ] **Step 1: Write the failing test** — a search result for a figurative domestic mark (mark_sample empty, mark_name backfilled to "TRADAGUI") carries `mark_name`:

```python
# tests/test_search_mark_name.py
import pytest

@pytest.mark.asyncio
async def test_search_result_carries_mark_name(client, seed_figurative_mark):
    await seed_figurative_mark()  # mark_sample="", mark_name="TRADAGUI", applicant="CÔNG TY ... DƯỢC PHẨM"
    r = await client.get("/api/v1/search", params={"q": "TRADAGUI"})
    hit = r.json()["results"][0]
    assert hit["mark_name"] == "TRADAGUI"
```

> Adapt `client`/`seed_figurative_mark` + response shape (`results`) to the route's real contract.

- [ ] **Step 2: Run → fail** (KeyError 'mark_name').

- [ ] **Step 3: Implement** — in `api/schemas.py`, add `mark_name: str | None = None` to `TrademarkOut` (next to `mark_sample`/`mark_text`). Since `TrademarkOut` is `model_validate`'d from the ORM `Trademark`, the new attribute serializes automatically — no route change. (If the search hit uses a narrower model, add `mark_name` there too — read `search.py`'s `SearchResultsOut`/hit model.)

- [ ] **Step 4: Run → pass.**

- [ ] **Step 5: Gates + commit** — `ruff`/`mypy`, targeted pytest. `git add app/backend/api/schemas.py app/backend/tests/test_search_mark_name.py && git commit -m "feat(marks): serialize mark_name on TrademarkOut"`.

---

## Task 3: Frontend — `markDisplay` uses `mark_name` + figurative placeholder

**Files:** Modify `app/frontend/lib/mark-display.ts`, `app/frontend/lib/api.ts`; Test `app/frontend/lib/mark-display.test.ts` (if a test runner exists; else verify via tsc + browser).

- [ ] **Step 1:** In `lib/api.ts`, add `mark_name: string | null;` to the Trademark/search-result type(s) that flow into `markDisplay`.

- [ ] **Step 2:** In `lib/mark-display.ts`, change `markDisplay(mark, wordmarkOverride?)`:
  - Resolve the wordmark as `wordmarkOverride ?? mark.mark_name ?? mark.mark_sample` (mark_sample kept only as a defensive fallback; mark_name already includes it after backfill).
  - When the resolved wordmark is null/empty, set the displayed **name to `"(figurative mark)"`** and DROP the applicant fallback from the NAME path (read the current function — remove the `|| applicant`-style branch in the name path only; the icon-initials may fall back to a neutral glyph like `"◧"`).
  - Keep everything else (case handling, image path) unchanged.

- [ ] **Step 3:** If a frontend unit-test runner exists (check `package.json` for vitest/jest), add `mark-display.test.ts`:

```ts
import { markDisplay } from "./mark-display";
test("uses mark_name", () => {
  expect(markDisplay({ mark_name: "TRADAGUI", mark_sample: null, applicant_name: "CÔNG TY" } as any).name).toBe("TRADAGUI");
});
test("figurative placeholder, not applicant", () => {
  expect(markDisplay({ mark_name: null, mark_sample: null, applicant_name: "CÔNG TY" } as any).name).toBe("(figurative mark)");
});
```
(Adapt the mark shape + the returned property name to the real `markDisplay` signature.) If there's no JS test runner, skip and rely on tsc + the browser check.

- [ ] **Step 4: Verify** — `cd app/frontend && npx tsc --noEmit && pnpm lint` (NEVER `pnpm build` while `pnpm dev` is live). Browser-check `/search?mark_category=domestic_registration`: figurative marks now show their real name (TRADAGUI, Tiniclean), ones with no name show "(figurative mark)" — never the applicant as the name.

- [ ] **Step 5: Commit** — `git add app/frontend/lib/mark-display.ts app/frontend/lib/api.ts app/frontend/lib/mark-display.test.ts && git commit -m "fix(marks): markDisplay uses mark_name, figurative placeholder, no applicant-as-name"`.

---

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest` (targeted pytest — sweep tests reset the live singleton). Migration `0028` chains off `20260624_0027`.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.
- PR `fix(marks): resolved mark_name (denormalized) — fix applicant-as-name on search/cmdk/compare`. Re-run `backfill_mark_name` after future ingests. Note the column in CLAUDE.md's denormalized-columns list.

## Self-review

- **Spec coverage:** column + migration + backfill (Task 1 ✓); TrademarkOut serializes mark_name (Task 2 ✓); markDisplay uses mark_name + figurative placeholder, drops applicant fallback (Task 3 ✓); idempotent + re-run note (Task 1 ✓); display-only / ranking unchanged (no ranking task — correct per spec ✓). All mapped.
- **Type consistency:** `backfill_mark_name(session) -> int` (Task 1) used by deploy + test; `mark_name` field name consistent across model (Task 1), `TrademarkOut`/TS type (Task 2 + 3), and `markDisplay` (Task 3).
- **Placeholders:** backfill + column given in full; TrademarkOut/markDisplay edits cite exact files/lines + flag what to read (search hit model, markDisplay return shape) before editing.
