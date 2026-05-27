/**
 * Compare flow — verifies the /compare page renders.
 *
 * The compare flow takes two markIds and renders a side-by-side
 * similarity report. With <2 marks pre-selected, the page renders an
 * empty-state explainer telling the user to add marks from Search.
 * We verify both code paths render without crashing — that's the
 * smoke goal.
 *
 * The page uses an <h2> with class `head-serif` rather than an <h1>,
 * and includes a "Compare" label in a <span>. We assert on the body
 * text (more forgiving) rather than on accessible heading role.
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
  test("/compare with no pre-selects renders the empty-state explainer", async ({ page }) => {
    await page.goto("/compare");
    // Empty-state copy: prompts the user to add marks from Search.
    await expect(page.getByText(/Need at least 2 marks|add them from Search/i).first()).toBeVisible();
    // No raw error shell.
    await expect(page.locator("text=/Application error|Internal Server Error/i")).toHaveCount(0);
    await expect(page).toHaveURL(/\/compare/);
  });

  test("/compare?ids=A,B renders a similarity result when two real marks are passed", async ({
    page,
  }) => {
    const ids = await firstTwoMarkIds(page);
    test.skip(ids.length < 2, "need at least 2 marks in DB to smoke compare");

    await page.goto(`/compare?ids=${ids[0]},${ids[1]}`);
    // No raw error shell — page rendered.
    await expect(page.locator("text=/Application error|Internal Server Error/i")).toHaveCount(0);
    // Similarity result region: tolerate any of these words near the
    // similarity figure ("score" in column header, "similarity" in body
    // text, "%" in score formatting). Either of these landing on the
    // page within 8s confirms the /api/v1/compare round-trip succeeded.
    await expect(page.locator("text=/score|similarity|%/i").first()).toBeVisible({
      timeout: 8_000,
    });
  });
});
