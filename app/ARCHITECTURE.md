# Architecture

```
                  ┌─────────────────────────────────────────────────────┐
                  │  Next.js 15 (App Router)  ·  Tailwind 3  ·  React 19 │
                  │   Today · Search · /marks/[id] · Compare · …         │
                  └────────────────────┬────────────────────────────────┘
                                       │  /api/v1/* (proxied via next rewrite)
                                       ▼
        ┌──────────────────────────────────────────────────────────────┐
        │                  FastAPI on uvicorn                          │
        │                                                              │
        │  Middleware:  RequestID → SlowAPI → CORS                     │
        │  Auth:        Depends(require_user) — stub user today        │
        │  Errors:      Consistent envelope w/ request_id              │
        │  Metrics:     /metrics (Prometheus)  +  Sentry init           │
        │  Logging:     structlog → JSON (prod) / console (dev TTY)    │
        │                                                              │
        │  Routers:    gazettes · trademarks · search · facets ·       │
        │              today · marks · compare · watchlists ·          │
        │              admin · stats                                   │
        └─────────┬─────────────────────────────────────┬──────────────┘
                  │ SQLAlchemy async                    │ enqueue
                  ▼                                     ▼
        ┌────────────────────┐              ┌────────────────────┐
        │   Postgres 16      │              │  Redis 7 (RQ)      │
        │   - gazettes       │              │  - ingest queue    │
        │   - trademarks     │              │  - slowapi storage │
        │   - watchlists     │              └─────────┬──────────┘
        └────────────────────┘                        │ work-horse fork
                                                      ▼
                                          ┌────────────────────────┐
                                          │  RQ worker             │
                                          │   worker.ingest.       │
                                          │   ingest_pdf()         │
                                          │      uses              │
                                          │   tm_extractor library │
                                          └────────────────────────┘
```

## Layers

### `tm_extractor/`
The PDF parser — completely separate from the API. Originally a single
1457-line `TM_csv_builder.py`; now modular: `processor.py` (the parsing state
machine), `applicant.py`, `text_processor.py`, `constants/` (WIPO markers,
country codes, classifier rules), `data_loaders.py` (cities/suffixes JSON).
The legacy CLI is preserved as `TM_csv_builder_legacy.py` at the repo root
for byte-identical reference output.

The image extractor lives separately at the repo root as
`Final_TRADEMARK_image_extractor_refine.py` (lazy-imported by
`worker/ingest.py` via a single `sys.path.insert`). It uses PyMuPDF for
blank-page removal + image-rect extraction and produces per-sector PNGs.

### `api/`
HTTP layer. Routes are thin — input validation via Pydantic, business logic
in `_filters.py` shared helpers, persistence via SQLAlchemy async session.

Key files:
- `main.py`         — app factory + middleware order + health/ready/metrics
- `settings.py`     — env-driven config (Pydantic Settings)
- `auth.py`         — `require_user` / `require_admin` / `optional_user`
- `errors.py`       — error envelope + `RequestIDMiddleware`
- `rate_limit.py`   — slowapi limiter (Redis-backed when available)
- `logging_config.py` — structlog setup with request-id context binding
- `db/`             — SQLAlchemy models + async session (NullPool — see below)
- `routes/_filters.py` — shared WHERE-clause builder for search + facets

### `worker/`
RQ ingest job. One file per concept:
- `ingest.py` — the job function `ingest_pdf(gazette_id)`
- `mapper.py` — section-dict → Trademark row mapping (also normalises
  Vietnamese country-code edge cases like `unknown` → NULL)
- `run_worker.py` — entry point with the macOS fork-safety guard

### `frontend/`
Standard App Router layout. Server components by default; client components
are gated behind `"use client"` (search filters, Cmd-K palette, drag-and-drop
upload). State management is local + URL — no Redux/Zustand.

Key files:
- `app/layout.tsx`            — fonts + nav + CmdKProvider
- `components/cmdk.tsx`       — ⌘K palette (live API search, recent-search localStorage)
- `components/specimen/`      — `MarkSpecimen` + placeholder treatment
- `lib/api.ts`                — typed API client; one method per backend route
- `lib/mark-display.ts`       — `markDisplay()` picks the best label

