# Madrid Rate-Aware Fast Mode (Design)

**Status:** Approved for planning · 2026-06-23 · companion to the domestic "Dead mode" (`2026-06-21-domestic-dead-mode-design.md`)

**Goal:** Give the Madrid (WIPO Madrid Monitor) sweep an opt-in high-throughput mode that paces to WIPO's **published** rate limit instead of WIPO-probing for a ban — "a dead mode, but less brute force."

## Why Madrid is different from domestic (the key insight)

Domestic "Dead mode" is brute force **by necessity**: NOIP publishes no rate limit and fronts a flaky cluster, so the only way to find its ceiling is empirically — `domestic_enrich/dead_mode/controller.py` runs an **AIMD** loop (TCP-congestion style: additive-increase concurrency while healthy, multiplicative-decrease on a block) over a thread pool, *probing for bans*.

WIPO hands you the budget instead. A live header probe (2026-06-23) of `https://www3.wipo.int/madrid/monitor/en/showData.jsp?ID=ROM.{irn}` returns:

```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 1000      # still full mid-"running" sweep — today's 0.5 req/s leaves huge headroom
X-RateLimit-Reset: -1782179894   # garbage (negative) — UNUSABLE for window timing
```

So the fast mode **paces to a given ceiling rather than searching for one** — simpler than AIMD. Two hard facts shape it:
1. **Pace off `X-RateLimit-Remaining`, never off `Reset`.** The Reset header is unreliable (negative), so we cannot compute the window boundary; we keep `Remaining` above a safety floor and let it recover by observation.
2. **Budget is `Limit` (1000) per (unknown-length) window.** Don't hardcode 1000 — read `X-RateLimit-Limit` live so a WIPO change is picked up automatically.

## Architecture (mirrors domestic Dead mode)

One self-contained package + one delegating branch, identical in shape to `dead_mode/`:

- **Schema:** migration adds a `mode` text column (default `'normal'`) and a `concurrency` int column to `madrid_sweep_control` (it currently has neither — domestic already has both).
- **Delegation:** `worker/madrid_sweep.run_chunk` gains one `if ctl["mode"] == "fast":` branch that lazy-imports and delegates the whole chunk to `madrid_enrich.fast_mode.run_chunk` (one-way dependency, no cycle). Normal sequential mode is untouched.
- **Package `madrid_enrich/fast_mode/`:** `__init__.py` (public surface), `controller.py` (pure rate-feedback), `runner.py` (threaded fetch / coroutine store).

### `controller.py` — pure rate-feedback (no I/O)

Not AIMD. A feedback loop keyed on `X-RateLimit-Remaining`, sized as a fraction of `X-RateLimit-Limit`:

- Inputs (last window): observed `remaining`, `limit`, whether a 429/throttle occurred, current concurrency.
- Floor = `max(FLOOR_ABS, FLOOR_FRAC * limit)` (e.g. `FLOOR_FRAC = 0.15` → 150 of 1000).
- Decision (priority order):
  1. **429 / throttle** → `paused = True` (runner sleeps the Retry-After, then re-probes). Dominates.
  2. **`remaining <= floor`** → step concurrency **down** (`current - 1`, min 1) AND signal a brief cool-down.
  3. **`remaining >= HEALTHY_FRAC * limit`** (e.g. 0.5 → 500) → step concurrency **up** (`current + 1`, max `CEILING`, e.g. 6).
  4. otherwise hold.
- Bounds: floor concurrency 1, ceiling small (≈6) — concurrency exists only to saturate WIPO's ~2 s round-trips, not to find a ceiling.

Pure and table-test-friendly, exactly like `dead_mode/controller.next_concurrency`.

### `runner.py` — threaded fetcher (proven domestic shape)

Reuse the domestic dead-mode runner shape verbatim where it fits: a small `ThreadPoolExecutor` of fetch workers, **one event loop per thread** so asyncpg connections are never shared across threads; fetch on threads, store via coroutines. Each worker calls `madrid_enrich.enrich_one`. Between windows it calls `controller` with the window's observed `remaining`/`limit` and applies the new concurrency target. Honors live `madrid_sweep_control` edits (status pause/stop, cap) each window, same as the normal chunk loop.

### `madrid_enrich/client.py` — finish "Plan 2" (serves both modes)

