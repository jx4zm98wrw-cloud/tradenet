# Deployment

## Environments

Three configurations distinguished by `TM_ENV`:

| `TM_ENV` | `/docs` exposed | Sentry sample rate | HSTS header | Default secret rejected |
|---|---|---|---|---|
| `development` | yes | 0% | no | no |
| `staging` | yes | 10% | yes | no |
| `production` | **no** | 10% | yes | **yes** — boot fails if `TM_SECRET_KEY` is the default |

## Required environment variables

See `.env.example` for the full list. The bare minimum for production:

```bash
TM_ENV=production
TM_DATABASE_URL=postgresql+asyncpg://USER:PASS@db-host:5432/tm
TM_DATABASE_URL_SYNC=postgresql+psycopg2://USER:PASS@db-host:5432/tm
TM_REDIS_URL=redis://redis-host:6379/0
TM_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(64))')
TM_CORS_ORIGINS=https://app.example.com
TM_UPLOAD_DIR=/mnt/tm-uploads
TM_DATA_DIR=/srv/backend                # where cities_by_country.json lives
TM_SENTRY_DSN=https://…@sentry.io/…     # optional but recommended
TM_RATE_LIMIT_DEFAULT=300/minute        # tune per traffic profile
TM_RATE_LIMIT_UPLOAD=20/minute
```

In production, supply these via the orchestrator's secret store
(Kubernetes Secrets, AWS Parameter Store, HashiCorp Vault) — **not** a
checked-in `.env` file.

## Building the image

```bash
docker build -t tradenet-api:$(git rev-parse --short HEAD) app/backend
```

The image runs as non-root user `app` (UID 1000). Mount the upload directory
RW; everything else can be read-only.

## Running locally with the image

```bash
docker compose up -d postgres redis
docker run --rm \
  --network=host \
  --env-file app/.env \
  -v $(pwd)/app/backend:/srv/backend:ro \
  -v /tmp/tm_uploads:/tmp/tm_uploads:rw \
  -e TM_DATABASE_URL=postgresql+asyncpg://tm:tm@localhost:5435/tm \
  -e TM_REDIS_URL=redis://localhost:6380/0 \
  tradenet-api:dev
```

## Migration strategy

Run `alembic upgrade head` before each deploy. The CI workflow does this
against the test DB; production deploys should run it in an init container
or release-phase job, not at uvicorn startup.

```bash
alembic upgrade head
alembic current  # confirm
```

Rollback: each migration has a `downgrade()` — use `alembic downgrade -1`.

## Workers

The RQ ingest worker is a separate process. In production, run at least one
per Redis queue partition. macOS-only: `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`
required (already set in `worker/run_worker.py`).

```bash
python -m worker.run_worker
```

Worker scaling: each work-horse fork serves one job at a time. For N
concurrent ingests, run N workers. pdfplumber is NOT thread-safe — never
raise `--max-workers` inside a single worker.

## Health probes

```
GET /health         → 200 {"status":"ok"} — process is up (no deps)
GET /health/ready   → 200 {"status":"ok","deps":{"database":"ok","redis":"ok"}}
                      OR 200 {"status":"degraded","deps":{...}} when a dep is down
```

Use `/health` for the orchestrator's liveness probe, `/health/ready` for the
readiness probe. Both return JSON — Kubernetes pattern.

## Observability

- **Logs** — JSON to stderr (when non-TTY). Ship to your aggregator
  (Loki / Datadog / CloudWatch). Every line carries `request_id` when
  emitted in a request context.
- **Metrics** — `/metrics` Prometheus endpoint. Suggested SLI panels:
  - `http_requests_total{handler,status}`
  - `http_request_duration_seconds_bucket`
  - RQ queue depth (scrape from Redis directly)
- **Errors** — Sentry SDK initialised when `TM_SENTRY_DSN` is set.
  `traces_sample_rate=0.1` in production by default; tune in
  `api/main.py:_init_sentry`.

## Backup

**Not implemented.** When the product needs it:

- Postgres: `pg_dump` to S3 nightly; PITR via WAL archiving for tighter RPO.
- Uploaded PDFs: mirror `TM_UPLOAD_DIR` to S3 (or skip — they're re-uploadable
  from source).

## Disaster recovery

Database is the source of truth. Uploaded PDFs are reproducible (the file
is dedup'd by `sha256` — re-upload is idempotent). The ingest worker can
re-run on demand by resetting `gazettes.status = 'uploaded'` and re-enqueuing.

## Rollback

1. Roll back image: `docker-compose pull tradenet-api:<previous-sha>`.
2. If the previous version's schema differs: `alembic downgrade <revision>`.
3. Verify `/health/ready` reports ok.
4. If watchlists' `query` JSONB changed shape, do not roll back schema —
   instead, run a forward fix.
