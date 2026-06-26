# Similarity Slider Scale Fix + Stepper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the `/search` "Similarity ≥" slider thumb match its `%` label, and add `−`/`+` buttons that step the threshold by 5%.

**Architecture:** One component (`components/search/query-band.tsx`). Change the range input's domain from `[0.4, 0.99]` to `[0, 1]` so the thumb position equals the `%` label, and flank it with two `IconButton`s wired to a clamped step helper. No backend, API, or state change — the threshold value already round-trips and filters.

**Tech Stack:** Next.js 15 + React + Tailwind 4 (TypeScript). Verification: `tsc --noEmit` + lint + manual.

---

## Background the engineer needs

- Work in `app/frontend`. Typecheck with `pnpm tsc --noEmit` and lint with `pnpm lint`. **NEVER run `pnpm build` while `pnpm dev` is live** (clobbers `.next` → "Internal Server Error" on every route); CI runs the production build separately.
- Spec: `docs/superpowers/specs/2026-06-26-search-similarity-slider-design.md`.
- The slider lives in `components/search/query-band.tsx`, in the `Extras` component, the `Similarity ≥` row (currently lines ~296-308). `threshold` (a 0–1 fraction) and `onThresholdChange` are already passed in from `app/(app)/search/page.tsx`.
- `IconButton` is exported from `@/components/ui` (a 30×30 button that spreads `...rest`, so `onClick`, `disabled`, `aria-label`, `title` all work). `query-band.tsx` already imports `{ FilterChip } from "@/components/ui"`.
- **GUARDRAILS:** NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`). `git add` explicit paths only — never `-A`/`.`/`-u`.

## File map

| File | Change |
|---|---|
| `app/frontend/components/search/query-band.tsx` | slider `min/max` → `0/1`; add `stepThreshold` helper + `−`/`+` `IconButton`s; add `IconButton` to the `@/components/ui` import |

---

### Task 1: Scale fix + `−`/`+` stepper

**Files:**
- Modify: `app/frontend/components/search/query-band.tsx`

- [ ] **Step 1: Add `IconButton` to the existing UI import**

Line 5 is:
```tsx
import { FilterChip } from "@/components/ui";
```
Change it to:
```tsx
import { FilterChip, IconButton } from "@/components/ui";
```

- [ ] **Step 2: Add the clamped step helper (module scope)**

Near the top of the file, after the imports (above the first component), add:
```tsx
/** Step the similarity threshold by `d`, rounded to 2 decimals and clamped to [0, 1]. */
const stepThreshold = (v: number, d: number): number =>
  Math.min(1, Math.max(0, Math.round((v + d) * 100) / 100));
```

- [ ] **Step 3: Rewrite the `Similarity ≥` row (scale fix + buttons)**

Replace the current block (lines ~296-308):
```tsx
      <div className="flex items-center gap-2 text-xs">
        <span className="text-mute">Similarity ≥</span>
        <input
          type="range"
          min={0.4} max={0.99} step={0.01}
          value={threshold}
          onChange={(e) => onThresholdChange(parseFloat(e.target.value))}
          className="w-40 accent-stamp"
        />
        <span className="font-mono font-semibold text-stamp tabular w-9 text-right">
          {Math.round(threshold * 100)}%
        </span>
      </div>
```
with:
```tsx
      <div className="flex items-center gap-2 text-xs">
        <span className="text-mute">Similarity ≥</span>
        <IconButton
          title="Lower threshold by 5%"
          aria-label="Lower similarity threshold"
          disabled={threshold <= 0}
          onClick={() => onThresholdChange(stepThreshold(threshold, -0.05))}
        >
          −
        </IconButton>
        <input
          type="range"
          min={0} max={1} step={0.01}
          value={threshold}
          onChange={(e) => onThresholdChange(parseFloat(e.target.value))}
          className="w-40 accent-stamp"
        />
        <IconButton
          title="Raise threshold by 5%"
          aria-label="Raise similarity threshold"
          disabled={threshold >= 1}
          onClick={() => onThresholdChange(stepThreshold(threshold, 0.05))}
        >
          +
        </IconButton>
        <span className="font-mono font-semibold text-stamp tabular w-9 text-right">
          {Math.round(threshold * 100)}%
        </span>
      </div>
```

(The `−` is a U+2212 minus sign to match the existing typographic style; a plain `-` is acceptable too.)

- [ ] **Step 4: Typecheck**

Run: `cd app/frontend && pnpm tsc --noEmit`
Expected: no errors.

- [ ] **Step 5: Lint**

Run: `cd app/frontend && pnpm lint`
Expected: clean (no new warnings/errors in `query-band.tsx`).

- [ ] **Step 6: Manual verification in the running dev app**

With `pnpm dev` running, open `localhost:3000/search`:
- The thumb position now matches the label: `0.65` sits at ~65% of the track (not ⅓); drag to mid → ~50%.
- `+` raises the threshold by 5% and re-filters the results; `−` lowers it by 5%.
- `−` is disabled at `0%`, `+` is disabled at `100%`; the value never leaves `[0, 100]%`.
- Changing the slider/buttons still updates the URL `threshold` param and re-queries (unchanged behavior).

- [ ] **Step 7: Commit**

```bash
git add app/frontend/components/search/query-band.tsx
git commit -m "fix(search): similarity slider thumb matches label (0-1 scale) + 5% stepper"
```

---

### Task 2: Open the PR

- [ ] **Step 1: Push and open the PR**

Push the branch and open a PR (base `main`) titled **"Search: fix similarity slider scale + add ± stepper"**.
Body: explains the thumb-vs-label mismatch (slider domain `0.4–0.99` vs label `value × 100`), the
`min/max → 0/1` fix, the `±5%` clamped stepper, and that it's frontend-only (no backend/API change).
Note the accepted `max={1}` edge (100% = exact-only → may yield 0 results). Do NOT merge — the human
reviews and squash-merges.

---

## Self-Review

**1. Spec coverage:** scale fix `min/max → 0/1` (Task 1 Step 3); `stepThreshold` clamp helper (Step 2);
`−`/`+` `IconButton`s with disabled-at-bounds (Step 3); import (Step 1); typecheck + lint + manual
verification (Steps 4-6). All spec sections mapped. No backend/test files (frontend-only, as scoped).

**2. Placeholder scan:** none — the full before/after JSX and the helper are literal.

**3. Type/identifier consistency:** `stepThreshold(v, d)`, `onThresholdChange`, `threshold`,
`IconButton` used consistently; `min={0} max={1}` matches the spec; the disabled guards (`<= 0`,
`>= 1`) match the clamp bounds.
