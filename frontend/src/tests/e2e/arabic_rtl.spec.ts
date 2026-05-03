import { test, expect } from "@playwright/test";
import { localeOf, isRTL, tFor } from "./_i18n";

test.describe("locale + direction", () => {
  test("marketing root has the correct document direction + language", async ({ page, context }, info) => {
    const locale = localeOf(info);
    await context.addCookies([
      { name: "NEXT_LOCALE", value: locale, url: "http://localhost:3000" },
    ]);
    await page.goto(locale === "ar" ? "/ar" : "/");

    await expect.poll(() => page.evaluate(() => document.documentElement.dir))
      .toBe(isRTL(locale) ? "rtl" : "ltr");
    await expect.poll(() => page.evaluate(() => document.documentElement.lang))
      .toMatch(new RegExp(`^${locale}`));
  });

  test("login page uses no garbled glyphs in the active locale", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(locale === "ar" ? "/ar/login" : "/login");
    const text = (await page.locator("body").textContent()) || "";
    expect(text).not.toContain("\uFFFD");
  });

  test("AR marketing root renders the Arabic catalogue CTA", async ({ page }, info) => {
    test.skip(localeOf(info) !== "ar", "AR-only assertion");
    await page.goto("/ar");
    await expect(page.getByText(tFor("ar", "marketing.ctaLaunch")).first()).toBeVisible();
  });

  test("EN marketing root renders the English catalogue CTA", async ({ page }, info) => {
    test.skip(localeOf(info) !== "en", "EN-only assertion");
    await page.goto("/");
    await expect(page.getByText(tFor("en", "marketing.ctaLaunch")).first()).toBeVisible();
  });

  test("AR chrome stays in Western digits (no Arabic-Indic 0-9)", async ({ page }, info) => {
    test.skip(localeOf(info) !== "ar", "AR-only assertion");
    await page.goto("/ar");
    const text = (await page.locator("body").textContent()) || "";
    expect(text).not.toMatch(/[\u0660-\u0669]/);
  });
});
