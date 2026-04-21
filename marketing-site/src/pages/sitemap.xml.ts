import type { APIRoute } from "astro";
import { SITE } from "../utils/site";
import { GLOSSARY } from "../content/glossary";
import { COMPARE } from "../content/compare";
import { GUIDES } from "../content/guides";

const STATIC = [
  { path: "/", priority: 1.0 },
  { path: "/features", priority: 0.9 },
  { path: "/pricing", priority: 0.9 },
  { path: "/about", priority: 0.6 },
  { path: "/contact", priority: 0.5 },
  { path: "/glossary", priority: 0.8 },
  { path: "/compare", priority: 0.7 },
  { path: "/guides", priority: 0.8 },
];

export const GET: APIRoute = () => {
  const today = new Date().toISOString().slice(0, 10);
  const urls: { loc: string; lastmod: string; priority: number }[] = [];

  for (const s of STATIC) {
    urls.push({ loc: SITE.url + s.path, lastmod: today, priority: s.priority });
  }
  for (const g of GLOSSARY) {
    urls.push({ loc: `${SITE.url}/glossary/${g.slug}`, lastmod: g.updated, priority: 0.7 });
  }
  for (const c of COMPARE) {
    urls.push({ loc: `${SITE.url}/compare/${c.slug}`, lastmod: c.updated, priority: 0.7 });
  }
  for (const g of GUIDES) {
    urls.push({ loc: `${SITE.url}/guides/${g.slug}`, lastmod: g.updated, priority: 0.7 });
  }

  const body =
    `<?xml version="1.0" encoding="UTF-8"?>\n` +
    `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n` +
    urls
      .map(
        (u) =>
          `  <url><loc>${u.loc}</loc><lastmod>${u.lastmod}</lastmod><priority>${u.priority.toFixed(1)}</priority></url>`
      )
      .join("\n") +
    `\n</urlset>\n`;

  return new Response(body, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
};