The client already reads `X-RateLimit-Remaining`. Add:
- Surface `X-RateLimit-Limit` on `FetchResult` (alongside the existing `rate_remaining`).
- **Act on throttling:** on HTTP 429 (or a `Retry-After` header), raise a new `WipoThrottledError(retry_after)` — distinct from a generic fetch failure — so the runner pauses for the stated seconds instead of hammering. This mirrors `domestic_enrich.client.NoipBlockedError`.

## Convergence / safety

- **No undocumented daily-cap guessing.** If `Remaining` stops recovering or WIPO 429s persistently, the controller parks the sweep `paused` (operator resumes later) — the same graceful-stop posture as dead mode on a block. An undocumented daily cap is handled by this path without needing to know its value.
- **Cache semantics unchanged.** Fetch-once, cached HTML, re-derive offline via `parse_version` (never interrupt a running sweep to apply parser changes — see the Madrid sweep memory). Fast mode only changes *fetch concurrency/pacing*, not what is fetched or stored.
- **Auto-revert?** No. Unlike dead mode (which auto-reverts to normal + pauses on sustained NOIP blocks because NOIP bans are opaque), WIPO throttling is explicit and recoverable, so fast mode throttles down / pauses-on-floor and stays in fast mode; the operator decides when to switch back.

## UI

A `mode` / `concurrency` control row on `/admin/madrid`, identical to the domestic ops panel's dead-mode toggle: enable fast mode, show live concurrency + `rate: Remaining/Limit · req/s`. The admin sweep endpoint accepts `mode` in its tune payload (mirrors `/admin/domestic-sweep`).

## Components & boundaries

| Unit | Responsibility | Depends on |
|---|---|---|
| `madrid_sweep_control.mode/concurrency` (migration) | persisted mode + live concurrency | — |
| `worker/madrid_sweep.run_chunk` (1 branch) | delegate when `mode=='fast'` | `fast_mode` (lazy) |
| `fast_mode/controller.py` | pure: next concurrency from rate headers | — |
| `fast_mode/runner.py` | threaded fetch + coroutine store, applies controller | `controller`, `madrid_enrich.enrich_one`, client |
| `madrid_enrich/client.py` | surface limit/remaining; raise on 429/Retry-After | — |
| `/admin/madrid` + sweep endpoint | toggle mode/concurrency, show rate | control row |

## Testing

- `controller` (pure): `remaining ≥ healthy → concurrency up`; `remaining ≤ floor → down + cooldown`; `429 → paused` dominates; bounds clamp at floor 1 / ceiling. Floor/healthy derived from `limit`, not hardcoded.
- `client`: a 429 (and a `Retry-After`) raises `WipoThrottledError(retry_after)`; a 200 surfaces `limit` + `remaining`.
- `run_chunk` delegates to `fast_mode` when `mode=='fast'` and to the normal loop otherwise (monkeypatch the fast runner).
- Targeted pytest only — sweep tests reset the live `madrid_sweep_control` singleton.

## Non-goals

- No AIMD / congestion probing (WIPO publishes the limit). No change to what is fetched, parsed, or stored. No change to the normal sequential mode's behavior. No auto-revert. No new reference data. No reliance on `X-RateLimit-Reset` (unusable).

## Standing constraints

- NEVER commit the rename trio (`README.md`, `app/.env.example`, `app/backend/api/settings.py`); `git add` explicit paths.
- Backend CI: `ruff check . && ruff format --check . && mypy api worker && alembic check && pytest`. This adds a migration (`alembic check` will require it).
- Never interrupt the running Madrid sweep to deploy — the sweep is fetch-once/cached; coordinate a pause or deploy to `worker-madrid` when idle.
- Frontend: never `pnpm build` while `pnpm dev` is live — `tsc --noEmit` + `pnpm lint`.

## Decomposition (for the plan)

1. **Client** (small): `WipoThrottledError` + 429/Retry-After handling + surface `X-RateLimit-Limit` on `FetchResult`. Tests.
2. **Migration**: `madrid_sweep_control.mode` (default `'normal'`) + `concurrency`.
3. **`fast_mode/controller.py`** (pure) + tests.
4. **`fast_mode/runner.py`** + the `run_chunk` delegating branch.
5. **API + `/admin/madrid` UI**: mode/concurrency toggle + rate display.
