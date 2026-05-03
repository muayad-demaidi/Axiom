import { defineConfig, devices } from "@playwright/test";
const exe = "/nix/store/qa9cnw4v5xkxyip6mb9kxqfq1z4x2dx1-chromium-138.0.7204.100/bin/chromium";
export default defineConfig({
  testDir: "./src/tests/e2e",
  timeout: 60_000,
  fullyParallel: false,
  reporter: [["list"]],
  use: { baseURL: "http://localhost:5000", timezoneId: "Asia/Riyadh", launchOptions: { executablePath: exe } },
  projects: [
    { name: "chromium-en", use: { ...devices["Desktop Chrome"], locale: "en", extraHTTPHeaders: { "Accept-Language": "en" }, launchOptions: { executablePath: exe } }, metadata: { e2eLocale: "en" } },
    { name: "chromium-ar", use: { ...devices["Desktop Chrome"], locale: "ar", extraHTTPHeaders: { "Accept-Language": "ar" }, launchOptions: { executablePath: exe } }, metadata: { e2eLocale: "ar" } },
  ],
});
