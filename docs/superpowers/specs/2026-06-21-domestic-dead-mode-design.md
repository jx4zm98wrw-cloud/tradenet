# Domestic "Dead Mode" — Adaptive Max-Throughput Sweep (Design)

**Status:** Approved for planning · 2026-06-21

**Goal:** Add a "Dead mode" to the domestic (NOIP) enrichment sweep that gathers data as fast as the source will sustain — **max sustainable throughput** — by self-tuning concurrency on the existing single clean IP, while never tripping a hard ban that would end the run.

## Framing decisions (settled in brainstorming)

- **Objective = max *sustainable* throughput.** "Gather as much as possible" ⇒ maximize `rate × time`. A hard ban sets `time → 0`, so the design rides NOIP's tolerance ceiling rather than ignoring it. Literal "regardless of consequences" was rejected as self-defeating.
- **Single clean IP only.** No proxy pool. Free anonymizing proxies were rejected: they would route **authoritative** trademark HTML through untrusted intermediaries (data-integrity risk — they can alter responses), they re-break NOIP's already-patched TLS chain, they're ~90% dead/slow (net slower), and rotating IPs to multiply total load on an already-near-capacity government cluster is the opposite of "sustainable." Paid datacenter IPs the operator controls remain a possible future lever, out of scope here.
- **Self-tuning (AIMD), not a fixed preset.** An adaptive controller auto-finds and holds the ceiling and re-adapts as NOIP's load varies (day/night).
- **Reuse the proven sync client.** Concurrency is added via a thread pool around the existing `domestic_enrich.client.fetch_raw` (keeps the committed Sectigo CA bundle, retry, `Retry-After`, `NoipBlockedError` block-detection, and caching unchanged). No async/httpx rewrite.

## Architecture

A `mode` field on `domestic_sweep_control` selects the chunk's execution path:

- **`mode='normal'` (default):** the chunk runs exactly as today — sequential, one mark at a time, `delay`/`jitter`-paced. Unchanged behavior.
- **`mode='dead'`:** the chunk runs an **adaptive concurrent fetcher** — a bounded thread pool whose active size is governed by an AIMD controller, with near-zero per-mark delay (concurrency *is* the throttle).

Both paths share: the same work-list (`iter_domestic_appnos` minus cached), the same `enrich_one` (fetch → parse → store), the same per-item live control re-read (pause/stop/mode honored mid-chunk), the same self-re-enqueue chain, and the same `domestic` queue / single `worker-domestic`.

## The AIMD controller (the heart)

Models TCP congestion control over a rolling window of recent fetch outcomes. Implemented as a **pure function** `next_concurrency(current, window_stats) -> int` for testability, plus a thin runtime that feeds it outcomes.

Each fetch is classified into one outcome:
- **SUCCESS** — HTTP 200 + valid body.
- **FLAKY_FAIL** — exhausted all retries (`RuntimeError` from `fetch_raw`); the flaky-cluster case.
- **BLOCK** — `NoipBlockedError` (403/429).

Evaluated once per **window** (default `window_size = 20` completed fetches):

| Condition (over the window) | Action |
|---|---|
| `BLOCK` count > 0 | **Multiplicative decrease:** `concurrency = max(floor, concurrency // 2)` + a **cooldown** (hold, default 30s) before probing up again |
| no BLOCK, success-rate < `degrade_threshold` (default 0.70) | **Mild decrease:** `concurrency = max(floor, concurrency - 1)` (treat a flaky spike as congestion) |
| no BLOCK, success-rate ≥ `probe_threshold` (default 0.95) | **Additive increase:** `concurrency = min(ceiling, concurrency + 1)` (probe for headroom) |
| otherwise | hold |

