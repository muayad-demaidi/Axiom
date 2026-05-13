import { getRequestConfig } from "next-intl/server";
import { asLocale, DEFAULT_LOCALE } from "./config";

/**
 * Per-request next-intl configuration.
 *
 * Resolves the active locale from the URL segment (set by the
 * middleware) and lazily loads the matching message catalogue.
 * Falls back to the default locale if the segment is unrecognised
 * so accidental URLs (typos, stale bookmarks) still render copy.
 */
export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = asLocale(requested ?? DEFAULT_LOCALE);
  const messages = (await import(`../../messages/${locale}.json`)).default;
  return { locale, messages };
});
