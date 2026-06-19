# RQ Worker as a Managed Compose Service (Design)

**Status:** Approved for planning · 2026-06-19

**Goal:** Run the RQ worker as a `docker-compose` service with `restart: unless-stopped`, so it survives machine reboots and session-end — replacing the hand-launched host process that currently dies when the session ends. This makes the `/admin/madrid` sweep controls (and gazette ingest) durable.

## Background

The worker is currently a plain host process (`python -m worker.run_worker`) launched by hand. When the launching session/terminal ends, the worker dies and the sweep controls go inert (state survives in Postgres, but nothing executes). `docker-compose.yml` today runs only `postgres` + `redis`; the backend and worker run on the host venv in dev. This adds a containerized `worker` service to the same compose stack.

## Architecture: containerized worker, baked image

Chosen flavor: **code baked into the image** (built via `app/backend/Dockerfile`), not bind-mounted source. The worker code changes rarely; a `docker compose build worker` on change is acceptable and keeps the service prod-like with fewer moving parts.

### The `worker` service (`app/docker-compose.yml`)

```yaml
  worker:
    build:
      context: ./backend            # app/backend (compose file lives in app/)
    command: python -m worker.run_worker
    environment:
      TM_DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-tm}:${POSTGRES_PASSWORD:-tm}@postgres:5432/${POSTGRES_DB:-tm}
      TM_DATABASE_URL_SYNC: postgresql+psycopg2://${POSTGRES_USER:-tm}:${POSTGRES_PASSWORD:-tm}@postgres:5432/${POSTGRES_DB:-tm}
      TM_REDIS_URL: redis://redis:6379/0
      TM_SECRET_KEY: ${TM_SECRET_KEY:-dev-only-not-for-prod}
      TM_DATA_DIR: /data
    volumes:
      - ../:/data                    # project root → shared file outputs
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
```

### Why each piece

- **Internal network URLs** (`postgres:5432`, `redis:6379`): inside the compose network the worker reaches the services by name on their container ports — *not* the host-published `5435`/`6380`. It hits the same Postgres/Redis the host API uses.
- **`TM_DATA_DIR=/data` + `../:/data` bind mount (the crux):** `Settings.data_dir = Path(__file__).resolve().parents[3]` resolves to the project root on the host, but inside the image (code at `/srv/backend`) it resolves to `/`. So `data_dir` **must** be set explicitly. Bind-mounting the host project root at `/data` and setting `TM_DATA_DIR=/data` makes the worker read/write the *same* `madrid_cache/`, `image/`, and `input/` directories the host API serves from — so gazette PNGs written by the worker appear at the host's `/static/image/`, and the WIPO HTML cache is shared (re-runs skip cached IRNs).
- **No macOS fork guard:** `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` is only needed on a macOS host; the Linux container doesn't need it.
- **`restart: unless-stopped`:** the Docker daemon restarts the worker after a crash or reboot — the durability the user asked for.
- **`depends_on … healthy`:** the worker waits for Postgres + Redis to be ready (they already define healthchecks).

### Cutover

Stop the hand-launched host worker (`pkill -f worker.run_worker`) before bringing up the container — otherwise two workers race the same `madrid`/`ingest` queues and double-process. From then on the worker runs in the container.

## Data flow (unchanged from the app's perspective)

```
admin UI → API (host) → enqueue on Redis → containerized worker pulls job
         → run_sweep_chunk / ingest_pdf → writes Postgres + /data files (shared)
```

The API stays host-run in dev; only the worker moves into compose. Both share Postgres, Redis, and the project-root filesystem.

## Error handling / edge cases

- **Image build deps:** the build installs the full `requirements.txt` (pymupdf, rq, etc.). If a dep fails to build in the slim image, fix the Dockerfile/requirements as part of implementation.
- **Double worker:** documented cutover (stop host worker) prevents queue races.
- **Stale cache vs DB:** unchanged — `enrich_one` keys on the DB; the shared cache only avoids re-fetching.

## Testing / verification

Infra change — no unit tests. Verification is operational:
1. `docker compose -f app/docker-compose.yml up -d --build worker`
2. `docker compose -f app/docker-compose.yml logs worker` shows *"Listening on ingest, madrid…"*.
3. Start a sweep from `/admin/madrid` (or enqueue a chunk); confirm the containerized worker processes it (control-row counters advance, `madrid_records` grows).
4. `docker compose restart worker` (or `docker stop` then daemon restart) and confirm it comes back on its own.

## Non-goals

- **Production orchestration** (Kubernetes, autoscaling, multiple workers) — out of scope; compose is the dev/local target.
- **Containerizing the API** in dev — it stays host-run for live reload; only the worker moves.
- **A separate prod compose file** — the existing file is the dev stack; prod uses an external orchestrator (as its header already notes).

## Out-of-scope follow-ups (noted)

- A `docker-compose.prod.yml` (or k8s manifests) if/when the app deploys.
- Bind-mounting worker source for live code reload, if worker development becomes frequent.
