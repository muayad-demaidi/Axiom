import { test, expect } from "@playwright/test";

// Tahleel CTA — feature is not yet implemented at the time this suite
// was added (Task #223). Marked as fixme so the suite stays green
// until the Tahleel surface ships.

test.describe("tahleel", () => {
  test.fixme(true, "Tahleel feature not yet built — CTA wiring pending.");

  test("ابدأ تحليل Tahleel CTA is visible on the workspace", async ({ page }) => {
    await page.goto("/app");
    await expect(page.getByText("ابدأ تحليل Tahleel")).toBeVisible();
  });
});
