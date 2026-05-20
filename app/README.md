# Trademark Gazette — vertical-slice app

End-to-end version of the NOIP Vietnam gazette extractor: PDF upload → background
ingest → searchable database → web UI.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Frontend (Next.js, :3000)                       │
│        /upload  →  /gazettes  →  / (search)                          │
└──────────────┬──────────────────────────────────────────────────────┘
               │   /api/* (proxied via next.config.js rewrites)
               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  FastAPI (:8000)  —  app/backend/api                 │
│   POST /api/gazettes      (upload PDF, dedup on sha256)              │
│   GET  /api/gazettes      (list + status)                            │
│   GET  /api/trademarks    (multi-filter search)                      │
└──────────────┬──────────────────────────────────────────────────────┘
               │ enqueue ingest job                          ▲
               ▼                                             │
        ┌──────────────┐     ┌──────────────────────────────┴──┐
        │ Redis (RQ)   │ ──▶ │ Worker — worker.ingest.ingest_pdf │
        │   :6380      │     │    uses tm_extractor library      │
        └──────────────┘     └──────────────┬───────────────────┘
                                            ▼
                                   ┌────────────────┐
                                   │ Postgres :5435 │
                                   │   gazettes      │
                                   │   trademarks    │
                                   └────────────────┘
```

The extraction logic itself (`tm_extractor`) is the refactored library version of
the original `TM_csv_builder.py`. CLI parity is byte-identical: running
`python TM_csv_builder.py` from the repo root still produces the same CSVs (the
file is now a thin wrapper around `tm_extractor.cli.run`).

## Quick start

### Prerequisites
- Docker + Docker Compose (for postgres + redis)
- Python 3.11+ and pnpm

### 1. Bring up infra

```bash
cd app
docker compose up -d                # postgres :5435, redis :6380
```

### 2. Backend

```bash
cd app
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# Env (copy and edit if needed)
cp .env.example .env

# Apply schema
cd backend
export $(grep -v '^#' ../.env | xargs)
alembic upgrade head

# Run API + worker (two terminals)
uvicorn api.main:app --reload --port 8000
# in another terminal:
python -m worker.run_worker
```

### 3. Frontend

```bash
cd app/frontend
pnpm install
pnpm dev                            # http://localhost:3000
```

Open `http://localhost:3000/upload`, drop a PDF, then check `/gazettes`. The
extraction job lands in Redis; the worker picks it up and inserts rows. The
gazettes page polls every 5s for non-terminal rows. Once `completed`, search
the data at `/`.

## Schema

Two tables. See `app/backend/api/db/models.py`.

### `gazettes`
One row per uploaded PDF. Deduped by sha256.

| col | type | notes |
|---|---|---|
| `id` | uuid | pk |
| `filename`, `sha256`, `size_bytes`, `storage_path` | | upload metadata |
| `gazette_type` | enum A/B | inferred from filename prefix |
| `issue_year`, `issue_number` | int | parsed from `<X>_T<n>_<YYYY>.pdf` |
| `status` | enum | `uploaded → processing → completed | failed` |
| `row_count`, `error_message`, `uploaded_at`, `processed_at` | | |

### `trademarks`
Flat per-record table. Indexes on app#, cert#, madrid#, country, city, type,
name, ip_agency, year, month, plus GIN on `nice_classes[]`.

Record types:
- `A` — A-file application (anchored by `(210)`)
- `B_domestic` — B-file with non-null `(111)`
- `B_madrid` — B-file with non-null `(116)` (matches the old `_madrid.csv` split)

Raw WIPO marker text is preserved verbatim in `raw_511_text` / `raw_531_text` /
`mark_sample` (which preserves case) etc. Parsed/typed values live in
`nice_classes text[]`, `publication_date_*`, `year/month`, `applicant_*`.

## Re-running ingest

The `gazettes.sha256` unique constraint means re-uploading the same file is a
no-op. To force re-extraction, delete the gazette (`DELETE FROM gazettes WHERE
id = '…'` — cascades to trademarks), then upload again, OR use
`backend/scripts/smoke_ingest.py <abs_pdf_path>` which resets the row in place.

## Ports (chosen to avoid common collisions)

| | port |
|---|---|
| Postgres | 5435 |
| Redis | 6380 |
| FastAPI | 8000 |
| Next.js | 3000 |

Adjust in `docker-compose.yml`, `.env`, and `next.config.js` if you need them
elsewhere.

## What's deferred

- **Auth.** No user model yet; `gazettes.uploaded_by` is a nullable string
  placeholder.
- **Hosting / deployment.** Backend Dockerfile is provided; no orchestration
  manifests (k8s, fly.io, etc.) yet — depends on hosting choice.
- **Search ergonomics.** Full-text on `applicant_name` uses `ILIKE` for now;
  a `pg_trgm` GIN index will be needed for fast fuzzy search once datasets grow.
- **Aggregations / dashboards.** The team-use views (top applicants, class
  distribution, country trends) are easy follow-up queries against the schema
  but no endpoint surfaces them yet.