- **Bounds:** `floor = 1`, `ceiling` configurable (default **6**; a single flaky cluster won't sustain much more). `start = 2`.
- It naturally settles at the fastest rate NOIP tolerates and re-probes upward when conditions improve.

## Safety valve & guardrails

- **Single block → survive, don't stop:** back off (halve) + cooldown, keep going at the safer rate. Dead mode's job is to find the safe ceiling, not to quit at the first 429.
- **Sustained blocks → auto-revert + pause (hard stop):** if `consecutive_block_windows ≥ block_giveup` (default 3) — i.e., even at reduced concurrency NOIP keeps blocking — set `mode='normal'`, `status='paused'`, and a clear `last_error` ("dead mode hit sustained NOIP blocks — reverted to normal + paused; cool down"). This is the runaway backstop.
- **Hard ceiling** on concurrency (config constant) — Dead mode can never exceed it regardless of how well things go.
- **Operator kill-switch:** flipping the toggle off (or Stop/Pause) is honored within ~1 item (the chunk re-reads `mode`/`status` per mark), reverting to the sequential path.
- **Per-fetch protections unchanged:** `NoipBlockedError` on 403/429, `Retry-After` honoring, and the (low, 8s-capped) retry backoff all remain inside `fetch_raw`.

## Schema (Alembic migration)

Add to `domestic_sweep_control`:
- `mode TEXT NOT NULL DEFAULT 'normal'` + `CHECK (mode IN ('normal','dead'))`.
- `concurrency INTEGER NOT NULL DEFAULT 0` — the controller's current active level, written each window so the panel can display it live (0 when normal/idle).

(Counters `processed`/`ok`/`failed` already exist and are reused; success-rate is shown from their deltas. No new table.)

## Control surface

- **Backend:** extend `api/routes/domestic_sweep.py` so `start`/`config` accept `mode`, and a `PATCH .../mode` (or reuse `config`) flips `mode` live. `SweepControlOut` gains `mode` + `concurrency`.
- **Frontend (`/admin/domestic`):** a **"Dead mode"** toggle (with a one-line "max-throughput; auto-throttles, auto-reverts on sustained blocks" caption) + live readouts: current **concurrency**, rolling **success rate**, and **req/s** (derived from `processed` delta over time). Flip on → watch it ramp; flip off → reverts to safe cadence.

## Components / files

| File | Responsibility |
|---|---|
| `app/backend/domestic_enrich/aimd.py` (new) | Pure `next_concurrency()` controller + outcome classification + bounds/cooldown/giveup constants. |
| `app/backend/worker/domestic_sweep.py` | Branch on `mode`; `_run_dead_chunk()` — bounded `ThreadPoolExecutor` around `enrich_one`/`fetch_raw`, feeding outcomes to the controller, honoring live `mode`/`status`, writing `concurrency`. |
| `app/backend/api/db/models.py` + Alembic migration | `mode` + `concurrency` columns. |
| `app/backend/api/routes/domestic_sweep.py` | Accept/return `mode`; live mode flip. |
| `app/frontend/app/(app)/admin/domestic/page.tsx` + `lib/api.ts` | Dead-mode toggle + live readouts. |
| Tests | AIMD unit tests; dead-chunk concurrency test (stubbed transport); block→backoff→giveup; mode toggle endpoint; live `mode`/`status` honored mid-chunk. |

## Error handling

- A worker crash mid-dead-chunk is covered by the existing boot auto-resume (#72) — it re-enqueues a chunk; `mode` persists in the control row, so it resumes in dead mode.
- Thread-pool exceptions per mark are isolated (one bad mark can't kill the chunk), same as today's per-mark `try/except`.
- **DB access from the pool (critical):** asyncpg connections are event-loop/thread-bound (see the #73 boot-resume fix). The dead chunk must NOT share one async session across worker threads. The plan should either (a) have each thread run a fully self-contained `enrich_one` on its own event loop + session and return an outcome, or (b) keep fetch (sync, thread-safe `requests`) in the threads and do all DB writes from the single owning coroutine after each batch. Decide in the plan; prefer (b) for simplicity and to keep one writer.

## Testing

- **Controller (pure):** increase on healthy window, mild-decrease on flaky window, halve+cooldown on block window, floor/ceiling clamping, sustained-block → giveup signal.
- **Dead chunk:** stubbed transport with tunable success/flaky/block mix → asserts concurrency ramps then holds; a block stream → asserts backoff then auto-revert+pause; `mode` flipped to normal mid-run → asserts it stops the concurrent path.
- **Endpoint:** `start`/flip set `mode`; `SweepControlOut` carries `mode`/`concurrency`; 409 guards unchanged.

## Non-goals

- No proxy pool / multiple egress IPs (data-integrity + scope). No async/httpx rewrite. Dead mode is **domestic-only** (the madrid sweep keeps the sequential path; the controller is reusable later if wanted). No change to the parser/store/derive. Not a fixed preset — adaptive only.

## Standing constraints (carry over)

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` by explicit path.
- GateGuard fact-forcing on first Edit/Write per file + first Bash.
- Backend CI gates: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`; frontend: `pnpm lint && pnpm build` (typecheck via build — don't `pnpm build` against a live `pnpm dev`; use `tsc --noEmit`). Run the backend suite cautiously — the sweep tests reset the live `domestic_sweep_control` singleton against the dev DB.
- One worker per sweep queue (recommended topology) — dead mode assumes a single `worker-domestic`.

## Rollout / suggested PR sequence

1. **AIMD controller** (`aimd.py`) + unit tests — pure, no integration.
2. **Schema** (`mode`/`concurrency` columns + migration) + model.
3. **Dead chunk** in `domestic_sweep.py` (thread pool + controller wiring + safety valve) + tests.
4. **Control API** (`mode` in/out, live flip) + tests.
5. **Frontend** toggle + live readouts.

Each PR is independently green-able; 1–4 are backend, 5 is frontend.
