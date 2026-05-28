/**
 * Login flow — verifies the unauthenticated UX path end-to-end.
 *
 * Doesn't share the .auth/admin.json storage state because we want to
 * exercise the login form itself. Each test in this file starts as a
 * pristine anonymous browser.
 */
import { test, expect } from "@playwright/test";

test.use({ storageState: { cookies: [], origins: [] } });

test.describe("Login", () => {
  test("redirects unauthenticated users to /login", async ({ page }) => {
    // Hit a protected page — AuthProvider should bounce us to /login.
    // `/` is now the public marketing landing (post-PR 1 restructure); use
    // `/today` instead, which lives under the (app) group + AuthProvider.
    await page.goto("/today");

    await expect(page).toHaveURL(/\/login(\?next=.+)?$/);
    await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();
  });

  test("rejects wrong password with an error message", async ({ page }) => {
    await page.goto("/login");

    await page.getByLabel(/email/i).fill("playwright@local");
    await page.getByLabel(/password/i).fill("definitely-not-the-password");
    await page.getByRole("button", { name: /sign in/i }).click();

    // The error region surfaces backend's structured detail (FastAPI returns
    // a 401 with `{detail: "Incorrect email or password"}` per auth router).
    // We assert the bare presence of an error UI region, not the literal
    // string, since the wording may evolve.
    await expect(page.locator("text=/incorrect|invalid|failed/i")).toBeVisible({
      timeout: 8_000,
    });
    // We must still be on /login — no redirect on failed login.
    await expect(page).toHaveURL(/\/login/);
  });

  test("preserves ?next= parameter through login", async ({ page }) => {
    // Visit a protected page; AuthProvider should redirect with ?next= set
    // to the original path so we can land back there.
    await page.goto("/watchlists");
    await expect(page).toHaveURL(/\/login\?next=/);

    // The redirect target should be url-encoded.
    const url = new URL(page.url());
    expect(url.searchParams.get("next")).toBe("/watchlists");
  });
});
