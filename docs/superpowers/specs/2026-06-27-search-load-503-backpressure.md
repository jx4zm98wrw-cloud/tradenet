# Search API 5xx-storm under concurrency — root cause + graceful-backpressure fix

**Date:** 2026-06-27
**Status:** fix implemented (errors.py 503 backpressure); capacity recommendations open
**Endpoint:** `GET /api/v1/search/trademarks`

## Finding (load test)

The tnqa stress harness drove the search endpoint at rising concurrency against
an unthrottled local instance (`TM_RATE_LIMIT_DEFAULT=100000000/minute`):

| concurrency | p95 | errors |
|---|---|---|
| 10 | 2.8s | 0 |
| 25 | 5.3s | 0 (p95 crosses SLO) |
| 50 | 10s | 0 |
| **100** | — | **~92% HTTP 5xx + conn-resets** |
| 1000 | — | ~86% HTTP 5xx |

Throughput plateaus at **~9 rps** regardless of concurrency. Above ~50
concurrent connections the service collapses into a 5xx-storm instead of
queueing / backpressuring.

## Root cause (proven, not guessed)

**There is no admission control / backpressure.** When the DB layer saturates,
the driver/pool exception propagates unhandled and FastAPI's catch-all
`@app.exception_handler(Exception)` ([api/errors.py](../../../app/backend/api/errors.py))
maps it to a blank **HTTP 500**. The saturation exception is operational
("at capacity, retry"), not a bug — but it's served as a 500.

The exact exception depends on the pool strategy
([api/db/session.py](../../../app/backend/api/db/session.py)), and **both were
reproduced end-to-end** with the actual server-side traceback captured:

### Path A — test/dev (`TM_ENV ∈ {test,testing,ci}` → NullPool) — what the harness measured
- NullPool opens a **fresh asyncpg connection per request** (no upper bound).
- Postgres `max_connections = 100`; the three RQ workers (+ pools) already hold
  ~74 connections, leaving **~26 free slots**.
- At concurrency 100, the search handler's first DB I/O
  ([search.py:339](../../../app/backend/api/routes/search.py) `await session.execute(...)`)
  tries to open a new connection and Postgres refuses:

  ```
  asyncpg.exceptions.TooManyConnectionsError: sorry, too many clients already
    File ".../api/routes/search.py", line 339, in search_trademarks
    File ".../asyncpg/connect_utils.py", line 1054, in _connect_addr
  ```
  → propagates unhandled → **HTTP 500**. Measured: conc 100 → **501× 500 + 293
  connection resets**, only 206/1000 OK.

### Path B — production (`TM_ENV` default/staging/prod → QueuePool 20+10=30)
- Pool is bounded (30), so Postgres's ceiling is not hit by this one service,
  but there is still no backpressure: 70 of 100 requests wait for a pool slot.
- Heavy GIN-trgm search queries over ~238k rows hold a slot ~1–5s, so the queue
  cannot drain; requests waiting past `pool_timeout` (SQLAlchemy default 30s)
  raise:

  ```
  sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 10 reached,
  connection timed out, timeout 30.00
  ```
  → propagates unhandled → **HTTP 500**. Measured: conc 100 → 18× 500, 981 OK,
  **rps 9.3** (reproduces the reported ~9 rps plateau exactly).

### Why throughput caps at ~9 rps
Throughput ≈ `usable_connections ÷ mean_query_time`. On the production
QueuePool that is `30 ÷ ~3s ≈ 10 q/s`. Adding concurrency beyond that does not
add throughput — it just lengthens the queue until requests time out (Path B)
or exhausts Postgres slots (Path A). **9 rps is a DB-capacity ceiling, not a
fixable bug.** The bug is that exceeding it returns 500s instead of degrading
gracefully.

## Fix implemented — smallest change that converts the storm into graceful degradation

`register_exception_handlers` ([api/errors.py](../../../app/backend/api/errors.py))
now registers handlers for the two saturation classes (and the defensive
`OperationalError(orig=TooManyConnectionsError)` wrap), returning
**HTTP 503 + `Retry-After`** via the standard error envelope
(`code="service_unavailable"`). Registering specific-class handlers takes
precedence over the bare-`Exception` handler (Starlette matches by closest MRO
type). Real bugs still map to 500 (regression-guarded by the test).

**Verified end-to-end** (same concurrency-100 load, instance running the fix):

| path | before | after |
|---|---|---|
| NullPool (A) | 501× **500** + 293 conn-resets | **704× 503**, 296 OK, **0 conn-resets** |
| QueuePool (B) | 18× **500** | **10× 503**, 990 OK, **0× 500** |

Capacity (~9 rps) is unchanged by design — the fix corrects the *failure mode*,
not capacity.

### Known interaction — Retry-After value
slowapi's `SlowAPIMiddleware` runs with `headers_enabled=True`
([api/rate_limit.py](../../../app/backend/api/rate_limit.py)) and **overwrites**
the handler's `Retry-After: 1` with its fixed-window reset delta (observed
`Retry-After: 57`, alongside injected `X-RateLimit-*` headers). The 503 *status*
is the handler's; the *value* is slowapi's. Clients still get a valid (if
conservative) backoff hint. If a tighter saturation-specific Retry-After is
wanted, special-case 503s or set `headers_enabled=False` — deferred as a
follow-up, not required for graceful degradation.

## Recommendations (prioritized)

1. **[DONE] 503 + Retry-After backpressure** — converts the 5xx-storm into
   honest degradation. Engine/pool-agnostic; schema-free.
2. **Bound total connections ≤ `max_connections`.** Latent prod risk: workers
   (~74) + API QueuePool (30) = **104 > 100**. Either raise Postgres
   `max_connections`, shrink/coordinate pools, or **front Postgres with
   pgbouncer** (transaction pooling) so the API's 30-slot pool multiplexes onto
   far fewer real backends. Highest-value capacity fix; infra-level, needs human
   review.
3. **Keep `statement_timeout` (already 30s)** so a runaway query holds a slot
   for ≤30s. Consider a lower per-search timeout (e.g. 5–10s) so saturation
   clears faster and Retry-After means what it says.
4. **NullPool is serving-unsafe** — it is only used in tests for the asyncpg
   cross-event-loop constraint. Never run a real serving instance with
   `TM_ENV ∈ {test,testing,ci}`; the unbounded-connection behavior is the
   Path-A storm.

## Reproduce

```bash
docker compose -f app/docker-compose.yml up -d
cd app/backend
TM_ENV=test TM_RATE_LIMIT_DEFAULT=100000000/minute \
TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \
TM_REDIS_URL=redis://localhost:6380/0 \
uvicorn api.main:app --port 8001          # foreground → captures 5xx tracebacks
# drive load at concurrency 100 (hey / tnqa stress / async loop) and read the log
```

Test: `tests/test_db_saturation_backpressure.py`.
