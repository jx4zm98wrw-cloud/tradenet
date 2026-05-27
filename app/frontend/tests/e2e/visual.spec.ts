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

  test("home (Today digest)", async ({ page }) => {
    await page.goto("/");
    // Wait for the main heading to be present before snapshotting — guards
    // against capturing a half-loaded SSR frame.
    await expect(page.locator("h1, h2").first()).toBeVisible();
    await expect(page).toHaveScreenshot("home.png", {
      fullPage: false,
      // Allow tiny anti-aliasing drift between runs without flagging.
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
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
    await expect(page).toHaveScreenshot("login.png", {
      fullPage: false,
      maxDiffPixelRatio: 0.01,
    });
  });
});
