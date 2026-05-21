# Contributing

## Local setup

See `README.md` "Quick start". Briefly: `docker compose up -d`, install
backend + frontend deps, `alembic upgrade head`, run dev servers.

## Workflow

1. Branch from `main`.
2. Make changes.
3. Run pre-commit locally: `pre-commit run --all-files` (lint + format).
4. Run the backend test suite: `cd app/backend && pytest`.
5. Run the frontend lint + build: `cd app/frontend && pnpm lint && pnpm build`.
6. Open a PR against `main`.

CI runs all of the above plus security audits (`pnpm audit`, `pip-audit`).

## Coding standards

### Python (backend)

- Ruff for lint + format (config in `pyproject.toml`).
- Mypy passes for `api/`, `worker/` — `tm_extractor/` is treated as
  vendored legacy (lint relaxations in `pyproject.toml`).
- Async everywhere in `api/` — never `requests`, never sync SQLAlchemy.
- Routes are thin: parse → call helper → return Pydantic model. Business
  logic lives in `routes/_filters.py` or dedicated services, not in
  route handlers.
- Use `Depends(require_user)` on any route that mutates or returns
  user-scoped data. Use `optional_user` when personalisation is a bonus.

### TypeScript (frontend)

- Strict mode on (`tsconfig.json`). `any` is a warning, not an error —
  prefer explicit unknown + narrowing.
- Server components by default; client components must declare `"use client"`.
- API calls go through `lib/api.ts` — never inline `fetch()` in components.
- New visual surfaces should reuse primitives from `components/ui/` and
  `components/specimen/`.

### Migrations

- New columns: add to `db/models.py` + create an Alembic revision via
  `alembic revision -m "describe change"`.
- Revisions sit in `alembic/versions/` with date-stamped filenames:
  `YYYYMMDD_NNNN_short_slug.py`.
- Always implement `downgrade()`.
- Test the migration both directions against the dev DB before opening
  the PR.

## Test policy

- **Smoke tests are required** for new route groups — at minimum, a 200
  on the happy path + a 4xx on a known-bad input.
- Integration tests against the live dev DB are OK — the suite resets
  state via `try/finally` cleanup, not transactions.
- For pure logic in `routes/_filters.py`, `tm_extractor/`, etc., prefer
  unit tests that don't hit the network.

## What changes need extra review

- **Auth / permissions** (`api/auth.py`): touches every protected route.
- **`api/main.py` middleware order**: changes can break correlation IDs or
  request lifecycle.
- **Migrations** that drop columns or rewrite types: irreversible-ish.
- **Similarity scoring**: small jitter changes can scramble UI rankings
  client teams have grown used to.

## Adding new routes

1. Create the router in `api/routes/<name>.py` with `prefix="/api/v1/<name>"`.
2. Add Pydantic input/output models — never return raw dicts.
3. Use `Depends(get_session)` for DB, `Depends(require_user)` for auth.
4. Register in `api/main.py`: `app.include_router(<name>.router)`.
5. Add a smoke test in `tests/test_smoke.py`.
6. Add the API client method in `app/frontend/lib/api.ts`.
7. If exposed in CI, the rate limiter applies the default budget — add
   `@limiter.limit(<callable>)` for stricter caps.

## Style

- Comments answer **why**, not **what**. Don't paraphrase the code in
  English next to it.
- Don't write multi-paragraph docstrings on every function. One-line
  signatures + a focused comment near the non-obvious logic.
- Prefer small surface areas: a 30-line route + a 30-line helper beats a
  100-line route every time.
