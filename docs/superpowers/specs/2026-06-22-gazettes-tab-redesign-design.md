# Gazettes Tab Redesign — Overview Dashboard + Group-by-Year (Design)

**Status:** Approved for planning · 2026-06-22

**Goal:** Rework `/admin/gazettes` to scale to ~430+ gazettes (2008–2026, ≥24/year) and add an analytics overview — with Domestic and Madrid surfaced as distinct streams.

## Problem

The current tab is a flat table sorted by upload date, fed by `listGazettes()` which calls `/api/v1/gazettes` with **no pagination params** → it gets the API default `limit=50`. So only the 50 most-recently-uploaded gazettes are visible; everything older (most of 2008–early-2025) is **unreachable in the UI**. There is also no analytics, and no Domestic/Madrid distinction.

## Classification — the heart of the analytics

Records are classified by WIPO INID markers in the source PDF. The **single source of truth is the stored `mark_category` generated column** (correct-by-construction). **Do NOT use `record_type`** — its `B_domestic` value silently lumps the 111-only Madrid registrations in with true domestic registrations (verified: 3,869 `madrid_registration` rows are mislabeled `B_domestic`).

| `mark_category` | INID rule | Count (2026-06-22) | Stream |
|---|---|---|---|
| `domestic_application` | A-file — has `(210)` | 28,985 | **Domestic** |
| `domestic_registration` | B-file — has `(111)` **and** `(210)` | 31,601 | **Domestic** |
| `madrid_registration` | B-file — `(111)` only, **no** `(210)` | 3,869 | **Madrid** |
| `madrid_renewal` | B-file — has `(116)` | 2,866 | **Madrid** |

- **Domestic** = `domestic_application` + `domestic_registration`.
- **Madrid** = `madrid_registration` + `madrid_renewal`.
- A single B-file gazette PDF contains a mix of `domestic_registration`, `madrid_registration`, and `madrid_renewal` rows; counts per gazette are derived by grouping its trademarks on `mark_category`.

## UI architecture

The tab stacks three parts (top to bottom):

1. **Upload dropzone** — unchanged (existing).
2. **Overview dashboard** — analytics, derived live (below).
3. **Group-by-year list** — collapsible year sections replacing the flat table.

### 2. Overview dashboard

All values from aggregation queries over `gazettes` + `trademarks.mark_category` (no new data):

- **Metric cards (4):** Total marks · Domestic (apps + regs) · Madrid (reg + renewal, with enrichment %) · Coverage % (issues present vs the expected ~24/year, with a missing-count).
- **Marks ingested per year** — stacked bar, one bar per year (2008→2026), three series: **Applications · Domestic registrations · Madrid registrations** (Madrid = reg + renewal). Colors: Applications blue (`#378ADD`), Domestic regs purple (`#7F77DD`), Madrid teal (`#1D9E75`). (Chart.js via the CSP-allowed cdnjs.)
- **Stream split** — three-way share bar (Applications / Domestic regs / Madrid).
- **Enrichment panel** — Madrid WIPO-validated % (from `madrid_records` vs Madrid IRNs) and Domestic NOIP-validated % (from `domestic_records` vs domestic appnos). Reuses the same coverage math as `/admin/madrid` and `/admin/domestic`.

### 3. Group-by-year list

- **Collapsible year sections**, newest first; the latest year open by default, older collapsed.
- Each **year header** shows a summary: issue count · total marks · flagged count · status hint.
- **Lazy loading:** the page loads a lightweight per-year summary first; a year's ~24 issues are fetched only when that year is expanded. This is what makes all 18 years reachable without ever pulling 430 rows at once.
- Within an expanded year, one row per gazette: `T<n> · <type pill> · <status> · marks · Browse →`. B-issue rows additionally show their domestic / Madrid mark counts (from `mark_category` grouping).
- **Filter bar:** search (issue, e.g. "T6 2024"), type segmented (All / A-applications / B-registrations), status dropdown (incl. "Flagged only").

## Backend

Two additions to `api/routes/gazettes.py` (read-only, all `GROUP BY`):

1. **`GET /api/v1/gazettes/overview`** → dashboard payload:
   - per-year × stream mark counts (join `trademarks` on `gazette_id`, group by `gazettes.issue_year`, `trademarks.mark_category`),
   - totals per stream, status breakdown, coverage (distinct `(year, issue_number)` present vs expected),
   - Madrid + domestic enrichment % (count `madrid_records`/`domestic_records` against their universes).
2. **Extend `GET /api/v1/gazettes`** (list) with optional `year`, `gazette_type`, `status` query filters + a `years` summary mode (counts grouped by year) so the frontend can render the accordion headers without fetching every row.

`mark_category` is the **only** column used to split Domestic vs Madrid.

## Components / files

| File | Responsibility |
|---|---|
| `api/routes/gazettes.py` | `GET /overview` aggregation + list filters (`year`/`type`/`status`) + years-summary mode. |
| `api/schemas` (gazette out types) | `GazetteOverviewOut` (streams/coverage/enrichment), year-summary shape. |
| `app/frontend/lib/api.ts` | `gazettesOverview()`, `listGazettes({ year, type, status })`, `gazetteYears()`. |
| `app/frontend/app/(app)/admin/gazettes/page.tsx` | Compose upload + `<GazettesDashboard>` + `<GazettesByYear>`. |
| `components/admin/gazettes-dashboard.tsx` (new) | Metric cards + per-year stacked chart + split + enrichment. |
| `components/admin/gazettes-by-year.tsx` (new) | Collapsible year accordion + filter bar; lazy per-year fetch. |

## Testing

- **Backend:** `/overview` aggregation correctness (stream counts match `mark_category` group-bys; coverage = present-vs-expected; enrichment % matches the existing admin endpoints); list filters (`year`/`type`/`status`) return the right subset; years-summary counts.
- **Frontend:** `tsc --noEmit` + `pnpm lint` (never `pnpm build` against a live dev server); component renders with empty/partial data; accordion lazy-fetch fires once per year.

## Non-goals

- No change to ingest/extraction or `mark_category` derivation. No write operations. No re-classification of existing data. No marks-per-month seasonality or processing-time analytics in v1 (candidates for later). Madrid/domestic enrichment **panels** reuse existing coverage math — they do not add new enrichment logic.

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` by explicit path.
- Backend CI gates: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. Frontend: `tsc --noEmit` + `pnpm lint`; never `pnpm build` while `pnpm dev` is live.
- `mark_category` is the classifier; `record_type` is forbidden for the Domestic/Madrid split.
