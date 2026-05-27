/**
 * Compare flow — verifies the /compare page renders.
 *
 * The compare flow takes two markIds and renders a side-by-side
 * similarity report. With <2 marks pre-selected, the page renders an
 * empty-state explainer. We verify both code paths render without
 * crashing — that's the smoke goal.
 */
import { test, expect, type Page } from "@playwright/test";

const API = process.env.PLAYWRIGHT_API_URL ?? "http://localhost:8000";

async function firstTwoMarkIds(page: Page): Promise<string[]> {
  const r = await page.request.get(`${API}/api/v1/search/trademarks?limit=2`);
  if (!r.ok()) return [];
  const body = await r.json();
  return (body?.items ?? []).map((x: { mark: { id: string } }) => x.mark.id).filter(Boolean);
}

test.describe("Compare", () => {
  test("/compare with no pre-selects renders the empty state", async ({ page }) => {
    await page.goto("/compare");
    // The header is stable regardless of pre-select state.
    await expect(page.getByRole("heading", { name: /compare/i }).first()).toBeVisible();
    // No raw error shell.
    await expect(page.locator("text=/application error|Internal Server Error/i")).toHaveCount(0);
  });

  test("/compare?ids=A,B renders a result when two real marks are passed", async ({ page }) => {
    const ids = await firstTwoMarkIds(page);
    test.skip(ids.length < 2, "need at least 2 marks in DB to smoke compare");

    await page.goto(`/compare?ids=${ids[0]},${ids[1]}`);
    // The page header always renders. The result region may take a beat
    // to fetch /api/v1/compare; we wait on the heading first as a
    // page-loaded sentinel, then for a similarity-score or pair
    // identifier to appear. Either selector is OK — we just want to
    // know the API came back.
    await expect(page.getByRole("heading", { name: /compare/i }).first()).toBeVisible();
    // Pages rendering the compare result include the word "score" or a
    // percent sign near the similarity figure. We tolerate either.
    await expect(
      page.locator("text=/score|similarity|%/i").first()
    ).toBeVisible({ timeout: 8_000 });
  });
});
