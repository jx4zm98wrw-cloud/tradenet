# Gazettes Tab Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. Full design detail lives in the spec: `docs/superpowers/specs/2026-06-22-gazettes-tab-redesign-design.md` — read it before each PR.

**Goal:** Replace the flat, 50-row-capped `/admin/gazettes` table with an analytics overview dashboard + a lazy-loaded group-by-year list, scaling to ~430 gazettes and splitting Domestic/Madrid by `mark_category`.

**Architecture:** Three independently-shippable PRs: (1) a read-only backend aggregation endpoint + list filters, (2) the frontend overview dashboard, (3) the frontend group-by-year list. All Domestic/Madrid splits key off `trademarks.mark_category` (4 values), never `record_type`.

**Tech Stack:** FastAPI + SQLAlchemy async (backend); Next.js 15 + React + a charting lib (Chart.js or recharts — pick one, add as dep) (frontend).

---

## Classification (used by every PR)

`trademarks.mark_category` ∈ {`domestic_application`, `domestic_registration`, `madrid_registration`, `madrid_renewal`}.
- Domestic = `domestic_application` + `domestic_registration`. Madrid = `madrid_registration` + `madrid_renewal`.
- Four **streams** are kept distinct in charts. **Never** use `record_type` (it mislabels 111-only `madrid_registration` as `B_domestic`).

## File structure

| File | PR | Responsibility |
|---|---|---|
| `app/backend/api/routes/gazettes.py` | 1 | `GET /overview` aggregation; extend list with `year`/`gazette_type`/`status` + `?summary=years`. |
| `app/backend/api/schemas/*` (gazette out) | 1 | `GazetteOverviewOut`, year-summary row. |
| `app/backend/tests/...test_gazettes_overview.py` | 1 | Aggregation + filter tests. |
| `app/frontend/lib/api.ts` | 2,3 | `gazettesOverview()`, `gazetteYears()`, `listGazettes({year,type,status})`. |
| `app/frontend/components/admin/gazettes-dashboard.tsx` | 2 | Metric cards + 4-stream chart + split + enrichment + Madrid origin + applicants/representatives (D/M toggles). |
| `app/frontend/components/admin/gazettes-by-year.tsx` | 3 | Collapsible year accordion (lazy per-year fetch) + filter bar. |
| `app/frontend/app/(app)/admin/gazettes/page.tsx` | 2,3 | Compose upload + dashboard + by-year. |

---

## Task 1 (PR 1): Backend — overview endpoint + list filters

**Files:** Modify `api/routes/gazettes.py`; add `GazetteOverviewOut` schema; create `tests/.../test_gazettes_overview.py`.

**Endpoint `GET /api/v1/gazettes/overview`** returns (Pydantic `GazetteOverviewOut`):
- `per_year`: list of `{year, applications, domestic_registrations, madrid_registrations, madrid_renewals}` — counts of `trademarks` joined to `gazettes` on `gazette_id`, grouped by `gazettes.issue_year` + `trademarks.mark_category`.
- `totals`: `{applications, domestic_registrations, madrid_registrations, madrid_renewals, total}`.
- `status_breakdown`: `{completed, processing, failed, uploaded}` (count gazettes by status) + `flagged` (count `needs_review`).
- `coverage`: `{present, expected, missing}` — distinct `(issue_year, issue_number)` present vs `years_span * 24` (or per-year expected 24); list `missing` as `[{year, issue_number, gazette_type}]` (top N).
- `madrid_origin`: top-8 `{country, n}` from `madrid_records.holder_country` (non-null), desc.
- `top_applicants`: `{domestic: [{name,n}], madrid: [{name,n}]}` — domestic from `trademarks.applicant_name` over domestic `mark_category`; madrid from `madrid_records.holder_name`. Top-6 each.
- `top_representatives`: `{domestic: [{name,n}], madrid: [{name,n}]}` — domestic from `trademarks.ip_agency_raw_740` over domestic rows with INTERIM normalization (`_normalize_rep`: casefold, collapse whitespace, strip leading `công ty (luật) tnhh|cổ phần` prefix); madrid from `madrid_records.representative` trimmed at first digit-run/address token. Top-6 each. (Full canonicalization is `task_057fcd61`; mark these "approximate" — leave a `# TODO(task_057fcd61)` and an `approximate: true` flag in the payload.)

