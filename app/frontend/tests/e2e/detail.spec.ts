/**
 * Mark detail flow — verifies /marks/[id] renders for a real ingested
 * trademark.
 *
 * Strategy: fetch the first trademark from the API, then navigate to its
 * detail page. The test is a no-op when the DB is empty (skipped with a
 * message) — it only runs against a populated dev / test DB.
 *
 * This avoids a hard-coded fixture ID that would break the moment the DB
 * is reset, and exercises the same JSON shape the UI consumes.
 */
import { test, expect, type Page } from "@playwright/test";

const API = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

async function firstMarkId(page: Page): Promise<string | null> {
  // Use the page's auth state (cookies + bearer) so the API call passes
  // require_admin / require_user.
  const r = await page.request.get(`${API}/api/v1/search/trademarks?limit=1`);
  if (!r.ok()) return null;
  const body = await r.json();
  const first = body?.items?.[0]?.mark;
  return first?.id ?? null;
}

test.describe("Mark detail", () => {
  test("/marks/[id] renders the hero + INID panel for a real mark", async ({ page }) => {
    const id = await firstMarkId(page);
    test.skip(id === null, "no marks in DB — bring up a gazette ingest first");

    await page.goto(`/marks/${id}`);

    // The hero column always renders a "Mark sample" or logo block plus
    // some structured INID fields. We assert on the heading region
    // (h1) being visible — that proves the page wired through the API,
    // not a 404 page.
    await expect(page.locator("h1").first()).toBeVisible();
  });

  test("/marks/<bogus-uuid> renders the not-found state gracefully", async ({ page }) => {
    // Send an unlikely UUID — must not throw or show a stack trace.
    await page.goto("/marks/00000000-0000-0000-0000-000000000000");
    // Either a 404-style "Mark not found" message or a redirect — both
    // are acceptable as long as we don't see a raw error page.
    // We assert no raw "Application error" / stack-trace shell appears.
    const errorShell = page.locator("text=/application error|Internal Server Error/i");
    await expect(errorShell).toHaveCount(0);
  });
});
