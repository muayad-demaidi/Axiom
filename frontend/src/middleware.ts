import { NextResponse, type NextRequest } from "next/server";
import createMiddleware from "next-intl/middleware";
import { LOCALES, DEFAULT_LOCALE } from "./i18n/config";

const intlMiddleware = createMiddleware({
  locales: [...LOCALES],
  defaultLocale: DEFAULT_LOCALE,
  localePrefix: "as-needed",
  localeDetection: false,
});

/**
 * Top-level middleware:
 *  - Requests fall through to the next-intl middleware.
 */
export default function middleware(request: NextRequest) {
  return intlMiddleware(request);
}

export const config = {
  // Skip Next internals, the API proxy, and any static assets.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
