# End-to-end smoke tests (Playwright)

Structural smoke tests for the four main user journeys: **login**, **search**, **mark detail**, **compare**. Each spec asserts page-load + key-element visibility, not data-specific content — they survive across dev-DB resets and re-ingests.

## Prerequisites

1. Backend running on `http://localhost:8000` (postgres on :5435, redis on :6380 — see [`app/docker-compose.yml`](../../../docker-compose.yml)).
2. Frontend running on `http://localhost:3000`. The Playwright config auto-starts `pnpm dev` if nothing's listening there yet, so leaving it running speeds up the inner loop.
3. A test admin user. Bootstrap once:
   ```bash
   cd app/backend
   python -m scripts.create_user \
     --email playwright@local --name Playwright \
     --role admin --password "playwright-test-password"
   ```
   Same credentials baked into `auth.setup.ts`.

## Run

From `app/frontend/`:

```bash
pnpm test:e2e:install   # first time only — downloads chromium
pnpm test:e2e           # headless run, results in playwright-report/
pnpm test:e2e:ui        # interactive mode — watch tests run + debug
```

Override target URL or credentials via env:

```bash
PLAYWRIGHT_BASE_URL=https://staging.tradenet.example \
PLAYWRIGHT_ADMIN_EMAIL=qa@example \
PLAYWRIGHT_ADMIN_PASSWORD='real-pwd' \
pnpm test:e2e
```

## Architecture

- **`auth.setup.ts`** runs once before any other spec — logs in via the real `/login` form, captures cookies + localStorage to `.auth/admin.json`.
- **`login.spec.ts`** runs without that stored state (it's the spec testing the login flow), so each test starts as anonymous.
- **`search.spec.ts`, `detail.spec.ts`, `compare.spec.ts`** start pre-authenticated via the stored state — no re-login per test.

`.auth/admin.json` is gitignored. If anything looks off, delete it and re-run; the setup spec will recreate it.

## What's intentionally not covered

- **Specific gazette content**. Search/detail/compare tests use whatever is in the DB; they skip cleanly if there are <1 / <2 marks. Adding a "minimum seeded data" fixture is a separate task.
- **CI execution**. The config is CI-aware (sets `forbidOnly: !!process.env.CI`, retries=1) but no GitHub Actions job runs Playwright yet. Wiring CI requires Postgres+Redis services + alembic migrate + uvicorn + the user bootstrap — tracked separately.
- **Visual diffs**. Playwright supports screenshot regression, but the spec set here is structural.