**List filters:** extend `GET /api/v1/gazettes` (`list_gazettes`) with optional `year: int | None`, `gazette_type: str | None` (A/B), `status: str | None`, and a `summary: Literal["years"] | None` mode that, when `"years"`, returns `[{year, issue_count, marks, flagged}]` grouped by year (for the accordion headers) instead of the row list.

- [ ] **Step 1: tests first** — `test_gazettes_overview.py`: seed a few gazettes + trademarks across categories/years (reuse existing fixtures), assert: per-year stream counts match a hand-computed group-by; totals sum; `record_type` is NOT referenced (counts use `mark_category`); list `?year=2026&gazette_type=B` filters correctly; `?summary=years` returns per-year counts. Run from `app/backend` with the venv + `TM_DATABASE_URL*` env (targeted — never the full suite; sweep tests reset the live singleton).
- [ ] **Step 2:** run → fail. **Step 3:** implement endpoint + schema + filters. **Step 4:** run → pass.
- [ ] **Step 5: gates** — `ruff check . && ruff format --check . && mypy api worker && alembic check`.
- [ ] **Step 6: commit + PR** — `git add` the route/schema/test by explicit path (NEVER the rename trio). PR title `feat(gazettes): overview aggregation endpoint + list filters`.

## Task 2 (PR 2): Frontend — overview dashboard

**Files:** add lib/api.ts methods + types; create `components/admin/gazettes-dashboard.tsx`; wire into `page.tsx` above the existing table. Add a charting lib (Chart.js via `pnpm add chart.js` + a thin React wrapper, or recharts).

- Metric cards (Total · Domestic · Madrid reg · Madrid renewal · Coverage), 4-stream stacked marks-per-year chart, stream split bar, enrichment (Madrid WIPO % + Domestic NOIP %), Madrid origin ranked bars, top applicants + top representatives panels each with a Domestic|Madrid toggle (client-side switch over the `/overview` payload).
- Colors: Applications `#378ADD`, Domestic regs `#7F77DD`, Madrid reg `#1D9E75`, Madrid renewal `#D85A30`.
- Verify: `npx tsc --noEmit && pnpm lint` (NEVER `pnpm build` while dev is live). Browser-check on `/admin/gazettes`.
- Commit + PR `feat(gazettes): overview dashboard`.

## Task 3 (PR 3): Frontend — group-by-year list

**Files:** create `components/admin/gazettes-by-year.tsx`; replace the flat table render in `page.tsx`; add `gazetteYears()` + filtered `listGazettes()` calls.

- Accordion of years from `?summary=years` (newest open); on expand, lazy-fetch that year's issues via `listGazettes({year})`. Each year header: issue count · marks · flagged. Issue rows: `T<n> · type pill · status · marks · Browse →`; B-issue rows show domestic/Madrid sub-counts (from per-gazette `mark_category` grouping — extend the list row payload with `{domestic, madrid}` counts). Filter bar: search, A/B toggle, status (incl. flagged-only).
- Verify: `npx tsc --noEmit && pnpm lint`; browser-check. Commit + PR `feat(gazettes): group-by-year list`.

---

## Standing constraints

- `mark_category` is the classifier; `record_type` forbidden for the split.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest` (targeted tests only — sweep tests reset the live `domestic_sweep_control` singleton).
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.
- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Representative metric is interim until `task_057fcd61` (canonicalization).

## Self-review

- Spec coverage: overview (streams/coverage/enrichment/origin/applicants/reps) → Task 1+2; group-by-year + filters + lazy load → Task 1 (filters/summary) + Task 3; upload unchanged. ✅
- `mark_category` used throughout; `record_type` excluded. ✅
- Types consistent: `GazetteOverviewOut` shape defined in Task 1 is consumed verbatim by Task 2. ✅
