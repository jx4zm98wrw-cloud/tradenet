# Domestic Enrichment — Frontend Surfacing (Plan C) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Surface the domestic (NOIP) enrichment that Plans A+B produce — attach `domestic_records` to the mark-detail API, render a `DomesticEnrichment` block on the mark page, and add a `/admin/domestic` operations panel + nav tab — mirroring the Madrid surfacing 1:1.

**Architecture:** The mark-detail API gains a parallel `domestic` field (joined `domestic_records.application_number == trademarks.application_number`, alongside the existing Madrid `enrichment`). `lib/api.ts` gets domestic types + admin methods. A new client `DomesticEnrichment` detail component renders on domestic marks; the existing source-agnostic `GoodsServices` component is reused by passing it the domestic per-class goods. A new `/admin/domestic` page copies the Madrid admin panel.

**Tech Stack:** Next.js 15 (App Router, client components), TypeScript, Tailwind 4, pnpm. Backend: FastAPI + SQLAlchemy + pydantic.

**Scope:** This is **Plan C of 3** — the final piece. Plans A (core) + B (sweep) are merged to `main`; this branch (`feat/domestic-frontend`) is off that merged `main`.

## Reference (the Madrid surfacing this mirrors — read first)

- `app/frontend/app/(app)/admin/madrid/page.tsx` — the admin panel to copy.
- `app/frontend/components/detail/madrid-enrichment.tsx` — the detail components to mirror (`MadridEnrichment`, `MadridVnBanner`, `MadridTimeline`, `MadridJurisdictions`).
- `app/frontend/app/(app)/marks/[id]/page.tsx` — where the block is wired in; `GoodsServices` is inline here (lines ~60-119, props `{classes, wipoGoods, raw511}`).
- `app/frontend/lib/api.ts` — `api` client (`json<T>` bearer-auth wrapper), `MarkDetail`/`MadridEnrichment`/`MadridEnrichmentStats`/`MadridSweepControl` types, `getMark`/`adminMadridStats`/`madridSweep*` methods.
- `app/frontend/components/top-nav.tsx` — `TABS` array (Madrid entry ~line 19).
- `app/backend/api/routes/marks.py` — `get_mark` (`GET /api/v1/marks/{id}` → `MarkDetailOut`, joins `MadridRecord` by `session.get(MadridRecord, m.lineage_key)`).
- `app/backend/api/schemas.py` — `MadridEnrichmentOut` (~lines 89-117), `MarkDetailOut`.

## Backend facts (verified)

- The mark-detail join is a PK lookup, NOT a SQL JOIN: `rec = await session.get(MadridRecord, m.lineage_key)`. The domestic analog is `await session.get(DomesticRecord, m.application_number)`.
- `DomesticRecord` (already on `main`) fields: `application_number, mark_text, mark_type, applicant_name, applicant_address, representative, colors, nice_classes[], goods_services{}, vienna_codes[], status_code, filing_date, publication_no, publication_date, grant_date, expiry_date, logo_url, timeline[], raw, source_url, fetched_at, content_hash, parse_version`.
- Backend `/api/v1/admin/domestic-enrichment` (already on `main`) returns `DomesticEnrichmentStats`: `unique_appnos, validated, remaining, pct_complete, granted, by_category`.
- Sweep control endpoints (already on `main`): `/api/v1/admin/domestic-sweep` (+ `/start /pause /resume /stop /config`), returning `SweepControlOut` with `current_appno`/`next_appno`.

## Standing constraints (every task)

- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` by explicit path.
- **GateGuard**: state facts on first Edit/Write per file + first Bash; retry.
- **Backend CI gates** (run from `app/backend` with venv + `TM_DATABASE_URL[_SYNC]`): `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest -q`. **`mypy api worker` type-checks the mark API (in `api`) — keep it type-clean.**
- **Frontend CI gates** (run from `app/frontend`, pnpm v10 / Node 22): `pnpm install --frozen-lockfile && pnpm lint && pnpm build` (`pnpm build` IS the typecheck — there is no separate tsc step).

## File Structure

| File | Responsibility |
|---|---|
| `app/backend/api/schemas.py` | Add `DomesticEnrichmentOut`; add `domestic` field to `MarkDetailOut`. |
| `app/backend/api/routes/marks.py` | Join `DomesticRecord` into `get_mark`. |
| `app/backend/tests/test_marks_enrichment.py` | Assert domestic attach. |
| `app/frontend/lib/api.ts` | `DomesticEnrichment` + stats/control types; `domestic` field on `MarkDetail`; admin methods. |
| `app/frontend/components/detail/domestic-enrichment.tsx` | New detail components. |
| `app/frontend/app/(app)/marks/[id]/page.tsx` | Wire the domestic block + reuse `GoodsServices`. |
| `app/frontend/app/(app)/admin/domestic/page.tsx` | New admin panel (copy Madrid). |
| `app/frontend/components/top-nav.tsx` | Add "Domestic" tab. |

---

## Task 1: Backend — attach `domestic_records` to mark detail

**Files:**
- Modify: `app/backend/api/schemas.py`
- Modify: `app/backend/api/routes/marks.py`
- Test: `app/backend/tests/test_marks_enrichment.py` (add a domestic case)

- [ ] **Step 1: Read the Madrid pieces.** Open `api/schemas.py` (find `MadridEnrichmentOut` + `MarkDetailOut`) and `api/routes/marks.py` (`get_mark` + `_build_detail`). Note the exact import style and the return shape.

- [ ] **Step 2: Add `DomesticEnrichmentOut`** to `app/backend/api/schemas.py`, next to `MadridEnrichmentOut`, with `ConfigDict(from_attributes=True)` (mirror the Madrid model's config). Fields map 1:1 to the `DomesticRecord` ORM columns the UI needs:

```python
class DomesticEnrichmentOut(BaseModel):
    application_number: str
    mark_text: str | None = None
    mark_type: str | None = None
    applicant_name: str | None = None
    applicant_address: str | None = None
    representative: str | None = None
    colors: str | None = None
    nice_classes: list[str] | None = None
    goods_services: dict[str, str] | None = None
    vienna_codes: list[str] | None = None
    status_code: str | None = None
    filing_date: date | None = None
    publication_no: str | None = None
    publication_date: date | None = None
    grant_date: date | None = None
    expiry_date: date | None = None
    logo_url: str | None = None
    timeline: list | None = None
    source_url: str | None = None
    fetched_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
```
(Reuse the existing `BaseModel`, `ConfigDict`, `date`, `datetime` imports already in `schemas.py` — verify they're imported; `MadridEnrichmentOut` uses them.)

- [ ] **Step 3: Add the `domestic` field to `MarkDetailOut`** in the same file, beside `enrichment`:

```python
    domestic: DomesticEnrichmentOut | None = None
```

- [ ] **Step 4: Join `DomesticRecord` in `get_mark`** (`app/backend/api/routes/marks.py`). Import `DomesticRecord` alongside `MadridRecord`, and after the Madrid lookup add the domestic lookup (keyed by `application_number`). Extend `_build_detail` to accept + set `domestic`, mirroring how it sets `enrichment`. Example shape:

```python
domestic = None
if m.application_number:
    drec = await session.get(DomesticRecord, m.application_number)
    if drec is not None:
        domestic = DomesticEnrichmentOut.model_validate(drec)
return _build_detail(m, enrichment, domestic)
```
Update `_build_detail`'s signature to add `domestic: DomesticEnrichmentOut | None = None` and set `domestic=domestic` on the returned `MarkDetailOut`. Keep mypy clean (annotate the new param).

- [ ] **Step 5: Write the test.** In `app/backend/tests/test_marks_enrichment.py` (read it first for the seeding + client fixtures), add a test that seeds a domestic `Trademark` (a `mark_category` in the domestic set, with an `application_number`) and a matching `DomesticRecord`, GETs `/api/v1/marks/{id}`, and asserts `body["domestic"]["mark_text"]` + `body["domestic"]["goods_services"]` are present, and that a non-domestic mark returns `domestic == None`.

- [ ] **Step 6: Run backend gates + commit**

```bash
cd app/backend && source ../.venv/bin/activate
ruff check . && ruff format --check . && mypy api worker
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm python -m pytest tests/test_marks_enrichment.py -q
```
Then:
```bash
git add app/backend/api/schemas.py app/backend/api/routes/marks.py app/backend/tests/test_marks_enrichment.py
git commit -m "$(printf 'feat(domestic): attach domestic_records to mark detail API\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Frontend API client — types + methods

**Files:**
- Modify: `app/frontend/lib/api.ts`

- [ ] **Step 1: Read** `lib/api.ts` — the `MadridEnrichment`, `MadridEnrichmentStats`, `MadridSweepControl`, `SweepCadence`, `MarkDetail` types and the `adminMadridStats`/`madridSweep*` methods; match their style exactly.

- [ ] **Step 2: Add types** (next to the Madrid ones):

