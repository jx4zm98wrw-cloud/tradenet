# Security posture

## What's protected today

### Input validation
- All request bodies validated by Pydantic at the route boundary.
- Path parameters use `uuid.UUID` (rejected if not valid UUID).
- Query-param bounds: `limit ≤ 200–500` per route, `offset ≥ 0`, `threshold ∈ [0,1]`.
- File upload: 500MB cap (`TM_MAX_UPLOAD_BYTES`), magic-byte sniff (`%PDF-`),
  extension whitelist (`.pdf`).

### SQL injection
- SQLAlchemy ORM everywhere.
- One `text()` query in `routes/stats.py` — bound parameters (`:lim`), safe.

### Cross-origin
- `CORSMiddleware` configured from `TM_CORS_ORIGINS` (comma-separated). Empty
  by default in production. Credentials allowed, all standard methods.
- `X-Request-ID` exposed for client-side correlation.

### Rate limiting
- `slowapi` IP-keyed limiter, Redis-backed.
- Defaults: 120/min global, 10/min on `POST /api/v1/gazettes`.
- On limit exceed: HTTP 429 with consistent error envelope.

### Security headers
- `Content-Security-Policy` — restricts script/style/connect/frame-ancestors.
- `X-Frame-Options: DENY`.
- `X-Content-Type-Options: nosniff`.
- `Referrer-Policy: strict-origin-when-cross-origin`.
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
- `Strict-Transport-Security` — production only (irreversible cache).

### Container hardening
- Multi-stage build; wheels built in build stage, runtime image is `slim`.
- Non-root user `app:app` (UID 1000) — no privilege escalation.
- `HEALTHCHECK` directive — liveness probe at `/health`.
- `.dockerignore` excludes dev deps, tests, secrets.

### Secrets
- All settings env-driven (`TM_*` prefix). `.env.example` documents the surface.
- `TM_SECRET_KEY` validator rejects the default placeholder in
  `TM_ENV=production`.
- Default DB password (`tm/tm`) is dev-only; docker-compose reads from env
  vars (`POSTGRES_PASSWORD` etc.) so prod overrides work.

### Observability
- `RequestIDMiddleware` assigns UUID per request → echoed in `X-Request-ID`
  response header → bound to structlog context for all log lines in the
  lifecycle.
- Sentry SDK initializes when `TM_SENTRY_DSN` is set; off otherwise.
- Prometheus metrics at `/metrics` when `TM_ENABLE_PROMETHEUS=true`.

## What's NOT protected yet

### Authentication
**The biggest gap.** `api/auth.py:_resolve_user()` returns a fixed stub user
for every request. All `require_user` / `require_admin` dependencies pass.

The seam is in place — when real auth lands (OAuth, session cookie, JWT…),
only `_resolve_user()` changes. All route guards (`Depends(require_user)`,
`Depends(require_admin)`) keep their wiring. The `users` + `sessions`
migration is also pending.

Until then: **the API must not be exposed to the public internet**. Local
dev / VPN / private network only.

### Backup / restore
No `pg_dump` cron, no S3 sync for uploaded PDFs, no documented RTO/RPO.
Mitigation: docker-compose volume `tm_pgdata` is persistent across reboots
but lost on volume removal.

### Audit logging
No append-only audit table for sensitive actions (delete watchlist, etc.).
Structured logs capture the requests, but logs aren't tamper-evident.

### DDoS / WAF
Rate limiting is per-IP only — trivially bypassed via header spoofing if the
load balancer doesn't supply `X-Forwarded-For`. Real protection needs a WAF
in front (Cloudflare / AWS WAF).

### Data retention / GDPR
Trademark applicants include named individuals. There's no retention policy,
no right-to-erasure workflow, no PII inventory. Out of scope for the MVP;
flag for legal before any external user lands.

## Reporting

Security issues to `security@<your-org>.example` — not via the issue tracker.
Include the `X-Request-ID` from the affected response if relevant.
