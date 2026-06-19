# Madrid Sweep Control module (Design)

**Status:** Approved for planning · 2026-06-19

**Goal:** Let an admin **start, pause, resume, stop, and tune** the Madrid (WIPO)
enrichment sweep from the `/admin/madrid` page — replacing the hand-launched
`/tmp` resume script with a proper, controllable RQ job whose live state is
visible in the UI.

## Background

The enrichment sweep currently runs as a detached `/tmp/madrid_resume.py` script
launched by hand: the web app can neither start it, stop it, nor see it. The
project already runs an **RQ worker** (`worker/run_worker.py` → Redis queue
`ingest`) and the real engine is `madrid_enrich` (`enrich_one`, `run_backfill`,
`iter_madrid_irns`). This module turns the sweep into an RQ job controlled via a
DB state row and admin endpoints. (The `/admin/madrid` enrichment-progress panel
listed UI sweep-control as an explicit non-goal — this is its dedicated design.)

## Architecture: RQ job + DB control row (execution model A)

Chosen over a FastAPI-managed subprocess (fragile, breaks under multi-worker /
restart) and a single long polling job (a paused job holds the worker slot and
blocks `ingest`). The chunked self-re-enqueuing job makes pause/resume trivial
and never blocks the ingest queue.

### 1. State — `madrid_sweep_control` (singleton table)

One source of truth, read by the panel and written by the job. Survives Redis
flush and API restarts. Singleton enforced by a fixed primary key (`id = 1`).

| column | type | meaning |
|---|---|---|
| `id` | int PK | always 1 (singleton) |
| `status` | text | `idle` · `running` · `paused` · `stopping` |
| `cap` | int null | target IRNs for this run (null = all remaining) |
| `delay` | float | seconds between fetches (default 8.0) |
| `jitter` | float | added random 0..jitter seconds (default 2.0) |
| `chunk_size` | int | IRNs processed per RQ chunk (default 25) |
| `processed` | int | IRNs attempted this run |
| `ok` | int | successful fetches this run |
| `failed` | int | failed fetches this run |
| `current_irn` | text null | IRN in flight |
| `last_error` | text null | most recent failure detail |
| `started_at` | timestamptz null | when the current run started |
| `updated_at` | timestamptz | heartbeat — bumped each chunk/IRN |

One Alembic migration creates the table and seeds the singleton row
(`id=1, status='idle'`, default cadence). Status is stored as text with a
CHECK constraint on the four values (matches the project's existing enum-as-text
style for `mark_category`).

### 2. Job — `worker/madrid_sweep.py`

`run_sweep_chunk()` (the RQ task):

1. Open a sync DB session; load the control row.
2. If `status != 'running'` → return immediately (paused / stopping / idle).
3. Build the work-list: `iter_madrid_irns()` minus cached HTML minus already-done,
   honoring `cap` (stop when `processed >= cap`).
4. Process up to `chunk_size` IRNs. For **each** IRN:
   - Re-read the control row's `status`, `delay`, `jitter` (so pause/stop land
     within ~1 IRN and cadence edits apply live).
   - If `status != 'running'` → break out (pause/stop honored mid-chunk).
   - `enrich_one(...)`; on success bump `ok`, reset the consecutive-failure
     streak; on failure bump `failed` + `last_error`, increment streak.
   - **Circuit breaker:** 5 consecutive failures → set `status='paused'` +
     `last_error`, break (a WIPO 403 block becomes visible and resumable, not a
     silent hard halt).
   - Bump `processed`, set `current_irn`, `updated_at`; `sleep(delay + rand*jitter)`.
5. After the chunk: reload `status`. If still `running` and work remains and
   `cap` not hit → re-enqueue `run_sweep_chunk` on the `madrid` queue. Otherwise
   set `status='idle'` (run complete) or leave `paused`. If `status=='stopping'`,
   set `idle`.

The job uses the **sync** DB engine (`TM_DATABASE_URL_SYNC`) like the rest of the
worker, and the existing `enrich_one` (which already does cache-skip + upsert).

### 3. Control API — `api/routes/madrid_sweep.py` (all `require_admin`)

A new router (keeps `admin.py` focused). Mounted in `api/main.py`.

- `GET  /api/v1/admin/madrid-sweep` → the control row (status, cadence, counters,
  `current_irn`, `last_error`, `started_at`, `updated_at`).
- `POST /api/v1/admin/madrid-sweep/start` body `{cap?, delay?, jitter?, chunk_size?}`
  → only if `idle`; reset counters, apply any cadence overrides, `started_at=now`,
  `status='running'`, enqueue first chunk. **409** if not `idle`.
