/**
 * Auth setup — logs in once and stores the resulting cookies + access
 * token to .auth/admin.json. Every other spec uses that state so it
 * starts already authenticated, skipping the login form on every test.
 *
 * The test admin account must already exist in the database. Bootstrap
 * once with:
 *
 *   cd app/backend
 *   python -m scripts.create_user \
 *     --email playwright@local --name Playwright \
 *     --role admin --password "playwright-test-password"
 *
 * If you change these credentials, update them here too.
 */
import { test as setup, expect } from "@playwright/test";
import path from "path";

const ADMIN_EMAIL = process.env.PLAYWRIGHT_ADMIN_EMAIL ?? "playwright@local";
const ADMIN_PASSWORD = process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? "playwright-test-password";
const STORAGE_PATH = path.join(__dirname, "..", "..", ".auth", "admin.json");

setup("authenticate as admin", async ({ page }) => {
  await page.goto("/login");

  // Confirm the login form is what's rendering — guards against accidentally
  // landing on a server-error page or stale `/login` redirect loop.
  await expect(page.getByRole("heading", { name: /sign in/i })).toBeVisible();

  await page.getByLabel(/email/i).fill(ADMIN_EMAIL);
  await page.getByLabel(/password/i).fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: /sign in/i }).click();

  // After login, AuthContext redirects to `/` (or `?next=…`). Wait until
  // we leave /login — the redirect is the actual auth proof.
  await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 10_000 });

  // Persist cookies + localStorage so other specs reuse this session.
  await page.context().storageState({ path: STORAGE_PATH });
});