## Cross-cutting concerns

### Session pooling
`db/session.py` uses `NullPool` — one connection per request, closed on
release. This avoids "cannot perform operation: another operation in progress"
errors when asyncpg connections leak across event loops (test loops, ASGI
lifespan reloads). Trade-off: connection setup is ~5–15ms per request. Swap
to `pool_size` / `max_overflow` once a single durable loop owns the process
(e.g. one Gunicorn worker per pod).

### Async DB inside Alembic
Alembic uses the **sync** URL (`TM_DATABASE_URL_SYNC` via psycopg2) — runtime
uses asyncpg via `TM_DATABASE_URL`. They point at the same database; keep both
in sync.

### macOS RQ fork crash
pdfplumber pulls in Objective-C libraries; once those touch the runtime, the
parent process can't safely `fork()`. `worker/run_worker.py` sets
`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` when `sys.platform == "darwin"`.
Linux is unaffected.

### Mark specimens (placeholder vs. real)
Two sources fill the specimen frame, picked in order:
1. **Extracted logo PNG** — `Final_TRADEMARK_image_extractor_refine.py` carves
   per-sector PNGs into `image/<year>/<stem>/`, the worker's `_resolve_logo_path`
   probes `(210) → (111) → (116)` (plus Madrid letter-suffix variants) and
   writes the relative path to `trademarks.logo_path`. `_save_page_images`
   is label-aware: when clustering merges image rects across sector
   boundaries, it splits the merged image at interior marker y-positions.
2. **(540) wordmark text** — only B-files (registrations) carry it; A-files
   (applications) don't.

When both are missing (~0.015% of rows — gazette pages with no figurative
metadata AND no transcribed wordmark), `markDisplay(mark)` falls back to a
derived label from `applicant_name` with Vietnamese entity prefixes
stripped, and the specimen frame renders in a visibly-subdued placeholder
mode. Coverage on the 2026 gazette set: 99.985% combined, all 4 A-files at
100% combined.

### Similarity engine (the load-bearing TODO)
All scoring (phonetic, visual, class overlap, composite) flows through small
`_score_*()` functions in `routes/{search,today,marks,compare}.py`. Class
overlap is real (Jaccard); the others are deterministic per-id jitter. Real
implementation plugs in by replacing function bodies — UI contract stays the
same.

## Data flow per route

### Today
1. `/health/ready` confirms DB+Redis
2. Today page calls `/api/v1/today/digest`, `/findings`, `/opposition-windows`,
   `/watchlists`, `/stats/pipeline` in parallel
3. Findings derive from real saved watchlists' `query` JSONB executed at
   request time (cached via Watchlist.last_run_at later)

### Search
1. Filters serialised to URL search params (sharable)
2. `useEffect` on filter change → debounced fetch to
   `/api/v1/search/trademarks`
3. Facet rail calls `/api/v1/facets/*` with the same filters minus its own
   column (`exclude=country`) → cross-react counts
4. Multi-select → selection bar → POST `/api/v1/compare`

### Detail
1. `/api/v1/marks/{id}` returns mark + computed opposition window + status
2. `/api/v1/marks/{id}/{timeline,co-marks,similar,applicant-stats,inid-fields}`
   load lazily in parallel
3. "Open in gazette" links to `/admin/gazettes`

### Ingest pipeline
1. `POST /api/v1/gazettes` streams PDF to disk (1MB chunks, size capped,
   %PDF- magic-byte sniff, sha256 dedup)
2. Inserts `Gazette` row with `status=uploaded`, `uploaded_by=user.id`
3. Enqueues `worker.ingest.ingest_pdf(gazette_id)` on Redis `ingest` queue
4. Worker picks up → `Gazette.status = processing` → runs `tm_extractor` →
   maps each section to a `Trademark` row (batched 200 at a time)
5. On completion → `status = completed` + `row_count` + `processed_at`
6. On failure → `status = failed` + `error_message[:4000]`
