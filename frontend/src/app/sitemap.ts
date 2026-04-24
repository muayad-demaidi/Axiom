import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";
import { getAllGlossary, getAllGuides, getAllCompare } from "@/lib/content";

function parseUpdated(s: string | undefined): Date {
  if (!s) return new Date(SITE.defaultUpdated);
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? new Date(SITE.defaultUpdated) : d;
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
    { url: `${base}/`,         lastModified: baseUpdated,        changeFrequency: "weekly",  priority: 1.0 },
    { url: `${base}/features`, lastModified: baseUpdated,        changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/pricing`,  lastModified: baseUpdated,        changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/about`,    lastModified: baseUpdated,        changeFrequency: "yearly",  priority: 0.6 },
    { url: `${base}/contact`,  lastModified: baseUpdated,        changeFrequency: "yearly",  priority: 0.5 },
    { url: `${base}/glossary`, lastModified: newest(glossary),  changeFrequency: "weekly",  priority: 0.8 },
    { url: `${base}/guides`,   lastModified: newest(guides),    changeFrequency: "weekly",  priority: 0.7 },
    { url: `${base}/compare`,  lastModified: newest(compare),   changeFrequency: "weekly",  priority: 0.8 },
  ];
  const dyn: MetadataRoute.Sitemap = [
    ...glossary.map((e) => ({ url: `${base}/glossary/${e.slug}`, lastModified: parseUpdated(e.data.updated), changeFrequency: "monthly" as const, priority: 0.7 })),
    ...guides.map((e)   => ({ url: `${base}/guides/${e.slug}`,   lastModified: parseUpdated(e.data.updated), changeFrequency: "monthly" as const, priority: 0.7 })),
    ...compare.map((e)  => ({ url: `${base}/compare/${e.slug}`,  lastModified: parseUpdated(e.data.updated), changeFrequency: "monthly" as const, priority: 0.7 })),
  ];
  return [...staticEntries, ...dyn];
}
