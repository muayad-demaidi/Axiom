/**
 * Static i18n configuration shared by middleware, request helpers,
 * and any client-side locale switcher.
 *
 * Keep this file dependency-free so it can be imported from edge
 * runtimes (middleware), the React tree, and unit tests alike.
 */

export const LOCALES = ["en", "ar"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";

/** Locales whose script flows right-to-left. */
export const RTL_LOCALES: ReadonlyArray<Locale> = ["ar"];

/** `<html dir>` value for the active locale. */
export function localeDir(locale: string): "ltr" | "rtl" {
  return RTL_LOCALES.includes(locale as Locale) ? "rtl" : "ltr";
}

/** Narrow an arbitrary string to a supported locale (or fall back). */
export function asLocale(value: string | undefined | null): Locale {
  if (value && (LOCALES as readonly string[]).includes(value)) {
    return value as Locale;
  }
  return DEFAULT_LOCALE;
}

/** Cookie name next-intl reads/writes for the user's locale preference. */
export const LOCALE_COOKIE = "NEXT_LOCALE";

/**
 * Strip the optional `/<locale>` prefix from a pathname so legacy
 * route-matching code (regexes like `^/app/project/(\d+)`, exact
 * comparisons against `/app/upload`, etc.) keeps working under any
 * locale. Returns the canonical "/app/..." (or "/") form.
 *
 * Examples:
 *   stripLocale("/ar/app/project/12") === "/app/project/12"
 *   stripLocale("/app/upload")         === "/app/upload"
 *   stripLocale("/ar")                 === "/"
 */
export function stripLocale(pathname: string | null | undefined): string {
  if (!pathname) return "/";
  for (const loc of LOCALES) {
    if (pathname === `/${loc}`) return "/";
    const prefix = `/${loc}/`;
    if (pathname.startsWith(prefix)) return pathname.slice(loc.length + 1);
  }
  return pathname;
}
