# Dead Mode — Frontend Toggle + Readouts (PR 5 of 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Surface Dead mode on `/admin/domestic` — a toggle that flips `mode` live via the config endpoint, a mode badge, and live readouts (concurrency, success rate, req/s).

**Architecture:** Two additive edits. `lib/api.ts`: `DomesticSweepControl` gains `mode`/`concurrency`; `SweepCadence` gains optional `mode` so `domesticSweepConfig`/`domesticSweepStart` can carry it. `app/(app)/admin/domestic/page.tsx`: extend `SweepControlCard` with a mode pill, a Dead-mode toggle (calls `domesticSweepConfig({ mode })`), and a readout line. No new components, no backend changes.

**Tech Stack:** Next.js 15 (App Router), React, TypeScript, Tailwind 4.

**Spec:** `docs/superpowers/specs/2026-06-21-domestic-dead-mode-design.md` (§Control surface — Frontend).

## Scope

PR 5 of 5, frontend only. The backend (PRs 1-4) is live: `domesticSweepConfig` accepts `{ mode }`, GET returns `mode`/`concurrency`. After this PR the operator can flip dead mode from the UI and watch it ramp.

## Standing constraints

- **NEVER commit the rename trio** (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` by explicit path.
- **GateGuard**: state facts on first Edit per file + first Bash; retry.
- **CRITICAL — never run `pnpm build` while `pnpm dev` may be live** (it clobbers `.next` → "Internal Server Error" on every route). Typecheck with `npx tsc --noEmit` and lint with `pnpm lint`. CI runs the real `pnpm build` in its own environment.
- Run frontend commands from `app/frontend/`.

## File Structure

| File | Responsibility |
|---|---|
| `app/frontend/lib/api.ts` | `DomesticSweepControl` +`mode`/`concurrency`; `SweepCadence` +`mode`. |
| `app/frontend/app/(app)/admin/domestic/page.tsx` | `SweepControlCard`: mode pill + Dead-mode toggle + readouts. |

---

## Task 1: API client types

**Files:**
- Modify: `app/frontend/lib/api.ts`

- [ ] **Step 1: Add `mode` + `concurrency` to `DomesticSweepControl`**

In `lib/api.ts`, in the `DomesticSweepControl` type, add two fields after `failed: number;`:

```ts
  mode: "normal" | "dead";
  concurrency: number;
```

- [ ] **Step 2: Add optional `mode` to `SweepCadence`**

Replace the `SweepCadence` type (currently `export type SweepCadence = { cap?: number | null; delay?: number; jitter?: number; chunk_size?: number };`) with:

```ts
export type SweepCadence = { cap?: number | null; delay?: number; jitter?: number; chunk_size?: number; mode?: "normal" | "dead" };
```

- [ ] **Step 3: Typecheck**

```bash
cd app/frontend && npx tsc --noEmit
```
Expected: no errors. (Do NOT run `pnpm build`.)

- [ ] **Step 4: Commit**

```bash
git add app/frontend/lib/api.ts
git commit -m "$(printf 'feat(dead-mode): mode + concurrency on the domestic sweep API client types\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Task 2: Toggle + readouts on the admin page

**Files:**
- Modify: `app/frontend/app/(app)/admin/domestic/page.tsx`

- [ ] **Step 1: Add a mode pill next to the status pill**

In `SweepControlCard`, find the status-pill block:

```tsx
            <span className="text-sm font-semibold">Sweep control</span>
            <Pill tone={tone as "ok" | "warn" | "mute"} size="sm">{s.status}</Pill>
```

Add a dead-mode pill right after the status pill:

```tsx
            <span className="text-sm font-semibold">Sweep control</span>
            <Pill tone={tone as "ok" | "warn" | "mute"} size="sm">{s.status}</Pill>
            {s.mode === "dead" ? <Pill tone="warn" size="sm">Dead mode</Pill> : null}
```

- [ ] **Step 2: Add the req/s sampling state**

`rps` is the throughput derived from the `processed` delta between polls. In `SweepControlCard`, add this state right after the existing `const [err, setErr] = React.useState<string | null>(null);` line:

```tsx
  const [rps, setRps] = React.useState<number | null>(null);
  const sample = React.useRef<{ processed: number; t: number } | null>(null);
```

Then, inside the `load` callback, right after `setS(next);`, add the sampling:

```tsx
      const t = Date.now();
      if (sample.current && next.processed >= sample.current.processed) {
        const dp = next.processed - sample.current.processed;
        const dt = (t - sample.current.t) / 1000;
        if (dt > 0) setRps(dp / dt);
      } else {
        setRps(null); // counter reset (new run) — drop the stale rate
      }
      sample.current = { processed: next.processed, t };
```

- [ ] **Step 3: Add the Dead-mode toggle row + readouts**

In `SweepControlCard`, locate the "this run" readout block:

```tsx
        <div className="text-[12px] text-mute">
          this run: <span className="font-mono text-ink">{formatNumber(s.processed)}</span> processed ·{" "}
          <span className="font-mono text-ok">{formatNumber(s.ok)}</span> ok ·{" "}
          <span className="font-mono text-rose-600">{formatNumber(s.failed)}</span> failed
          {s.current_appno ? <> · current <span className="font-mono text-ink">{s.current_appno}</span></> : null}
          {s.next_appno ? <> · next <span className="font-mono text-ink">{s.next_appno}</span></> : null}
        </div>
```

Immediately BEFORE that block, insert the toggle row and the dead-mode readout:

```tsx
        <div className="flex items-center justify-between gap-2 flex-wrap border-t border-line pt-3">
          <div className="text-[11px] text-mute max-w-prose">
            <span className="font-semibold text-ink">Dead mode</span> — max-throughput adaptive concurrency on
            the single clean IP; auto-throttles and auto-reverts to normal + pauses on sustained NOIP blocks.
          </div>
          <Button
            variant={s.mode === "dead" ? "primary" : "ghost"}
            disabled={busy}
            onClick={() => act(() => api.domesticSweepConfig({ mode: s.mode === "dead" ? "normal" : "dead" }))}
          >
            {s.mode === "dead" ? "Disable dead mode" : "Enable dead mode"}
          </Button>
        </div>

        <div className="text-[12px] text-mute">
          rate: <span className="font-mono text-ink">{s.processed > 0 ? `${Math.round((s.ok / s.processed) * 100)}%` : "—"}</span>
          {s.mode === "dead" ? <> · concurrency <span className="font-mono text-ink">{s.concurrency}</span></> : null}
          {rps !== null ? <> · <span className="font-mono text-ink">{rps.toFixed(1)}</span> req/s</> : null}
        </div>
```

- [ ] **Step 4: Typecheck + lint**

```bash
cd app/frontend && npx tsc --noEmit && pnpm lint
```
Expected: no type errors; lint clean. (Do NOT run `pnpm build`.)

- [ ] **Step 5: Commit**

```bash
git add app/frontend/app/\(app\)/admin/domestic/page.tsx
git commit -m "$(printf 'feat(dead-mode): /admin/domestic dead-mode toggle + concurrency/rate readouts\n\nCo-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>')"
```

---

## Self-Review

**Spec coverage** (§Control surface — Frontend):
- Dead-mode toggle with caption → Step 3 toggle row. ✅
- Live mode flip via config → `api.domesticSweepConfig({ mode })`. ✅
- Live readouts: concurrency (when dead), success rate, req/s → Steps 2-3. ✅
- Mode badge → Step 1 pill. ✅

**Placeholder scan:** none.

**Type/consistency:** `mode` is `"normal" | "dead"` in both `DomesticSweepControl` and `SweepCadence`; `domesticSweepConfig` already takes `SweepCadence`, so `{ mode }` typechecks; `s.concurrency` is `number`; the toggle reuses the existing `act()`/`busy` machinery and the 3s `load()` poll already in the card; `rps` is `number | null` and rendered defensively. No backend or new-file changes.
