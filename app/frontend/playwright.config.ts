/**
 * Playwright config for end-to-end smoke tests.
 *
 * Scope: structural — verify that the login flow, search UX, mark detail,
 * and compare pages render their key elements. No data-specific assertions
 * (no "expect a row labelled X to exist") because the test DB content
 * varies between dev machines and CI.
 *
 * Local run flow:
 *   1. Backend running on :8000, frontend on :3000 (the `webServer` block
 *      below auto-starts the frontend if it isn't already up).
 *   2. A test admin account exists. Bootstrap it once with:
 *        cd app/backend
 *        python -m scripts.create_user \
 *          --email playwright@local --name Playwright \
 *          --role admin --password "playwright-test-password"
 *      The same credentials are baked into `auth.setup.ts`.
 *   3. `pnpm test:e2e` (headless) or `pnpm test:e2e:ui` (interactive).
 *
 * CI is deferred — wiring requires Postgres+Redis services, alembic
 * migrate, backend uvicorn process, and the user bootstrap. Tracked
 * as a follow-up.
 */
import { defineConfig, devices } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://localhost:3000";

export default defineConfig({
  testDir: "./tests/e2e",
  // One worker keeps the test DB stable (parallel tests can race the
  // shared admin session). When we wire CI we'll likely partition by
  // user instead.
  workers: 1,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Reasonable defaults — most pages render under 5s on commodity hw.
    actionTimeout: 10_000,
    navigationTimeout: 20_000,
  },
  // Stored-state pattern: `auth.setup.ts` logs in once and saves the
  // resulting access token + cookies to `.auth/admin.json`. All other
  // specs declare `storageState: ".auth/admin.json"` and start
  // pre-authenticated. Cuts test wall time roughly in half.
  projects: [
    {
      name: "setup",
      testMatch: /.*\.setup\.ts/,
    },
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        storageState: ".auth/admin.json",
      },
      dependencies: ["setup"],
    },
  ],
  // Auto-start the frontend dev server if nothing is listening on :3000.
  // Backends are NOT auto-started — they're heavier (Postgres + Redis +
  // python deps) and developers usually have them running already.
  webServer: process.env.PLAYWRIGHT_SKIP_WEBSERVER
    ? undefined
    : {
        command: "pnpm dev",
        url: BASE_URL,
        reuseExistingServer: true,
        timeout: 60_000,
      },
});
