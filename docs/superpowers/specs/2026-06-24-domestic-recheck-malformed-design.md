# Domestic: Admin Re-check Pending + Malformed-Appno Surfacing (Design)

**Status:** Approved for planning · 2026-06-24

**Goal:** Give the `/admin/domestic` operator two things the not_found backoff didn't: (1) an on-demand **"re-check all pending"** control to re-probe IP VIETNAM without waiting out the 30-day backoff, and (2) a **verification mechanism** that surfaces *malformed* application numbers (the truncated `4-2024-1` class) which today rot invisibly inside the "unresolved" count.

## Background

The not_found fix (migration `20260623_0024`) records IP VIETNAM "no published detail" responses in `domestic_not_found` with a 30-day backoff: the sweep work-list excludes any appno whose `last_checked_at >= now − _NOT_FOUND_BACKOFF` (`worker/domestic_sweep.py:131–146`). Two gaps surfaced:

1. **No manual re-check.** When IP VIETNAM publishes a batch, an operator can't force a re-probe of the pending marks — they wait up to 30 days.
2. **Malformed appnos are invisible.** `4-2024-1` was a real mark (SUSHI) whose `(210)` was truncated at extraction. `appno_to_vnid("4-2024-1")` returns `None`, so `enrich_one` skips it silently (no fetch) and it sits forever inside "unresolved". It was only caught by eyeballing the dashboard's `1`.

## Part A — "Re-check all pending" control

The backoff is just a timestamp gate, so a re-check is a timestamp reset — no new fetch plumbing.

- **Backend:** new admin endpoint `POST /api/v1/admin/domestic-sweep/recheck-pending` (mirrors the existing `domestic-sweep` start/pause/stop/config actions in `api/routes/admin.py`). It runs:
  `UPDATE domestic_not_found SET last_checked_at = now() − (_NOT_FOUND_BACKOFF + 1 day) WHERE application_number NOT IN (SELECT application_number FROM domestic_records)`
  — moving the *unvalidated* not_found rows' `last_checked_at` back so they fall out of `recent_not_found` and re-enter the sweep's `todo`. Setting the timestamp (vs deleting the row) preserves `check_count` + `first_seen_at` history. Then, **if the sweep status is `idle`, enqueue one chunk** so the re-check actually runs without a separate Start; if it's already `running`, it picks them up on the next pass. Returns `{reset: <count>}`.
- **Frontend (`/admin/domestic/page.tsx`):** a **"Re-check pending (N)"** button near the Pending-publication stat / sweep controls. Shows a confirm (it re-fetches N marks from IP VIETNAM). On success, calls `refresh()`. New `api.domesticSweepRecheckPending()` in `lib/api.ts`.

## Part B — Malformed-appno surfacing (verification mechanism)

- **Detection (deterministic, pure):** an appno is **malformed** iff `domestic_enrich.idmap.appno_to_vnid(appno) is None` — i.e. it can't be mapped to a valid IP VIETNAM id (wrong length/format, like the truncated `4-2024-1`). No fetching or guessing.
- **Backend:** extend `DomesticEnrichmentStats` (`api/routes/admin.py:110`) with:
  - `malformed: int`
  - `malformed_appnos: list[MalformedAppno]` where `MalformedAppno = {application_number, applicant_name, gazette}` — capped (e.g. top 50) for display.
  Computed by taking the **unresolved set** (domestic appnos not in `domestic_records` and not in `domestic_not_found`) and partitioning with `appno_to_vnid`: `None` → malformed, else → unresolved. The unresolved set is tiny (single digits to low hundreds), so the per-appno check is cheap. **`unresolved` now means *fetchable*-unresolved** (mappable but not yet fetched); `malformed` is split out so the two are operationally distinct.
- **Frontend:** a new **"Malformed — needs review"** stat card next to Unresolved/Pending, plus a short list (appno · applicant · gazette) so any `4-2024-1`-style mark surfaces immediately. Correction is manual for v1 (the SUSHI method: fix the `trademarks.application_number`, then it enriches).

## Data flow

```
/admin/domestic load → GET /api/v1/admin/domestic-enrichment
   → unique/validated/granted (as today)
   → remaining set = domestic appnos ∉ domestic_records
       → in domestic_not_found (unvalidated) → pending_publication
       → else, appno_to_vnid is None         → malformed (+ list)
       → else                                 → unresolved (fetchable)

Re-check button → POST /api/v1/admin/domestic-sweep/recheck-pending
   → reset last_checked_at on unvalidated domestic_not_found rows
   → if idle: enqueue one chunk
   → sweep re-probes → validated OR re-cached not_found
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `recheck-pending` endpoint | reset backoff on unvalidated not_found; kick a chunk if idle | `domestic_not_found`, sweep enqueue |
| `DomesticEnrichmentStats` + malformed compute | split unresolved into fetchable vs malformed; list malformed | `appno_to_vnid` |
| `/admin/domestic` button + card + api | trigger re-check; show malformed | the two endpoints |

## Out of scope (v1)

- In-UI appno editing/correction (operator fixes `trademarks.application_number` manually, as for SUSHI).
- Catching **well-formed-but-wrong-digit** appnos that map to a real-but-empty IP VIETNAM record (those land in pending looking legit; reliably catching them needs cross-checking the IP VIETNAM applicant vs the gazette applicant — heavier).
- Per-mark re-check (only "all pending").

## Testing

- **Pure / malformed detection:** an unresolved appno where `appno_to_vnid` is `None` is counted in `malformed` (with its applicant/gazette) and NOT in `unresolved`; a mappable unresolved appno stays in `unresolved`.
- **Re-check:** a `domestic_not_found` row with recent `last_checked_at` is moved back by the endpoint so it's no longer in `recent_not_found` (becomes sweep-eligible); validated appnos are not touched; endpoint returns the reset count; idle→enqueues a chunk (assert enqueue called via a stubbed enqueue).
- Targeted pytest only — sweep tests reset the live `domestic_sweep_control` singleton.

## Non-goals / constraints

- No schema change (reuses `domestic_not_found`; malformed is computed live). No migration.
- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.

## Decomposition (for the plan)

1. **Backend — malformed surfacing:** `MalformedAppno` schema + `malformed`/`malformed_appnos` on `DomesticEnrichmentStats`; partition the unresolved set with `appno_to_vnid`. Tests.
2. **Backend — recheck-pending endpoint:** the reset SQL + idle-enqueue; `{reset}` response. Tests.
3. **Frontend:** `api.ts` methods; the "Re-check pending (N)" button (+ confirm) and the "Malformed — needs review" card + list on `/admin/domestic`.
