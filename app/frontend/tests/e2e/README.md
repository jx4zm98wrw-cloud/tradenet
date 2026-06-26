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

## Visual regression (opt-in)

`visual.spec.ts` captures screenshots of 5 chrome states (home, /search, /compare, /admin/gazettes, /watchlists, /login) and compares against committed baselines. **Skipped by default** — set `PLAYWRIGHT_VISUAL=1` to run.

### Why opt-in

Playwright screenshots are platform-specific (macOS vs Linux render differently due to font hinting + sub-pixel positioning). Baselines committed from one platform fail in CI on the other. Opt-in keeps the default suite portable and the visual checks tied to a single canonical environment.

### One-time bake (Linux / CI only)

```bash
# Bring up backend + frontend per the Run section above
PLAYWRIGHT_VISUAL=1 pnpm test:e2e --update-snapshots visual
# Inspect generated PNGs under tests/e2e/visual.spec.ts-snapshots/
git add tests/e2e/visual.spec.ts-snapshots/
git commit -m "test(visual): bake baselines on $(uname -s)"
```

After committing baselines, subsequent runs with `PLAYWRIGHT_VISUAL=1` enforce the diff. Any visual change of >1% pixel ratio fails.

### In CI — advisory, not gating

The `e2e` job runs Playwright in **two steps**:

1. **`Run Playwright suite (functional)`** — gating. `PLAYWRIGHT_VISUAL` is unset, so the visual specs self-skip; a red here is a real regression (broken login, mis-wired API, client-routing break) and blocks merge.
2. **`Run visual regression (advisory)`** — `continue-on-error: true` with `PLAYWRIGHT_VISUAL=1`, running only `visual.spec.ts`. A pixel diff here does **not** fail the job or block merge — an intentional UI change is *expected* to fail it until the baseline is re-baked. The HTML report + traces are still uploaded (the diagnostic upload steps fire on `steps.visual.outcome == 'failure'`), so the diff is available for manual review.

When a visual diff is intentional, re-bake and commit the baseline (see the one-time bake above, run on the CI runner image) — that turns the advisory step green again. Do **not** re-add `PLAYWRIGHT_VISUAL` to the job-level `env:` block; it belongs only on the advisory step.

#### Cheap re-bake: reuse the CI artifact (no local Linux stack needed)

You don't have to stand up the noble stack yourself to get a Linux baseline. When the advisory step fails, Playwright saves the freshly-captured screenshot to `test-results/<test>/<name>-actual.png`, and CI uploads that directory as the `playwright-traces` artifact. That `-actual.png` **is** what `--update-snapshots` would write — same noble runner, same font hinting — so it can be committed verbatim:

```bash
# Find the run whose advisory step captured the diff (e.g. main HEAD, or your PR)
gh run download <run-id> -n playwright-traces -D /tmp/pw
# Copy the actual → the committed baseline (filename keeps the -chromium-linux suffix)
cp /tmp/pw/*search-empty*/search-empty-actual.png \
   tests/e2e/visual.spec.ts-snapshots/search-empty-chromium-linux.png
git add tests/e2e/visual.spec.ts-snapshots/search-empty-chromium-linux.png
```

Sanity-check before committing: the artifact's `-expected.png` should equal the baseline you're replacing, and if the run retried, both attempts' `-actual.png` should be byte-identical (a stable render, not a flake).

## What's intentionally not covered

- **Specific gazette content**. Search/detail/compare tests use whatever is in the DB; they skip cleanly if there are <1 / <2 marks. Adding a "minimum seeded data" fixture is a separate task.
- **Visual baselines pre-committed**. See "Visual regression" above — opt-in scaffolding lands now, baselines are a separate deliberate commit on Linux.
