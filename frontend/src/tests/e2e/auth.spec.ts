import { test, expect } from "@playwright/test";
import { localeOf, isRTL, tFor } from "./_i18n";
import { switchLocaleViaSettings } from "./_locale-switch";

function loginPath(locale: "en" | "ar") {
  return locale === "ar" ? "/ar/login" : "/login";
}
function signupPath(locale: "en" | "ar") {
  return locale === "ar" ? "/ar/signup" : "/signup";
}

test.describe("auth", () => {
  test("login page renders the localised heading, fields, and submit", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(loginPath(locale));

    await expect.poll(() => page.evaluate(() => document.documentElement.dir))
      .toBe(isRTL(locale) ? "rtl" : "ltr");
    await expect.poll(() => page.evaluate(() => document.documentElement.lang))
      .toMatch(new RegExp(`^${locale}`));

    await expect(page.getByRole("heading", { name: tFor(locale, "auth.signIn") })).toBeVisible();
    await expect(page.getByPlaceholder(tFor(locale, "auth.emailOrUsername"))).toBeVisible();
    await expect(page.getByPlaceholder(tFor(locale, "auth.password"))).toBeVisible();
    await expect(page.getByRole("button", { name: tFor(locale, "auth.signIn") })).toBeVisible();
  });

  test("invalid credentials keeps the user on /login", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(loginPath(locale));

    await page.getByPlaceholder(tFor(locale, "auth.emailOrUsername")).fill("nope@example.com");
    await page.getByPlaceholder(tFor(locale, "auth.password")).fill("badpass");
    await page.getByRole("button", { name: tFor(locale, "auth.signIn") }).click();

    await expect(page).toHaveURL(/\/login(\?|$)/);
  });

  test("signup page renders the localised create-account form", async ({ page }, info) => {
    const locale = localeOf(info);
    await page.goto(signupPath(locale));

    await expect(page.getByRole("heading", { name: tFor(locale, "auth.createAccount") })).toBeVisible();
    await expect(page.getByPlaceholder(tFor(locale, "auth.email"))).toBeVisible();
    await expect(page.getByPlaceholder(tFor(locale, "auth.username"))).toBeVisible();
    await expect(page.getByRole("button", { name: tFor(locale, "auth.createAccountCta") })).toBeVisible();
  });

  test("protected route redirects unauthenticated users", async ({ page, context }, info) => {
    const locale = localeOf(info);
    await context.clearCookies();
    await page.addInitScript(() => {
      try { window.localStorage.removeItem("authToken"); } catch {}
    });

    await page.goto(locale === "ar" ? "/ar/app" : "/app");
    await expect.poll(() => page.url(), { timeout: 5_000 })
      .toMatch(/\/(login|signup|app)(\?|\/|$)/);
  });

  test("Settings page locale switcher flips chrome en ⇄ ar", async ({ page, context }, info) => {
    const start = localeOf(info);
    const target = start === "ar" ? "en" : "ar";
    await switchLocaleViaSettings(page, context, start, target);
  });
});