```ts
export interface DomesticEnrichment {
  application_number: string;
  mark_text: string | null;
  mark_type: string | null;
  applicant_name: string | null;
  applicant_address: string | null;
  representative: string | null;
  colors: string | null;
  nice_classes: string[] | null;
  goods_services: Record<string, string> | null;
  vienna_codes: string[] | null;
  status_code: string | null;
  filing_date: string | null;
  publication_no: string | null;
  publication_date: string | null;
  grant_date: string | null;
  expiry_date: string | null;
  logo_url: string | null;
  timeline: Array<Record<string, unknown>> | null;
  source_url: string | null;
  fetched_at: string | null;
}

export interface DomesticEnrichmentStats {
  unique_appnos: number;
  validated: number;
  remaining: number;
  pct_complete: number;
  granted: number;
  by_category: Record<string, number>;
}

export interface DomesticSweepControl {
  status: string;
  cap: number | null;
  delay: number;
  jitter: number;
  chunk_size: number;
  processed: number;
  ok: number;
  failed: number;
  current_appno: string | null;
  next_appno: string | null;
  last_error: string | null;
  started_at: string | null;
  updated_at: string;
}
```

- [ ] **Step 3: Add the `domestic` field to `MarkDetail`** (beside `enrichment`):

```ts
  domestic: DomesticEnrichment | null;
```

- [ ] **Step 4: Add the `api` methods** (mirror the Madrid ones; reuse the existing `SweepCadence` type for the cadence body). COPY the exact request-construction shape the Madrid methods use — only swap the URL + return type:

```ts
  adminDomesticStats: () => json<DomesticEnrichmentStats>("/api/v1/admin/domestic-enrichment"),
  domesticSweepStatus: () => json<DomesticSweepControl>("/api/v1/admin/domestic-sweep"),
  domesticSweepStart: (c: SweepCadence) =>
    json<DomesticSweepControl>("/api/v1/admin/domestic-sweep/start", { method: "POST", body: JSON.stringify(c), headers: { "Content-Type": "application/json" } }),
  domesticSweepPause: () =>
    json<DomesticSweepControl>("/api/v1/admin/domestic-sweep/pause", { method: "POST" }),
  domesticSweepResume: () =>
    json<DomesticSweepControl>("/api/v1/admin/domestic-sweep/resume", { method: "POST" }),
  domesticSweepStop: () =>
    json<DomesticSweepControl>("/api/v1/admin/domestic-sweep/stop", { method: "POST" }),
  domesticSweepConfig: (c: SweepCadence) =>
    json<DomesticSweepControl>("/api/v1/admin/domestic-sweep/config", { method: "PATCH", body: JSON.stringify(c), headers: { "Content-Type": "application/json" } }),
```

- [ ] **Step 5: Typecheck + commit**

```bash
cd app/frontend && pnpm build 2>&1 | tail -20   # type errors fail here
```
Then:
```bash
git add app/frontend/lib/api.ts
git commit -m "$(printf 'feat(domestic): frontend api types + admin/sweep client methods\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 3: Admin `/admin/domestic` panel + nav tab

**Files:**
- Create: `app/frontend/app/(app)/admin/domestic/page.tsx`
- Modify: `app/frontend/components/top-nav.tsx`

- [ ] **Step 1: Copy the Madrid admin page** `app/(app)/admin/madrid/page.tsx` → `app/(app)/admin/domestic/page.tsx`. Adapt:
  - `api.adminMadridStats` → `api.adminDomesticStats`; `madridSweep*` → `domesticSweep*`.
  - Types `MadridEnrichmentStats`/`MadridSweepControl` → `DomesticEnrichmentStats`/`DomesticSweepControl`.
  - Stat cards: `unique_irns`→`unique_appnos`; `VN granted`→`Granted` (`stats.granted`); `by_category["madrid_registration"|"madrid_renewal"]` → `by_category["domestic_registration"|"domestic_application"]` (labels "Registrations"/"Applications"); progress denominator `unique_appnos`.
  - Sweep control card: `current_irn`/`next_irn` → `current_appno`/`next_appno`; headings "Madrid" → "Domestic".
  - Keep the admin-check redirect, the polling, and the component structure identical.

- [ ] **Step 2: Add the nav tab** in `app/frontend/components/top-nav.tsx`, immediately after the Madrid entry in `TABS`:

```tsx
    { href: "/admin/domestic", label: "Domestic", match: (p: string) => p.startsWith("/admin/domestic") },
```

- [ ] **Step 3: Typecheck/lint + commit**

```bash
cd app/frontend && pnpm lint && pnpm build 2>&1 | tail -20
```
Then:
```bash
git add app/frontend/app/\(app\)/admin/domestic/page.tsx app/frontend/components/top-nav.tsx
git commit -m "$(printf 'feat(domestic): /admin/domestic operations panel + nav tab\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 4: `DomesticEnrichment` detail block on the mark page

**Files:**
- Create: `app/frontend/components/detail/domestic-enrichment.tsx`
- Modify: `app/frontend/app/(app)/marks/[id]/page.tsx`

