/**
 * Test-side i18n helper (Task #223 follow-up).
 *
 * Loads the same JSON catalogues the production app uses so component
 * and end-to-end tests can assert against translation keys instead of
 * literal strings.
 *
 * Usage:
 *   import { t } from "@/tests/utils/i18n";
 *   expect(screen.getByText(t("en", "settings.title"))).toBeInTheDocument();
 *
 * - Missing keys throw loudly. We never silently fall back to the key
 *   path because that would let real bugs hide behind passing tests.
 * - Placeholder substitution uses the same `{name}` syntax next-intl
 *   exposes; numbers/booleans/strings are coerced via String().
 */
import enMessages from "../../../messages/en.json";
import arMessages from "../../../messages/ar.json";

export type Locale = "en" | "ar";

const CATALOGUES: Record<Locale, unknown> = {
  en: enMessages,
  ar: arMessages,
};

export const LOCALES: readonly Locale[] = ["en", "ar"] as const;

function lookup(catalogue: unknown, dottedKey: string): string {
  const parts = dottedKey.split(".");
  let cur: unknown = catalogue;
  for (const p of parts) {
    if (cur && typeof cur === "object" && p in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[p];
      continue;
    }
    throw new Error(`[tests/i18n] missing translation key: "${dottedKey}"`);
  }
  if (typeof cur !== "string") {
    throw new Error(
      `[tests/i18n] key "${dottedKey}" did not resolve to a string`,
    );
  }
  return cur;
}

function interpolate(template: string, values?: Record<string, unknown>): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => {
    const v = values[k];
    if (v == null) {
      throw new Error(
        `[tests/i18n] missing value for placeholder "{${k}}" in "${template}"`,
      );
    }
    return String(v);
  });
}

export function t(
  locale: Locale,
  key: string,
  values?: Record<string, unknown>,
): string {
  const cat = CATALOGUES[locale];
  return interpolate(lookup(cat, key), values);
}
