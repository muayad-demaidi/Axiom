/**
 * Locale switching is no longer a user-facing feature — the app is
 * English-only. This stub keeps the existing e2e specs compiling and
 * is a no-op at runtime so the rest of each spec still exercises the
 * feature it actually targets.
 */
import type { BrowserContext, Page } from "@playwright/test";

export async function switchLocaleViaSettings(
  _page: Page,
  _context: BrowserContext,
  _start: string,
  _target: string,
): Promise<void> {
  return;
}
