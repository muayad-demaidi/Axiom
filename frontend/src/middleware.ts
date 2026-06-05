import createMiddleware from "next-intl/middleware";
import { LOCALES, DEFAULT_LOCALE } from "./i18n/config";

/**
 * Top-level middleware: defer locale routing entirely to next-intl.
 *
 * English is served prefix-free (`/app`, `/pricing`) and Arabic under
 * the `/ar` prefix (`/ar/app`, `/ar/pricing`) per `localePrefix:
 * "as-needed"`. Arabic is RTL — the `<html dir>` is set in the locale
 * layout from `localeDir()`.
 */
const intlMiddleware = createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "as-needed",
  localeDetection: false,
});

export default intlMiddleware;

export const config = {
  // Skip Next internals, the API proxy, and any static assets.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