- `POST /api/v1/admin/madrid-sweep/pause` → `running`→`paused`. **409** otherwise.
- `POST /api/v1/admin/madrid-sweep/resume` → `paused`→`running`, enqueue next
  chunk. **409** otherwise.
- `POST /api/v1/admin/madrid-sweep/stop` → from `running`/`paused` → `stopping`
  (the job converts it to `idle` at its next status check; if no job is in
  flight, the endpoint sets `idle` directly). **409** from `idle`.
- `PATCH /api/v1/admin/madrid-sweep/config` body `{delay?, jitter?, cap?, chunk_size?}`
  → update cadence in any state; the running job picks it up on the next IRN.

Enqueueing uses `rq.Queue("madrid", connection=Redis.from_url(settings.redis_url))`.

### 4. Frontend — extend `/admin/madrid`

A **Sweep control** card above the existing stats:
- Status badge (`idle`/`running`/`paused`/`stopping`) with a pulse dot when active.
- Buttons enabled per state: **Start** (idle), **Pause** (running), **Resume**
  (paused), **Stop** (running/paused).
- Editable cadence inputs (`cap`, `delay`, `jitter`, `chunk_size`) + **Apply**
  → `PATCH .../config`.
- Live this-run detail: `processed · ok · failed`, `current_irn`, `last_error`.
- Polls `GET /madrid-sweep` every 3s (alongside the existing stats poll).

New `lib/api.ts`: `MadridSweepControl` type + methods `madridSweepStatus`,
`madridSweepStart`, `madridSweepPause`, `madridSweepResume`, `madridSweepStop`,
`madridSweepConfig`.

### 5. Worker + cutover

`worker/run_worker.py` listens on `Queue("ingest")` **and `Queue("madrid")`**.
Docs (`CLAUDE.md`, `app/README.md`) note the worker must be running for sweep
control to function (`python -m worker.run_worker`). **Cutover:** stop the
hand-launched `/tmp/madrid_resume.py` sweep before first use — two sweeps would
double-fetch the same IRNs.

## Data flow

```
admin page → POST /madrid-sweep/start → control row status=running + enqueue chunk
RQ worker  → run_sweep_chunk → enrich_one × chunk_size, updates control row
           → re-enqueue if still running
admin page → GET /madrid-sweep (3s poll) → live status + counters
admin page → POST /pause|/resume|/stop, PATCH /config → state transitions
```

## Error handling

- **Bad state transition** (e.g. start while running, resume while idle) → **409
  Conflict** with a clear message.
- **Non-admin** → 403 (require_admin); unauthenticated → 401.
- **WIPO 403 block** → circuit breaker pauses the run (`status='paused'`,
  `last_error` set), resumable once the rate window clears.
- **Worker down:** the job never executes, so `status` stays `running` while
  `updated_at` goes stale. The panel warns "running, but no progress — is the
  worker up?" when `status=='running'` and `updated_at` is older than ~60s.

## Testing

Backend (pytest + httpx/ASGI):
- **Endpoints:** start→`running` (+counters reset, `started_at` set); pause→`paused`;
  resume→`running`; stop→`stopping`/`idle`; PATCH config updates cadence; **409**
  on each illegal transition; **403** for a non-admin (`viewer_client`).
- **Job:** call `run_sweep_chunk` directly against seeded Madrid IRNs with
  `enrich_one` monkeypatched (no live WIPO/worker). Assert it processes up to
  `chunk_size`, updates `ok`/`processed`, **honors a mid-chunk pause** (flip the
  row to `paused` → loop exits), sets `paused` after 5 monkeypatched consecutive
  failures, and **re-enqueues** when still `running` (enqueue stubbed/recorded).
- Enqueue is stubbed in tests (assert it was called with `run_sweep_chunk` on the
  `madrid` queue) so tests need no running worker.

## Non-goals

- **Multiple concurrent sweeps** — singleton control row; one sweep at a time.
- **Scheduling** (cron-style auto-start) — manual start only; revisit later.
- **Per-IRN retry policy / re-derive control** — the offline re-derive
  (`parse_version` bump) stays a separate operator action.
- **Replacing the coverage counts** — `/madrid-enrichment` (unique/validated/
  remaining) stays as-is; this adds process control beside it.

## Out-of-scope follow-ups (noted)

- Auto-start the worker in dev (`docker-compose` service) so sweep control works
  without a manually-run worker.
- A scheduled nightly sweep (cron) once the manual controls are proven.
