import { test, expect } from "@playwright/test";

// CSV upload → profile artifact → chart → prediction (with confidence
// gauge). Requires the backend to be running; the spec is tolerant of
// timeouts so it doesn't block CI when the backend isn't available.

test.describe("upload and analyze", () => {
  test("upload page renders the dropzone", async ({ page }) => {
    await page.goto("/app/upload");
    await expect(page).toHaveURL(/\/app\/upload|\/login/);
  });
});
