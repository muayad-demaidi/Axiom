/**
 * Playwright-side i18n helper (Task #275).
 *
 * E2E specs are parameterised by Playwright project metadata (set in
 * `playwright.config.ts` as `metadata.e2eLocale`). Specs use
 * `t(testInfo, key)` to look up the expected user-visible string from
 * the same `messages/{locale}` catalogue the production app uses.
 *
 * Missing keys throw — never silently fall back to the dotted path,
 * because that would let real bugs hide behind passing tests.
 */
import type { TestInfo } from "@playwright/test";
import enMessages from "../../../messages/en.json";
import arMessages from "../../../messages/ar.json";

export type Locale = "en" | "ar";

const CATALOGUES: Record<Locale, unknown> = {
  en: enMessages,
  ar: arMessages,
};

export function localeOf(info: TestInfo): Locale {
  const m = (info.project.metadata as { e2eLocale?: string } | undefined)?.e2eLocale;
  return m === "ar" ? "ar" : "en";
}

export function isRTL(locale: Locale): boolean {
  return locale === "ar";
}

function lookup(catalogue: unknown, dottedKey: string): string {
  const parts = dottedKey.split(".");
  let cur: unknown = catalogue;
  for (const p of parts) {
    if (cur && typeof cur === "object" && p in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[p];
      continue;
    }
    throw new Error(`[e2e/i18n] missing translation key: "${dottedKey}"`);
  }
  if (typeof cur !== "string") {
    throw new Error(`[e2e/i18n] key "${dottedKey}" did not resolve to a string`);
  }
  return cur;
}

function interpolate(template: string, values?: Record<string, unknown>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => {
    const v = values[k];
    if (v == null) {
      throw new Error(
        `[e2e/i18n] missing value for placeholder "{${k}}" in "${template}"`,
      );
    }
    return String(v);
  });
}

export function t(
  info: TestInfo,
  key: string,
  values?: Record<string, unknown>,
): string {
  return interpolate(lookup(CATALOGUES[localeOf(info)], key), values);
}

export function tFor(
  locale: Locale,
  key: string,
  values?: Record<string, unknown>,
): string {
  return interpolate(lookup(CATALOGUES[locale], key), values);
}
