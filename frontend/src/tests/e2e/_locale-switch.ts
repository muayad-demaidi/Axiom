import { expect, type BrowserContext, type Page } from "@playwright/test";
import { isRTL, tFor, type Locale } from "./_i18n";

// Drive the Settings → Language UI and assert the chrome re-rendered.
export async function switchLocaleViaSettings(
  page: Page,
  context: BrowserContext,
  start: Locale,
  target: Locale,
): Promise<void> {
  let savedLocale: string | null = null;
  await page.route("**/api/auth/me", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: 1, email: "demo@axiom.app", locale: start }),
    }),
  );
  await page.route("**/api/users/me/locale", async (route) => {
    const body = JSON.parse(route.request().postData() || "{}");
    savedLocale = body.locale ?? null;
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: 1,
        email: "demo@axiom.app",
        locale: savedLocale ?? start,
      }),
    });
  });

  await context.addCookies([
    { name: "NEXT_LOCALE", value: start, url: "http://localhost:3000" },
  ]);
  await page.addInitScript(() => {
    try {
      window.localStorage.setItem("axiom_token", "e2e-token");
    } catch {}
  });

  const settingsPath = start === "ar" ? "/ar/app/settings" : "/app/settings";
  await page.goto(settingsPath);

  // Settings page is rendered even without a real token; the form
  // stays usable (the API PATCH is skipped when `authed` is false).
  await page
    .locator(`#locale-${target}`)
    .waitFor({ state: "visible", timeout: 10_000 });
  await page.locator(`#locale-${target}`).check();
  await page
    .getByRole("button", { name: tFor(start, "common.save") })
    .click();

  await expect.poll(() => savedLocale, { timeout: 10_000 }).toBe(target);

  await expect
    .poll(() => page.evaluate(() => document.documentElement.dir), {
      timeout: 10_000,
    })
    .toBe(isRTL(target) ? "rtl" : "ltr");
  await expect
    .poll(() => page.evaluate(() => document.documentElement.lang))
    .toMatch(new RegExp(`^${target}`));

  // Sanity-check that *some* chrome string from the target catalogue
  // is now rendered, proving the catalogue swap landed (not just the
  // <html> attributes).
  await expect(
    page
      .getByText(tFor(target, "settings.languageSection"))
      .first(),
  ).toBeVisible({ timeout: 5_000 });
}
