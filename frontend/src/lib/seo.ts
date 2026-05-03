import type { Metadata } from "next";
import { SITE } from "@/lib/site";
import { LOCALES, DEFAULT_LOCALE, type Locale } from "@/i18n/config";

/**
 * Build canonical URL + hreflang `alternates.languages` map for a
 * marketing page. Mirrors `next-intl`'s `localePrefix: "as-needed"`
 * routing — the default locale (English) lives at the bare path,
 * other locales sit under `/<locale>`.
 *
 * Used by `generateMetadata` on every public marketing route so
 * search engines see one canonical URL per locale and Google can
 * pick the right one per user (Task #276 SEO hardening).
 */
export function localizedAlternates(
  path: string,
  locale: string = DEFAULT_LOCALE,
): NonNullable<Metadata["alternates"]> {
  const base = SITE.url.replace(/\/$/, "");
  const cleanPath = path === "/" ? "" : path.startsWith("/") ? path : `/${path}`;
  const canonical = locale === DEFAULT_LOCALE
    ? `${base}${cleanPath || "/"}`
    : `${base}/${locale}${cleanPath}`;
  const languages: Record<string, string> = {};
  for (const loc of LOCALES) {
    languages[loc] = loc === DEFAULT_LOCALE
      ? `${base}${cleanPath || "/"}`
      : `${base}/${loc}${cleanPath}`;
  }
  // x-default points search engines at the locale-neutral fallback.
  languages["x-default"] = `${base}${cleanPath || "/"}`;
  return { canonical, languages };
}

/**
 * Build a full per-page Metadata object: canonical + hreflang +
 * OpenGraph + Twitter card. Page-level OG/Twitter overrides the
 * site-level defaults inherited from `[locale]/layout.tsx` so each
 * route gets a tailored social card.
 */
export function pageMetadata(opts: {
  title: string;
  description: string;
  path: string;
  locale?: Locale;
  image?: string;
}): Metadata {
  const { title, description, path, locale = DEFAULT_LOCALE, image = SITE.socialImage } = opts;
  const alternates = localizedAlternates(path, locale);
  const url = (alternates.canonical as string) || SITE.url;
  return {
    title,
    description,
    alternates,
    openGraph: {
      title,
      description,
      url,
      siteName: SITE.name,
      images: [image],
      type: "website",
      locale: "en_US",
    },
    twitter: {
      card: "summary_large_image",
      title,
      description,
      images: [image],
    },
  };
}
