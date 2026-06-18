# Madrid Enrichment Admin Panel (Design)

**Status:** Approved for planning · 2026-06-18

**Goal:** Surface live Madrid (WIPO) enrichment progress in the admin UI — how many
unique Madrid IRNs the system holds, how many have been validated via the WIPO
endpoint, and how many remain — so an operator can monitor the sweep's coverage
without running ad-hoc SQL.

## Core principle: derived, not stored

Every number is computed at request time from `SELECT count(...)` over
`trademarks` and `madrid_records`. There is **no stored counter** to maintain or
to drift. `remaining = unique_irns − validated` is correct-by-construction.

This was validated against a real drift incident: the running sweep printed
`total remaining 2775` from a cache snapshot taken at its start (cache ≈ 1,665),
while the live DB denominator is 4,440. A stored/snapshot number goes stale; a
derived one cannot.

## Definitions (authoritative)

- **Unique IRNs** = `count(distinct lineage_key)` over `trademarks` where
  `mark_category IN ('madrid_registration','madrid_renewal')` and `lineage_key`
  is non-null/non-empty. This is exactly what `madrid_enrich.backfill.iter_madrid_irns()`
  returns (the sweep's work-list). Value today: **4,440**.
- **Validated** = `count(*)` from `madrid_records` (a row exists ⇒ the IRN was
  fetched + parsed + stored). The durable outcome, not the cache. Value: **1,732**.
- **Remaining** = `unique_irns − validated`. Value: **2,708**.
- **pct_complete** = `validated / unique_irns` (0.0 when `unique_irns == 0`).
- **vn_granted** = `count(*)` from `madrid_records where vn_status='granted'`.
- **by_category** = distinct `lineage_key` count per `mark_category`
  (`madrid_registration`, `madrid_renewal`).

"Validated" deliberately counts `madrid_records` rows, **not** cached HTML files.
Cache (1,730) and DB (1,732) differ slightly; the DB is the source of truth for
"done."

## Architecture

### Backend — one endpoint

`GET /api/v1/admin/madrid-enrichment` in `app/backend/api/routes/admin.py`
(grouped with admin ops; gated by the same admin requirement used for other
`/admin/*` ops — defense in depth, mirroring the gazettes listing).

Response model `MadridEnrichmentStats` (Pydantic `BaseModel`):

```python
class MadridEnrichmentStats(BaseModel):
    unique_irns: int
    validated: int
    remaining: int
    pct_complete: float        # 0.0–1.0
    vn_granted: int
    by_category: dict[str, int]  # {"madrid_registration": N, "madrid_renewal": M}
```

Implementation: async SQLAlchemy `select(func.count(...))` queries against the
existing session dependency (`get_session`). The unique-IRN query reuses the
exact predicate from `iter_madrid_irns` so the panel and the sweep can never
disagree on the denominator. No new tables, no migration.

### Frontend — one page

`app/frontend/app/(app)/admin/madrid/page.tsx`, a client component following the
`/admin/gazettes` pattern:

- **Access gate:** `api.adminCheck()` → redirect non-admins to `/today`
  (identical to the gazettes page).
- **Data:** `api.adminMadridStats()` (new method in `lib/api.ts` calling the
  endpoint above; new `MadridEnrichmentStats` TS type).
- **Render:** a progress bar (`validated / unique_irns`), stat cards for the six
  figures, and a per-category mini-breakdown. A **Refresh** button re-fetches;
  **light auto-poll** (every ~5s) runs only while `remaining > 0` (mirrors the
  gazettes page's conditional polling).
- **Navigation:** add a link to `/admin/madrid` wherever `/admin/gazettes` is
  linked in the app nav/layout, so the panel is reachable.

### Data flow

```
admin page → GET /api/v1/admin/madrid-enrichment (require_admin)
           → count queries over trademarks + madrid_records
           → MadridEnrichmentStats JSON → stat cards + progress bar
```

## Error handling

- Endpoint: non-admin → 403 (via the admin dependency); unauthenticated → 401.
- Page: admin-check failure → "Admin check failed" message (as gazettes does);
  fetch failure → inline error, Refresh to retry.

## Testing

Backend pytest (httpx + ASGI, matching `app/backend/tests/`):

1. Seed N Madrid `trademarks` (mix of `madrid_registration`/`madrid_renewal`,
   some sharing a `lineage_key` across rows) + M `madrid_records` (subset of
   those IRNs, some `vn_status='granted'`).
2. Assert `unique_irns`, `validated`, `remaining = unique − validated`,
   `pct_complete`, `vn_granted`, and `by_category` match the seeded data.
3. Assert a non-admin user receives 403.

Frontend: no component test (the existing `/admin/gazettes` page has none;
match the established pattern). Verify manually in the running app.

## Non-goals

- **Live progress of the running sweep process.** Its progress lives in
  `/tmp/madrid_sweep.log`, not the DB. Surfacing it would require the sweep to
  persist status to a table — a separate, larger piece, flagged for later.
- **Cached-file count.** An implementation detail of the sweep, not a product
  metric. Omitted (DB `validated` is the truth for "done").
- **Triggering or controlling the sweep from the UI.** Read-only panel.

## Out-of-scope follow-ups (noted, not built)

- A sweep-status table so the panel can show the live in-flight batch.
- The gazette-vs-WIPO standardization audit
  (`docs/superpowers/specs/2026-06-18-madrid-standardization-design.md`) is a
  separate thread.
