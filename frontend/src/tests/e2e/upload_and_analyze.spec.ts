import { test, expect } from "@playwright/test";
import { localeOf, isRTL, tFor } from "./_i18n";
import { switchLocaleViaSettings } from "./_locale-switch";

test.describe("upload and analyze", () => {
  test("upload page renders the localised dropzone copy + direction", async ({ page, context }, info) => {
    const locale = localeOf(info);
    await context.addCookies([
      { name: "NEXT_LOCALE", value: locale, url: "http://localhost:3000" },
    ]);
    await page.goto(locale === "ar" ? "/ar/app/upload" : "/app/upload");

    if (/\/login/.test(page.url())) {
      await expect(page.getByRole("heading", { name: tFor(locale, "auth.signIn") })).toBeVisible();
    } else {
      const dropRe = new RegExp(
        [tFor(locale, "upload.dropAreaGuided"), tFor(locale, "upload.dropAreaExpert")]
          .map((s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
          .join("|"),
      );
      await expect(page.getByText(dropRe).first()).toBeVisible();
    }

    await expect.poll(() => page.evaluate(() => document.documentElement.dir))
      .toBe(isRTL(locale) ? "rtl" : "ltr");
  });

  test("upload flow exercises the Settings locale switcher", async ({ page, context }, info) => {
    const start = localeOf(info);
    const target = start === "ar" ? "en" : "ar";
    await switchLocaleViaSettings(page, context, start, target);
  });
});
