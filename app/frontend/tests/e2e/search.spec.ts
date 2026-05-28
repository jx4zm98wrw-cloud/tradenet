/**
 * Search flow — verifies the nav-search → cmdk → results-page transitions.
 *
 * Pre-authenticated via the .auth/admin.json storage state (set up by
 * auth.setup.ts). Assertions are structural and forgiving — the UI is
 * search-input-driven (no page-level <h1>, no debounced URL update on
 * keystroke), so we verify page loads + key interactive elements
 * appear rather than guess at headings.
 */
import { test, expect } from "@playwright/test";

test.describe("Search", () => {
  test("nav-search button opens the Cmd-K palette", async ({ page }) => {
    // `/` is the marketing landing now (post-PR 1) — it renders MarketingNav
    // with no Cmd-K search box. The in-app TopNav with the search button
    // lives under (app) routes; use /today as the entrypoint.
    await page.goto("/today");
    // TopNav's central search button: locate by its visible label text.
    // Using getByText (not getByRole + name) because the button mixes a
    // text label with an icon and a ⌘K Kbd badge, which confuses
    // accessible-name matching.
    await page.getByText(/Search marks, applicants, classes/i).click();

    // Cmd-K opens an overlay with an input that should receive focus.
    // We don't depend on a specific role/placeholder — just confirm an
    // input is visible and ready for input within a reasonable timeout.
    const overlayInput = page
      .locator("input[autofocus], input[aria-autocomplete='list'], [role='dialog'] input")
      .first();
    await expect(overlayInput).toBeVisible({ timeout: 5_000 });
  });

  test("/search renders without crashing", async ({ page }) => {
    await page.goto("/search");
    // No raw error shell — that's the smoke goal here.
    await expect(page.locator("text=/Application error|Internal Server Error/i")).toHaveCount(0);
    // And the URL stuck; we landed on the right route.
    await expect(page).toHaveURL(/\/search/);
  });

  test("typing + submitting in /search updates the URL with q=", async ({ page }) => {
    await page.goto("/search");
    // Fill the first input + press Enter. The page commits the query to
    // the URL on submit, not on every keystroke.
    const q = page.locator("input").first();
    await q.fill("zzz_no_match_smoke");
    await q.press("Enter");
    await expect(page).toHaveURL(/[?&]q=zzz_no_match_smoke/, { timeout: 5_000 });
  });
});
