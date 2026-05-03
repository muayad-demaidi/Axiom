import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";
import { getAllGlossary, getAllGuides, getAllCompare } from "@/lib/content";
import { LOCALES, DEFAULT_LOCALE } from "@/i18n/config";

function parseUpdated(s: string | undefined): Date {
  if (!s) return new Date(SITE.defaultUpdated);
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? new Date(SITE.defaultUpdated) : d;
}

// Build a sitemap entry that lists every locale variant of the same
// route under `alternates.languages` so search engines understand the
// EN/AR pair (mirrors `localePrefix: "as-needed"` from the middleware
// and the `pageMetadata` helper). Default-locale URL has no prefix.
function localizedEntry(
  base: string,
  path: string,
  lastModified: Date,
  changeFrequency: MetadataRoute.Sitemap[number]["changeFrequency"],
  priority: number,
): MetadataRoute.Sitemap[number] {
  const cleanPath = path === "/" ? "" : path;
  const languages: Record<string, string> = {};
  for (const loc of LOCALES) {
    languages[loc] = loc === DEFAULT_LOCALE
      ? `${base}${cleanPath || "/"}`
      : `${base}/${loc}${cleanPath}`;
  }
  return {
    url: `${base}${cleanPath || "/"}`,
    lastModified,
    changeFrequency,
    priority,
    alternates: { languages },
  };
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = SITE.url.replace(/\/$/, "");
  const [glossary, guides, compare] = await Promise.all([
    getAllGlossary(),
    getAllGuides(),
    getAllCompare(),
  ]);
  const newest = (xs: { data: { updated: string } }[]) =>
    xs.reduce<Date>((acc, x) => {
      const d = parseUpdated(x.data.updated);
      return d > acc ? d : acc;
    }, new Date(SITE.defaultUpdated));

  const baseUpdated = new Date(SITE.defaultUpdated);
  const staticEntries: MetadataRoute.Sitemap = [
    localizedEntry(base, "/",         baseUpdated,        "weekly",  1.0),
    localizedEntry(base, "/features", baseUpdated,        "monthly", 0.9),
    localizedEntry(base, "/pricing",  baseUpdated,        "monthly", 0.9),
    localizedEntry(base, "/about",    baseUpdated,        "yearly",  0.6),
    localizedEntry(base, "/contact",  baseUpdated,        "yearly",  0.5),
    localizedEntry(base, "/glossary", newest(glossary),  "weekly",  0.8),
    localizedEntry(base, "/guides",   newest(guides),    "weekly",  0.7),
    localizedEntry(base, "/compare",  newest(compare),   "weekly",  0.8),
  ];
  const dyn: MetadataRoute.Sitemap = [
    ...glossary.map((e) => localizedEntry(base, `/glossary/${e.slug}`, parseUpdated(e.data.updated), "monthly", 0.7)),
    ...guides.map((e)   => localizedEntry(base, `/guides/${e.slug}`,   parseUpdated(e.data.updated), "monthly", 0.7)),
    ...compare.map((e)  => localizedEntry(base, `/compare/${e.slug}`,  parseUpdated(e.data.updated), "monthly", 0.7)),
  ];
  return [...staticEntries, ...dyn];
}