- [ ] **Step 1: Create the detail component** `app/frontend/components/detail/domestic-enrichment.tsx`, modeled on `components/detail/madrid-enrichment.tsx`'s `MadridEnrichment` card (read it for the card/label styling + the `Card` import + the date/label helpers). Export a `DomesticEnrichment` component taking `{ e: DomesticEnrichmentData }` and rendering a NOIP record card: applicant name + address, representative, colours, mark type, status (`status_code`), filing/publication/grant/expiry dates, Nice classes, Vienna codes, and a `source_url` link. Also export a small `DomesticTimeline` for `e.timeline` if non-empty (event/date/status rows), mirroring `MadridTimeline`'s presentation. Use the same `formatDate`/label helpers the Madrid component uses (import from wherever it does).

> Presentational only. Match the Madrid component's Tailwind classes + `Card` usage for visual consistency. Import the `DomesticEnrichment` *type* from `@/lib/api` under an alias (e.g. `DomesticEnrichment as DomesticEnrichmentData`) so it doesn't clash with the component name.

- [ ] **Step 2: Wire it into the mark page** `app/(app)/marks/[id]/page.tsx`:
  - Import `{ DomesticEnrichment, DomesticTimeline }` from `@/components/detail/domestic-enrichment`.
  - Render the domestic blocks gated on `detail.domestic` (mutually exclusive with Madrid `detail.enrichment` — a mark is one or the other). Place them analogously to the Madrid blocks: the record card in the main column, the timeline where the Madrid timeline sits.
  - **Reuse `GoodsServices`**: it already accepts `wipoGoods: Record<string,string> | null`. Pass `wipoGoods={detail.enrichment?.goods_services ?? detail.domestic?.goods_services ?? null}` so domestic per-class goods render through the existing collapse (PREVIEW=5). Keep `raw511` as-is.
  - Mark-name fallback: extend the existing `markDisplay(m, detail.enrichment?.mark_text)` to also fall back to the domestic mark text: `markDisplay(m, detail.enrichment?.mark_text ?? detail.domestic?.mark_text)`.

- [ ] **Step 3: Typecheck/lint + commit**

```bash
cd app/frontend && pnpm lint && pnpm build 2>&1 | tail -20
```
Then:
```bash
git add app/frontend/components/detail/domestic-enrichment.tsx app/frontend/app/\(app\)/marks/\[id\]/page.tsx
git commit -m "$(printf 'feat(domestic): DomesticEnrichment detail block on the mark page\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 5: All gates green + docs sync

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Backend gates** (the mark-API change):

```bash
cd app/backend && source ../.venv/bin/activate
ruff check . && ruff format --check . && mypy api worker
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm alembic check
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm python -m pytest -q
```
Expected: all clean / pass.

- [ ] **Step 2: Frontend gates:**

```bash
cd app/frontend && pnpm install --frozen-lockfile && pnpm lint && pnpm build
```
Expected: lint clean, build succeeds (no type errors).

- [ ] **Step 3: Docs sync.** In `CLAUDE.md`, extend the `domestic_enrich/` description to note the frontend surfacing is now complete: a `/admin/domestic` operations panel (coverage + sweep control), a `DomesticEnrichment` block on the mark detail page (NOIP-authoritative applicant/goods/Vienna/status/timeline), and the mark-API `domestic` field joined from `domestic_records`. Mirror the Madrid wording. The domestic enrichment epic (Plans A+B+C) is then complete.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "$(printf 'docs(domestic): record frontend surfacing (admin panel + detail block)\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage** (§Detail page, §Control API + admin panel):
- Mark-API `domestic` join → Task 1. ✅
- Frontend types + admin/sweep client methods → Task 2. ✅
- `/admin/domestic` panel + nav → Task 3. ✅
- `DomesticEnrichment` detail block + goods reuse → Task 4. ✅
- NOIP-authoritative goods via the shared `GoodsServices` (`wipoGoods` arg) → Task 4. ✅

**Type/name consistency:** backend `DomesticEnrichmentOut` (Task 1) field names == frontend `DomesticEnrichment` (Task 2) field names == ORM `DomesticRecord` columns. `MarkDetail.domestic` (frontend) == `MarkDetailOut.domestic` (backend). Admin methods (`adminDomesticStats`, `domesticSweep*`) match the backend routes already on `main`.

**CI gotchas:** `mypy api worker` covers the mark-API change (Task 1); `pnpm build` is the only frontend typecheck (Tasks 2-4 each run it). The component name `DomesticEnrichment` vs the type `DomesticEnrichment` must be disambiguated (import the type under an alias) to avoid a TS clash.

**Mutual exclusivity:** a mark is Madrid OR domestic, so `detail.enrichment` and `detail.domestic` won't both be set; the blocks are gated independently and won't collide.
