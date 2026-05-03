import { defineConfig, devices } from "@playwright/test";

/**
 * Two Playwright projects so the same specs run under the new EN
 * default *and* the existing AR locale (Task #275). Specs read
 * expected text from `messages/{locale}.json` via the helper at
 * `src/tests/utils/i18n.ts`, and pick up the active locale from
 * `process.env.E2E_LOCALE` which each project sets below.
 */
export default defineConfig({
  testDir: "./src/tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  reporter: [["html", { open: "never" }], ["list"]],
  use: {
    baseURL: "http://localhost:3000",
    timezoneId: "Asia/Riyadh",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npm run dev:e2e",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    {
      name: "chromium-en",
      use: {
        ...devices["Desktop Chrome"],
        locale: "en",
        extraHTTPHeaders: { "Accept-Language": "en" },
      },
      metadata: { e2eLocale: "en" },
    },
    {
      name: "chromium-ar",
      use: {
        ...devices["Desktop Chrome"],
        locale: "ar",
        extraHTTPHeaders: { "Accept-Language": "ar" },
      },
      metadata: { e2eLocale: "ar" },
    },
  ],
});
