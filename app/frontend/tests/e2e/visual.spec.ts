/**
 * Visual regression guardrails — screenshot diff against committed baselines.
 *
 * Opt-in only: gated by `PLAYWRIGHT_VISUAL=1`. Without the env var, every
 * test in this file is skipped at runtime. This keeps the default
 * `pnpm test:e2e` run fast and dependent only on structural assertions
 * (login.spec, search.spec, etc.).
 *
 * Why opt-in?
 *  - Playwright screenshots are platform-specific (macOS vs Linux differ on
 *    font hinting + sub-pixel rendering). Baselines must be generated on the
 *    same OS that runs CI.
 *  - Baking initial baselines is a one-time event that should be deliberate,
 *    not a side-effect of someone running tests locally.
 *
 * Bake initial baselines (Linux/CI only — won't work cleanly on macOS):
 *   1. Bring up backend + frontend per tests/e2e/README.md
 *   2. PLAYWRIGHT_VISUAL=1 pnpm test:e2e --update-snapshots visual
 *   3. Commit the resulting `visual.spec.ts-snapshots/` directory
 *   4. Subsequent runs with PLAYWRIGHT_VISUAL=1 will fail on any diff
 *
 * Pages covered: the 5 user-visible chrome states that don't depend on
 * seeded data. Detail / compare result pages are skipped because they
 * depend on a real mark in the DB.
 */
import { test, expect } from "@playwright/test";

const VISUAL_ENABLED = process.env.PLAYWRIGHT_VISUAL === "1";

test.describe("Visual regression", () => {
  test.skip(!VISUAL_ENABLED, "Set PLAYWRIGHT_VISUAL=1 to run visual diffs.");

  // Standard viewport — keeps screenshots stable across runners.
  test.use({ viewport: { width: 1280, height: 720 } });

  // `/` now serves the public marketing landing (since the (marketing)
  // route group landed). The in-app Today digest moved to `/today`.
  // Two separate visual snapshots: one for each surface.

  test("landing page (/)", async ({ page }) => {
    await page.goto("/");
    // Hero h1 — "Catch every conflict..." — is the LCP candidate.
    await expect(page.locator("h1").first()).toBeVisible();
    await expect(page).toHaveScreenshot("landing.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });

  test("today digest (/today)", async ({ page }) => {
    await page.goto("/today");
    // Wait for the main heading to be present before snapshotting — guards
    // against capturing a half-loaded SSR frame.
    await expect(page.locator("h1, h2").first()).toBeVisible();
    await expect(page).toHaveScreenshot("today.png", {
      fullPage: false,
      // Allow tiny anti-aliasing drift between runs without flagging.
      maxDiffPixelRatio: 0.01,
    });
  });

  test("pricing page (/pricing)", async ({ page }) => {
    await page.goto("/pricing");
    // Wait for the serif hero heading — the page is largely static, but the
    // segmented controls are client components that hydrate after first paint.
    await expect(page.getByRole("heading", { name: /Priced for the work/i })).toBeVisible();
    await expect(page).toHaveScreenshot("pricing.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });

  test("coverage page (/coverage)", async ({ page }) => {
    await page.goto("/coverage");
    // Hero h1 is the marketing /coverage signal — there is no in-app
    // /coverage route, so this URL unambiguously hits the (marketing)
    // route group. The ingest timeline below is a client component but
    // its data is deterministic, so the rendered grid is pixel-stable.
    await expect(
      page.getByRole("heading", { name: /Every Vietnam IP issue/i }),
    ).toBeVisible();
    await expect(page).toHaveScreenshot("coverage.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });

  test("docs page (/docs/getting-started)", async ({ page }) => {
    await page.goto("/docs/getting-started");
    // The "Introduction to Tradenet" h1 is rendered by DocsArticleShell;
    // the docs route lives in the (marketing) group and is statically
    // generated (one SSG render per slug), so no client-side hydration
    // delay before the heading appears.
    await expect(
      page.getByRole("heading", { name: /Introduction to Tradenet/i }),
    ).toBeVisible();
    await expect(page).toHaveScreenshot("docs-getting-started.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });

  test("/search empty state", async ({ page }) => {
    await page.goto("/search");
    await expect(page.locator("input").first()).toBeVisible();
    await expect(page).toHaveScreenshot("search-empty.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });

  test("/compare empty state", async ({ page }) => {
    await page.goto("/compare");
    await expect(page.getByText(/Need at least 2 marks|add them from Search/i).first()).toBeVisible();
    await expect(page).toHaveScreenshot("compare-empty.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });

  test("/admin/gazettes empty state", async ({ page }) => {
    await page.goto("/admin/gazettes");
    // Wait until either the table renders (with rows or empty-state)
    // or the loading shimmer disappears.
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("admin-gazettes.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });

  test("/watchlists", async ({ page }) => {
    await page.goto("/watchlists");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveScreenshot("watchlists.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });
});

// Anonymous + login form has its own visual identity worth pinning.
test.describe("Visual regression — anonymous", () => {
  test.skip(!VISUAL_ENABLED, "Set PLAYWRIGHT_VISUAL=1 to run visual diffs.");
  test.use({
    viewport: { width: 1280, height: 720 },
    storageState: { cookies: [], origins: [] },
  });

  test("login page", async ({ page }) => {
    await page.goto("/login");
    // Post-PR 3 redesign: the visible h1 is "Welcome back." (the previous
    // simple form's h1 was "Sign in"). The submit button is still labeled
    // "Sign in" but it's a <button>, not a heading.
    await expect(page.getByRole("heading", { name: /welcome back/i })).toBeVisible();
    await expect(page).toHaveScreenshot("login.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });
});
