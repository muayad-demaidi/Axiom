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
 *  - Any legacy `/ar/*` URL (from bookmarks, search results, or
 *    cookies set before we removed Arabic) is redirected to the
 *    English equivalent so users never land on a 404.
 *  - All other requests fall through to the next-intl middleware.
 */
export default function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  if (pathname === "/ar" || pathname.startsWith("/ar/")) {
    const stripped = pathname === "/ar" ? "/" : pathname.slice(3);
    const url = request.nextUrl.clone();
    url.pathname = stripped || "/";
    url.search = search;
    return NextResponse.redirect(url);
  }
  return intlMiddleware(request);
}

export const config = {
  // Skip Next internals, the API proxy, and any static assets.
  matcher: ["/((?!api|_next|_vercel|.*\\..*).*)"],
};
