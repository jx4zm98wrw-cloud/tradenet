# Similarity slider scale fix + stepper — Design

**Status:** Approved for planning · 2026-06-26

**Goal:** Make the `/search` "Similarity ≥" slider thumb line up with its `%` label, and add `−`/`+`
buttons to nudge the threshold in 5% steps.

## Why (the bug)

In `components/search/query-band.tsx` the slider is `<input type="range" min={0.4} max={0.99}
step={0.01} value={threshold}>` while the label renders `{Math.round(threshold * 100)}%`. A native
range input positions its thumb relative to **its own domain** `[0.4, 0.99]`, so `0.65` renders at
`(0.65 − 0.4)/(0.99 − 0.4) ≈ 42%` of the track — yet the label says `65%`. The two use different
reference scales (track domain `0.4–0.99` vs label `0–100`), so the thumb visually disagrees with the
number at every position (far-left thumb reads "40%", far-right reads "99%"). The filtering value
itself is correct; only the thumb-position-vs-label is wrong.

## Resolution

All changes are in `components/search/query-band.tsx`, the `Similarity ≥` row (~lines 297-306). The
threshold state and `onThresholdChange` callback already live in `app/(app)/search/page.tsx` and are
passed down — no new state, no API change (the threshold is already sent and already filters).

### 1. Scale fix — full 0–100% domain

Change `min={0.4} max={0.99}` to **`min={0} max={1}`** (step stays `0.01`). Now the thumb sits at
`value × track`, so `0.65` renders at 65% of the track, matching the `Math.round(threshold * 100)%`
label by construction. The mismatch is gone for every value.

Edge (accepted per design decision): with `max={1}`, a 100% threshold filters out everything in text
mode (the top text score is ~0.98 for an exact match), so the user can land on "0 results". This is
the honest meaning of "≥100% similar"; the empty-state already coaches "lower the threshold", so
`max={1}` is kept rather than silently capped.

### 2. `−`/`+` stepper

Flank the slider with two `IconButton`s (already exported from `@/components/ui`, used elsewhere in the
app; `query-band.tsx` already imports from `@/components/ui` and `@/components/icons`):

- `−` → `onThresholdChange(step(threshold, -0.05))`
- `+` → `onThresholdChange(step(threshold, +0.05))`
- `step(v, d) = Math.min(1, Math.max(0, Math.round((v + d) * 100) / 100))` — the `round` keeps values
  clean (no `0.6500000001` float drift); the clamp pins to `[0, 1]`.
- `−` is `disabled` when `threshold <= 0`; `+` is `disabled` when `threshold >= 1` (so you can't
  overshoot the ends).

Layout: `Similarity ≥  [−] [====slider====] [+]  65%`. The label and slider already exist; the two
buttons reuse the shared `onThresholdChange`.

## Components & boundaries

| Unit | Change |
|---|---|
| `components/search/query-band.tsx` | slider `min/max` → `0/1`; add `−`/`+` `IconButton`s + `step()` clamp helper; add `IconButton` to the existing `@/components/ui` import |

`app/(app)/search/page.tsx`, the API, the backend, and every other component are **untouched** — the
threshold value, its URL sync (`threshold !== 0.65 ? ... : undefined`), and the request already work.

## Out of scope

- No backend / API / route change — the threshold already round-trips and filters correctly.
- No change to how text-mode scores are computed (the bucketed substring-strength heuristic stays).
- No new state, no new URL param, no migration.

## Testing

Frontend-only UI change — no backend tests:
- `pnpm tsc --noEmit` (typecheck) clean; lint clean. **Never `pnpm build` while `pnpm dev` is live**
  (clobbers `.next`); CI runs the production build separately.
- Manual verification in the running dev app (`localhost:3000/search`):
  1. Thumb position matches the `%` label at several values (e.g. drag to ~mid → reads ~50%; `0.65`
     sits at 65% of the track, not ⅓).
  2. `+` raises the threshold by 5% and re-filters results; `−` lowers it by 5%.
  3. `−` is disabled at 0%, `+` disabled at 100%; no value goes outside `[0,100]%`.
  4. The URL `threshold` param + result filtering still behave (changing the slider re-queries).

## Constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`);
  `git add` explicit paths only.
- Frontend CI gate: `pnpm lint` + `pnpm build` (run by CI). Locally use `tsc --noEmit`; do not
  `pnpm build` while `pnpm dev` is running.

## Decomposition (for the plan)

1. **Scale fix**: `min/max` → `0/1` in `query-band.tsx`; verify thumb matches label.
2. **Stepper**: add the `step()` clamp helper + `−`/`+` `IconButton`s with disabled-at-bounds; verify
   stepping/clamping; `tsc --noEmit` + lint clean.
