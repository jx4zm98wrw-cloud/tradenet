# Mark Status: Single Source of Truth (faithful label + normalized tone) — Design

**Status:** Approved for planning · 2026-06-24

**Goal:** Replace the crude `record_type`-based status heuristic — duplicated in the compare page and the mark-detail endpoint — with one shared helper that derives an **IP VIETNAM-faithful status label** + a **normalized tone** from the enriched data, and surface it on `/compare` (which today carries no status field and invents a stub).

## Problem

The mark "Status" is wrong in two places, both keyed off `record_type` (the unreliable A/B enum that mislabels 111-only Madrid registrations as `B_domestic`), neither using the enriched data:

- **`compare/page.tsx:112–122`** hardcodes `m.record_type === "A" ? "Pending publication" : "Active"`. So every application shows **"Pending publication"** — even when it has a gazette **Published** date + source gazette shown on the same page. The `CompareResponse` payload carries **no** status field, which forced this stub.
- **`marks.py:87–93`** (mark detail) is the same shape: `record_type == A → "Examination pending"`, expired → "Lapsed", else "Active registration". Also ignores `domestic_records.status_code` and the new `trademarks.vn_grant_date`.

Result: a Chinese-applicant UV-Rays application that's published in the gazette reads "Pending publication," contradicting the data beside it.

## Resolution — one `derive_status` helper

### `api/_status.py` (new, pure)
`derive_status(domestic_status_code: str | None, vn_grant_date: date | None, expiry_date: date | None, *, today: date) -> tuple[str, str]` → `(label, tone)`:

- **Label (IP VIETNAM-faithful):**
  - enriched domestic (`domestic_status_code` non-empty) → the status_code **verbatim** (e.g. `"Cấp bằng"`, `"Đang giải quyết"`).
  - else `vn_grant_date` present → `"Granted"`.
  - else `expiry_date` and `expiry_date < today` → `"Lapsed"`.
  - else → `"Pending"`.
- **Tone (normalized, drives the dot color):**
  - `vn_grant_date` present → `"ok"`.
  - `expiry_date < today` → `"mute"`.
  - else → `"warn"`.

So a Vietnamese status string still gets a sensible color, and the taxonomy is consistent across domestic + Madrid (Madrid has no `domestic_status_code`, so it uses the normalized fallback — granted/lapsed/pending).

### Wiring

- **mark-detail (`marks.py`):** replace the `record_type` branch with `derive_status(...)`. It already has the mark + the domestic join; read `domestic_records.status_code`, `mark.vn_grant_date`, and the expiry it already uses (`expiry_date_141`). Keep `statusLabel`/`statusTone` field names (frontend unchanged).
- **compare (`compare.py`):** the compare query already loads the marks; LEFT JOIN `domestic_records` for `status_code` (and `vn_grant_date` is already on `Trademark`). Add **`status_label: str` + `status_tone: str`** to each mark entry in `CompareResponse`, computed via `derive_status`.

### Frontend (`compare/page.tsx`)
Drop the `isA` stub (`:112–122`); render `m.status_label` with `<PulseDot tone={m.status_tone}>`. Add `status_label`/`status_tone` to the compare mark TS type in `lib/api.ts`. Mark-detail already consumes `statusLabel`/`statusTone` — no frontend change there.

## Data flow

```
derive_status(domestic_records.status_code, trademarks.vn_grant_date, expiry, today=DEMO_TODAY)
   → mark-detail.statusLabel/statusTone   (replaces record_type heuristic)
   → compare mark.status_label/status_tone (new fields; frontend renders instead of the isA stub)
```

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `api/_status.py:derive_status` | pure: (status_code, grant_date, expiry) → (label, tone) | — |
| `marks.py` mark-detail | use the helper for statusLabel/statusTone | helper, domestic join, vn_grant_date |
| `compare.py` | join domestic status_code; add status_label/status_tone | helper |
| `compare/page.tsx` + `lib/api.ts` | render the real status; drop the stub | the new payload fields |

## Testing

- **Helper (pure, table tests):** enriched `status_code="Cấp bằng"` → label that verbatim; tone `ok` if `vn_grant_date` set. Un-enriched + `vn_grant_date` → `("Granted","ok")`. Expired, no grant → `("Lapsed","mute")`. Else → `("Pending","warn")`. status_code wins the label even without grant_date; tone still from grant/expiry.
- **compare route:** the response includes `status_label`/`status_tone` per mark; an A-file enriched as granted shows "Granted"/ok (NOT "Pending publication").
- **mark-detail:** statusLabel comes from the helper (granted mark → "Granted"/ok, not "Examination pending").
- Targeted pytest only — sweep tests reset the live `domestic_sweep_control` singleton.

## Out of scope (v1)

- No new enrichment fetch (uses stored data). No change to similarity scoring or the conflict scorecard. No Madrid-specific status text (Madrid uses the normalized fallback). No status filter on search (that's the separate grant-status work, already shipped).

## Constraints

- No migration (uses existing columns: `domestic_records.status_code`, `trademarks.vn_grant_date`). NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.

## Decomposition (for the plan)

1. **Helper + mark-detail:** `api/_status.py:derive_status` (+ unit tests); wire into `marks.py` (replace the record_type branch). Tests.
2. **Compare backend:** join `domestic_records.status_code`; add `status_label`/`status_tone` to `CompareResponse` via the helper. Tests.
3. **Frontend:** compare page renders the real status (drop the `isA` stub) + `lib/api.ts` type.
