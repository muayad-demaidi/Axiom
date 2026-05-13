import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    // Block the authenticated workspace, the API proxy, and locale-
    // prefixed copies of the same so /ar/app/* doesn't leak into the
    // index either. Public marketing routes (incl. /ar/<page>) stay
    // crawlable.
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/app/", "/api/", "/ar/app/", "/ar/api/"],
      },
    ],
    sitemap: SITE.url.replace(/\/$/, "") + "/sitemap.xml",
    host: SITE.url,
  };
}
