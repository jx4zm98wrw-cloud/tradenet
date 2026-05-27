# Tradenet — Trademark Gazette workbench

Internal tool for IP/trademark professionals working with the Vietnamese NOIP
gazette. The product surfaces are organized around the user's jobs:

- **Watch** — what new filings this week resemble marks my clients own?
- **Clear** — is this proposed name conflict-free?
- **Oppose** — what's in the opposition window, and when does it close?
- **Report** — produce client-facing watch reports

---

## Repository layout

```
app/
├── backend/                FastAPI + SQLAlchemy + Postgres + RQ worker
│   ├── api/                HTTP layer (routes, auth, errors, settings, logging)
│   │   └── routes/         Resource routers (one file per concept)
│   ├── alembic/            DB migrations
│   ├── tm_extractor/       PDF parser library (refactored from TM_csv_builder)
│   ├── worker/             RQ ingest job + section→row mapper
│   ├── tests/              pytest suite (httpx AsyncClient against live ASGI)
│   ├── pyproject.toml      Ruff + Mypy + pytest config
│   ├── requirements.txt    Pinned runtime deps
│   ├── requirements-dev.txt Lint/test/type-check deps
│   ├── Dockerfile          Multi-stage build, non-root user, HEALTHCHECK
│   └── .dockerignore
├── frontend/               Next.js 15 (App Router), React 19, Tailwind 4
│   │                       Marketing site (Landing / Pricing / Coverage /
│   │                       Docs / Login) is planned to ship into this same
│   │                       codebase as a (marketing)/ Route Group — see
│   │                       ../design_handoff_tradenet_marketing/IMPLEMENTATION_PLAN.md
│   ├── app/                File-based routes (Today / Search / Detail / …)
│   ├── components/         UI primitives, specimen renderer, Cmd-K
│   ├── lib/                Typed API client + helpers
│   ├── next.config.js      Security headers (CSP / HSTS / X-Frame / …)
│   ├── .eslintrc.json      ESLint config (extends `next/core-web-vitals`)
│   └── tsconfig.json       Strict mode on
├── docker-compose.yml      Postgres + Redis for local dev
└── .env.example            All env vars; copy to .env for local

../.github/workflows/ci.yml    Backend + frontend + security audit
../.pre-commit-config.yaml     Local mirror of CI lint
```

See `ARCHITECTURE.md` for the cross-cutting design, `SECURITY.md` for the
security posture, and `DEPLOYMENT.md` for the production runbook.

---

## Quick start (local)

### 1. Infrastructure

```bash
cd app
cp .env.example .env       # edit if defaults conflict with local ports
docker compose up -d       # postgres on :5435, redis on :6380
```

### 2. Backend

```bash
cd app
python3 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt
pip install -e backend           # editable install of the `tm-backend` package
                                 # (puts api/, worker/, scripts/ on sys.path)

cd backend
export $(grep -v '^#' ../.env | xargs)
alembic upgrade head
uvicorn api.main:app --reload --port 8000

# In a separate terminal — RQ worker (macOS needs the fork guard)
OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES python -m worker.run_worker
```

### 3. Frontend

```bash
cd app/frontend
pnpm install
pnpm dev               # http://localhost:3000
```

Open `http://localhost:3000/` for the Today screen, or `/admin/gazettes`
(currently always admin) to upload a PDF.

---

## API

All endpoints live under `/api/v1/`. OpenAPI schema served at `/openapi.json`
and Swagger UI at `/docs` (disabled in production).

Public-ish (rate-limited, no auth required today; will require auth once it's
wired):

| | |
|---|---|
| `GET /health` | Liveness (no deps checked) |
| `GET /health/ready` | Readiness — DB + Redis reachable |
| `GET /metrics` | Prometheus scrape endpoint |
| `GET /api/v1/today/digest` | Dashboard headline stats |
| `GET /api/v1/findings` | Watchlist matches in latest gazette |
| `GET /api/v1/opposition-windows` | Open opposition windows |
| `GET /api/v1/search/trademarks` | Scored search |
| `GET /api/v1/facets/{country,nice-classes}` | Cross-reactive facet counts |
| `GET /api/v1/marks/{id}` | Mark detail with derived opposition + status |
| `GET /api/v1/marks/{id}/{timeline,co-marks,similar,inid-fields,applicant-stats}` | Detail subresources |
| `POST /api/v1/compare` | Side-by-side conflict scorecard |

Auth-gated (require `Depends(require_user)`):

| | |
|---|---|
| `POST /api/v1/gazettes` | Upload PDF (rate-limited: 10/minute per IP) |
| `POST /api/v1/watchlists` | Create watchlist (owner_id auto-stamped) |
| `PUT  /api/v1/watchlists/{id}` | Update — must own (admins bypass) |
| `DELETE /api/v1/watchlists/{id}` | Delete — same |

Admin-gated:

| | |
|---|---|
| `GET /api/v1/admin/check` | Stub returns `{ isAdmin: true }` until auth lands |

Every response wears an `X-Request-ID` header. On error you get the envelope
`{ "error": { "code", "message", "request_id", "details" } }`.

---

## Real vs. mocked

This product depends on several systems that aren't built yet. Each mock is
isolated to a single function so swap-in is trivial.

| Capability | State | File |
|---|---|---|
| Similarity engine (phonetic / visual / semantic) | **Mock** — substring + per-id jitter | `routes/search.py:_score`, `routes/today.py:_fake_score`, `routes/compare.py:_score_pair`, `routes/marks.py:_similar` |
| OCR confidence + flagged-row count | **Mock** — derived from SHA-256 of file content | `routes/gazettes.py:_gazette_out` |
| Authentication | **Stub** — returns a fixed admin user | `api/auth.py:_resolve_user` |
| Recent-search history | localStorage (no server-side persistence) | `components/cmdk.tsx`, `app/page.tsx` |
| Mark specimen images | **Real** — `image_extractor/extractor.py` extracts per-sector PNGs to `image/<year>/<stem>/`; worker resolver writes `trademarks.logo_path`; ~99.985% combined coverage across the 2026 gazette set. `markDisplay()` falls back to a synthesized SVG wordmark only for the ~0.015% of rows where the gazette has no figurative image AND no `(540)` text. | `lib/mark-display.ts`, `worker/ingest.py:_resolve_logo_path` |
| Compare PDF report export | Returns HTTP 501 | `routes/compare.py:export_pdf` |

Real data flowing today: trademark records, opposition window math, co-marks,
applicant portfolio counts, watchlist CRUD + saved-query execution, facet
cross-counts, pipeline ingest stats.

---

## CI

`.github/workflows/ci.yml` runs three jobs on push + PR:

- **backend** — Ruff lint + format, Alembic migrate, pytest suite (against
  ephemeral Postgres + Redis services)
- **frontend** — pnpm install + ESLint + production build (catches TS errors)
- **audit** — `pnpm audit --audit-level=high` + `pip-audit`

Local pre-commit (optional): `pip install pre-commit && pre-commit install`.

---

## Ports

| | | |
|---|---|---|
| Postgres | 5435 | `TM_DATABASE_URL` |
| Redis | 6380 | `TM_REDIS_URL` |
| FastAPI | 8000 | `--port` |
| Next.js | 3000 | `--port` |

Adjust in `.env` + `docker-compose.yml` if there's a collision.
