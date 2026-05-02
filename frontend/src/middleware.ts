import createMiddleware from "next-intl/middleware";
import { LOCALES, DEFAULT_LOCALE } from "./i18n/config";

/**
 * next-intl middleware.
 *
 *   * `localePrefix: "as-needed"` keeps existing English URLs (`/`,
 *     `/app/dashboard`, …) untouched while serving the Arabic
 *     variant under `/ar/…`. Users with a `NEXT_LOCALE=ar` cookie
 *     get redirected to the prefixed URL automatically.
 *   * `localeDetection: true` lets the browser's Accept-Language
 *     header bootstrap the first visit; the cookie / explicit
 *     selection wins after that.
 */
export default createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "as-needed",
  localeDetection: true,
});

export const config = {
  // Skip Next internals, the API proxy, and any static assets.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
