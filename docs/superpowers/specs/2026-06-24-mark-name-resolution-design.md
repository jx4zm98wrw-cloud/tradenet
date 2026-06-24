# Resolved Mark Name (denormalized `trademarks.mark_name`) — Design

**Status:** Approved for planning · 2026-06-24

**Goal:** Fix the ~172,085 domestic marks (78.5% of all domestic) that display the **applicant** instead of their real mark name, by resolving a single denormalized `trademarks.mark_name` (`mark_sample` → `domestic.mark_text` → `madrid.mark_text` → figurative placeholder) that every surface reads.

## Problem

`markDisplay(mark, wordmarkOverride?)` (`lib/mark-display.ts:88`) takes an optional wordmark override:
- The **mark-detail page** passes it (`marks/[id]/page.tsx:177`: `markDisplay(m, …?? detail.domestic?.mark_text)`) → correct name.
- The **search grid/table** (`results-grid.tsx:28`, `results-table.tsx:40`) and **cmdk** (`cmdk.tsx:158`) call `markDisplay(m)` with **no override** — their payloads don't carry `domestic.mark_text`, so the chain falls through `mark_sample` → applicant.

For figurative domestic marks, `mark_sample` (the `(540)` wordmark) is empty, so the card shows the applicant. Confirmed live:

| appno | `mark_sample` | `domestic.mark_text` | card shows |
|---|---|---|---|
| 4-2024-00990 | *(empty)* | **TRADAGUI** | "DƯỢC PHẨM" (applicant) |
| 4-2024-08402 | *(empty)* | **Tiniclean HOUSE CLEANING** | "NGUYỄN THỊ" (applicant) |
| 4-2024-40980 | **Taseko** | Taseko | "Taseko" ✓ |

Counts: 219,154 domestic; 178,193 empty `mark_sample`; **172,085 of those have a real `domestic.mark_text`** — recoverable. The data exists; only display resolution is wrong, and it's inconsistent (detail correct, search/cmdk/compare/exports wrong).

## Resolution — one denormalized field every surface reads

Rather than thread `domestic.mark_text` into each individual payload (many call sites to remember), denormalize a resolved name onto `trademarks`, mirroring `vn_grant_date` / `applicant_clean`.

### Schema (migration)
Add to `trademarks`:
```
mark_name  text  NULL   -- resolved display name; NULL = figurative (no wordmark)
```
Indexed (btree) — used by future "by mark name" lookups and keeps payloads cheap.

### Resolution order (the helper the backfill uses)
`mark_sample` (non-empty) → `domestic_records.mark_text` (non-empty, joined by `application_number`) → `madrid_records.mark_text` (non-empty, joined by `lineage_key = irn`) → `NULL`. Trimmed; empty strings treated as absent.

### Backfill (`scripts/backfill_mark_name.py`, idempotent)
Mirrors `backfill_vn_grant.py` (recompute-and-compare, `MARK_NAME_VERSION` guard). ~172k+ rows updated. **The ingest worker does NOT populate it — re-run after a fresh ingest/enrichment** (same caveat as `*_norm` / `vn_grant_date`).

### Backend
`TrademarkOut` serializes `mark_name`. Because search / cmdk / compare / exports / watchlists / today all return Trademark rows, they get the resolved name from this one field — no per-payload joins.

### Frontend (`lib/mark-display.ts` + call sites)
- `markDisplay` uses `mark.mark_name` as the wordmark source; when it's null/empty → name renders the placeholder **"(figurative mark)"**. **Drop the applicant fallback from the name path** (the applicant still appears in its own card line/row — it just stops masquerading as the mark name).
- Keep the `wordmarkOverride` param (detail page), but it defaults to `mark.mark_name`; the icon-initials logic falls back to a neutral glyph (e.g. "◧"/"?") rather than applicant initials when there's no name.

## Data flow

```
backfill_mark_name → trademarks.mark_name  (mark_sample | domestic.mark_text | madrid.mark_text | NULL)
TrademarkOut.mark_name → markDisplay(mark) → mark.mark_name  OR  "(figurative mark)"
   → search grid/table, cmdk, compare, exports, watchlists, today — all consistent
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| migration | add `trademarks.mark_name` + index | — |
| `backfill_mark_name.py` | resolve name from the trusted sources; idempotent | domestic_records, madrid_records |
| `TrademarkOut` | serialize `mark_name` | the column |
| `lib/mark-display.ts` | use `mark_name`; "(figurative mark)" when empty; no applicant fallback | the payload field |

## Testing

- **Backfill (idempotent, table tests):** `mark_sample` set → that; empty `mark_sample` + `domestic.mark_text` → that; both empty + `madrid.mark_text` → that; all empty → NULL; second run no-op.
- **markDisplay (pure):** `mark_name` present → shown; `mark_name` null → "(figurative mark)" (NOT the applicant); given a `wordmarkOverride` → that wins.
- **payload:** a search result for a figurative domestic mark carries `mark_name` = the `domestic.mark_text` (e.g. "TRADAGUI"), not the applicant.
- Targeted pytest only — sweep tests reset the live `domestic_sweep_control` singleton.

## Out of scope (v1)

- No logo OCR / re-extraction — the ~6,108 marks with no extracted name anywhere stay "(figurative mark)" (the logo still renders).
- **Search ranking** still matches `mark_sample`/applicant (`search.py:96`); matching on `mark_name` is a separate follow-up — this is a display-only fix.
- No change to the applicant display (it stays in its own line/row).

## Constraints

- One migration (`alembic check` will require it). NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.

## Decomposition (for the plan)

1. **Schema + backfill:** migration adds `trademarks.mark_name` + index; `scripts/backfill_mark_name.py` (idempotent, version-guarded); run it (~172k). Tests.
2. **Backend payload:** add `mark_name` to `TrademarkOut`. Test a search result carries it.
3. **Frontend:** `markDisplay` reads `mark_name`, renders "(figurative mark)" when empty, drops the applicant fallback; update the TS type.
