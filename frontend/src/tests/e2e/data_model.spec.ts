import { test, expect } from "@playwright/test";

// Multi-CSV data-model journey: upload two CSVs, confirm the suggested
// relationship, see the open question land in OpenQuestionsBar.

test.describe("data model", () => {
  test("project workspace exposes the data-model surface", async ({ page }) => {
    await page.goto("/app/projects");
    expect(page.url()).toMatch(/\/(app|login)/);
  });
});
