# Search: Grant-Status Filter — fix + rename "Granted", drop "Protected in VN" (Design)

**Status:** Approved for planning · 2026-06-24

**Goal:** Make the Search "granted" filter mean *registration status* across **both** regimes (domestic + Madrid), fixing its silent under-count; rename it to **"Granted"**; and remove the redundant **"Protected in VN"** facet.

## Problem

The Search page (`/search`) has two VN-related facets, and both are wrong in different ways:

1. **`VN STATUS → Granted in VN` = 18,994** — filters on `madrid_records.vn_status='granted'`, so it counts **Madrid only** (18,994 ≈ the entire Madrid corpus). The **100,636 domestically-granted marks** (`domestic_records.grant_date`, just enriched) are silently excluded. A user filtering "Granted in VN" misses ~84% of granted marks.
2. **`DESIGNATED JURISDICTION → Protected in VN`** — *jurisdiction*, not status. Every mark in this corpus is VN-scoped by construction (domestic filings are VN; Madrid marks are ingested **because** they designate VN). So this facet matches ~100% of the corpus — it filters nothing.

**Insight (from the user):** "granted in VN" conflates *jurisdiction* (universal here → useless) with *status* (granted vs pending/refused → useful). The status filter is worth keeping + fixing; the jurisdiction filter is noise.

## Resolution

- **"Granted"** (status): keep + **rename** (drop the redundant "in VN") + **fix** to count domestic *and* Madrid grants (~119,630 unified).
- **"Protected in VN"** (jurisdiction): **remove** the facet (and its backend param) — it has no filtering value.

## Architecture — denormalized `vn_grant_date`, backfilled

Follows the proven entity-canonicalization pattern (`applicant_clean`/`applicant_norm` + `backfill_entity_clean.py`): a denormalized column on `trademarks`, resolved from the trusted source, so search faceting stays a single indexed predicate — **no 100k-row join per query** (the perf lesson from the `/admin/domestic` index fix).

### Schema (migration)
Add to `trademarks`:
```
vn_grant_date  date  NULL   -- the VN registration grant date; NULL = not granted
```
Indexed (btree). Chosen over a bare boolean because the search route already exposes `grant_date_from` / `grant_date_to` params — one nullable-date column serves **both** the boolean "Granted" facet (`vn_grant_date IS NOT NULL`) **and** date-range filtering.

### Backfill (`scripts/backfill_vn_grant.py`, idempotent)
Mirrors `backfill_entity_clean.py` (re-runnable, recompute-and-compare, `VN_GRANT_VERSION` guard). Per mark, resolve `vn_grant_date` from the trusted source by identifier:
- **Domestic** (`mark_category ∈ {domestic_application, domestic_registration}`): `domestic_records.grant_date` joined by `application_number`.
- **Madrid** (`madrid_registration` / `madrid_renewal`): `madrid_records.vn_grant_date` (the existing VN grant date) joined by `lineage_key = irn`, when `vn_status='granted'`.
- Else `NULL`.

> The ingest worker does NOT populate `vn_grant_date` (same as `*_norm`), so re-run the backfill after a fresh ingest/enrichment.

### Search wiring (`api/routes/_filters.py` + search route)
- `vn_status='granted'` (or a cleaner `granted: bool` param) → `where(Trademark.vn_grant_date.is_not(None))`.
- `grant_date_from` / `grant_date_to` → range on `Trademark.vn_grant_date`.
- The **"Granted"** facet count = `count(*) where vn_grant_date is not null` over the current filter set.
- **Remove** the `protected_in_vn` / designated-jurisdiction param + facet from the route/filters.

### Frontend (`/search`)
- Rename the facet label **"Granted in VN" → "Granted"**; its count now reflects the unified value.
- **Remove** the **"DESIGNATED JURISDICTION → Protected in VN"** facet block.
- (Sidebar section heading "VN STATUS" can stay or simplify — minor.)

## Data flow

```
backfill_vn_grant → trademarks.vn_grant_date  (domestic_records.grant_date | madrid_records.vn_grant_date)
/search facet "Granted" → count(trademarks.vn_grant_date IS NOT NULL) over filters
filter granted=true     → WHERE vn_grant_date IS NOT NULL   (indexed; no join)
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| migration | add `trademarks.vn_grant_date` + index | — |
| `backfill_vn_grant.py` | resolve grant date from trusted source; idempotent | domestic_records, madrid_records |
| `_filters.py` + search route | granted/date filter on `vn_grant_date`; "Granted" facet; drop protected-in-VN | the column |
| `/search` frontend | rename facet; remove Protected-in-VN block | the facet payload |

## Testing

- **Backfill (idempotent):** a domestic mark with `grant_date` → `vn_grant_date` set; a Madrid mark with `vn_status='granted'` → set from `madrid_records.vn_grant_date`; an ungranted mark → NULL; second run no-op.
- **Filter:** `granted=true` returns only `vn_grant_date IS NOT NULL`; the "Granted" facet count = domestic-granted + Madrid-granted (≈119,630 on the full corpus).
- **Removal:** no `protected_in_vn` param/facet remains (grep); the search response no longer includes it.
- Targeted pytest only — sweep tests reset the live `domestic_sweep_control` singleton.

## Out of scope (v1)

- Richer status facet (pending / refused / abandoned) — only the granted/not-granted split. (Could extend later via the same column + a status field.)
- Changing the "VN STATUS" section heading or other facets.
- No new enrichment fetch — uses already-stored grant data.

## Constraints

- One migration (`alembic check` will require it). NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.

## Decomposition (for the plan)

1. **Schema + backfill:** migration adds `trademarks.vn_grant_date` + index; `scripts/backfill_vn_grant.py` (idempotent, version-guarded); run it. Tests.
2. **Backend search:** `_filters.py` granted/date filter on `vn_grant_date`; "Granted" facet count; remove `protected_in_vn`. Tests.
3. **Frontend:** rename "Granted in VN" → "Granted"; remove the "Protected in VN" facet block.
