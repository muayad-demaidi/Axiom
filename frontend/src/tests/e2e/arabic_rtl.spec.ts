import { test, expect } from "@playwright/test";

// Arabic RTL rendering — direction, glyphs, drawer labels, Western
// digits in numeric gauges.

test.describe("arabic rtl", () => {
  test("at least one RTL section is present on the marketing root", async ({ page }) => {
    await page.goto("/");
    const hasRtl = await page.evaluate(() => {
      return Boolean(document.querySelector('[dir="rtl"]'));
    });
    expect(hasRtl).toBeTruthy();
  });

  test("login page uses no garbled glyphs", async ({ page }) => {
    await page.goto("/login");
    const text = await page.locator("body").textContent();
    expect(text || "").not.toContain("\uFFFD");
  });
});
