# Domestic "Dead Mode" — Adaptive Max-Throughput Sweep (Design)

**Status:** Approved for planning · 2026-06-21

**Goal:** Add a "Dead mode" to the domestic (NOIP) enrichment sweep that gathers data as fast as the source will sustain — **max sustainable throughput** — by self-tuning concurrency on the existing single clean IP, while never tripping a hard ban that would end the run.

## Framing decisions (settled in brainstorming)

- **Objective = max *sustainable* throughput.** "Gather as much as possible" ⇒ maximize `rate × time`. A hard ban sets `time → 0`, so the design rides NOIP's tolerance ceiling rather than ignoring it. Literal "regardless of consequences" was rejected as self-defeating.
- **Single clean IP only.** No proxy pool. Free anonymizing proxies were rejected: they would route **authoritative** trademark HTML through untrusted intermediaries (data-integrity risk — they can alter responses), they re-break NOIP's already-patched TLS chain, they're ~90% dead/slow (net slower), and rotating IPs to multiply total load on an already-near-capacity government cluster is the opposite of "sustainable." Paid datacenter IPs the operator controls remain a possible future lever, out of scope here.
- **Self-tuning (AIMD), not a fixed preset.** An adaptive controller auto-finds and holds the ceiling and re-adapts as NOIP's load varies (day/night).
- **Reuse the proven sync client.** Concurrency is added via a thread pool around the existing `domestic_enrich.client.fetch_raw` (keeps the committed Sectigo CA bundle, retry, `Retry-After`, `NoipBlockedError` block-detection, and caching unchanged). No async/httpx rewrite.

## Architecture

**Dead mode is a self-contained package — `domestic_enrich/dead_mode/` — that the existing sweep merely *delegates* to.** The proven normal sweep stays as-is; its only awareness of dead mode is a single one-line branch.

A `mode` field on `domestic_sweep_control` selects the chunk's execution path:

- **`mode='normal'` (default):** `worker/domestic_sweep.run_chunk` runs exactly as today — sequential, one mark at a time, `delay`/`jitter`-paced. Unchanged behavior.
- **`mode='dead'`:** after its status check, `run_chunk` delegates the entire chunk to `dead_mode.run_chunk(...)` — the package's **adaptive concurrent fetcher**: a bounded thread pool whose active size is governed by the AIMD controller, near-zero per-mark delay (concurrency *is* the throttle).

### Module boundary (the "independent module" requirement)

- **`domestic_enrich/dead_mode/`** owns everything dead-mode-specific: the AIMD controller, the concurrent runner, the safety valve, and its own tests. Public surface is a single entry point `dead_mode.run_chunk(session, *, enqueue_next, http_session=None) -> dict` (plus the `DEAD` mode constant).
- **One-way dependency:** `worker/domestic_sweep.py` → `dead_mode` (via a lazy import inside the `if mode=='dead'` branch, to avoid any import cycle). `dead_mode` **never** imports from `worker.domestic_sweep`. It reuses the shared primitives *directly* — `iter_domestic_appnos` (backfill), `enrich_one`/`fetch_raw` (enrich/client), `appno_to_vnid` (idmap), `DomesticSweepControl` (models) — so there's no cycle and no duplication of the work-list/fetch machinery. It does its own control-row read/write (it needs to anyway: it writes `concurrency` and performs the auto-revert).
- **Removability:** delete the `dead_mode/` package + the one delegation branch + the two schema columns ⇒ the normal sweep is byte-for-byte its old self.
- **The PR-1 controller (`domestic_enrich/aimd.py`) relocates into the package** as `dead_mode/controller.py` (nothing imports it yet, so the `git mv` + test-import update is clean).

Both paths still share: the same work-list (`iter_domestic_appnos` minus cached), the same `enrich_one` (fetch → parse → store), the same per-item live control re-read (pause/stop/mode honored mid-chunk), the same self-re-enqueue chain, and the same `domestic` queue / single `worker-domestic`.

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
| `app/backend/domestic_enrich/dead_mode/__init__.py` (new) | Package public API: re-export `run_chunk` + the `DEAD` mode constant. |
| `app/backend/domestic_enrich/dead_mode/controller.py` (moved from `aimd.py`) | Pure AIMD controller: `next_concurrency()` + `should_give_up()` + `Outcome`/`WindowStats`/`Decision` + constants. |
| `app/backend/domestic_enrich/dead_mode/runner.py` (new) | `run_chunk(session, *, enqueue_next, http_session=None)` — bounded `ThreadPoolExecutor` around `enrich_one`/`fetch_raw`, feeds per-fetch `Outcome`s to the controller window, applies `Decision` (concurrency + cooldown), honors live `mode`/`status`, writes `concurrency`, and does the sustained-block auto-revert+pause. Imports shared primitives directly (no `worker.domestic_sweep` import). |
| `app/backend/worker/domestic_sweep.py` | **One change only:** `if ctl["mode"] == "dead": return await dead_mode.run_chunk(...)` (lazy import). Normal path untouched. |
| `app/backend/api/db/models.py` + Alembic migration | `mode` + `concurrency` columns on `domestic_sweep_control`. |
| `app/backend/api/routes/domestic_sweep.py` | Accept/return `mode`; live mode flip. |
| `app/frontend/app/(app)/admin/domestic/page.tsx` + `lib/api.ts` | Dead-mode toggle + live readouts. |
| `app/backend/tests/domestic_enrich/dead_mode/` | Controller unit tests (moved); runner tests: concurrency ramp (stubbed transport), block→backoff→giveup→revert+pause, live `mode`/`status` honored mid-chunk. |

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

1. **AIMD controller** — pure + unit tests. *(Shipped as `domestic_enrich/aimd.py`, PR #75.)*
2. **`dead_mode/` package + schema** — create the package: `git mv aimd.py → dead_mode/controller.py` (+ update its test import), add `__init__.py`, and add the `mode`/`concurrency` columns + migration + model. No runtime behavior yet. (Package skeleton + schema land together so the runner PR has a home + the columns.)
3. **Dead-chunk runner** (`dead_mode/runner.py`) — thread pool + controller wiring + safety valve + auto-revert; plus the **single delegation branch** in `worker/domestic_sweep.py`. + tests.
4. **Control API** (`mode` in/out, live flip) + tests.
5. **Frontend** toggle + live readouts.

Each PR is independently green-able; 1–4 are backend, 5 is frontend. The one-way `domestic_sweep → dead_mode` dependency (lazy import) keeps the normal sweep removable-clean.
