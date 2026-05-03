import Link from "next/link";
import type { Metadata } from "next";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getAllCompare } from "@/lib/content";
import { SITE } from "@/lib/site";
import { pageMetadata } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  return pageMetadata({
    title: "Compare AXIOM with other tools",
    description: "Honest, side-by-side comparisons of AXIOM with Power BI, Tableau, Excel, Google Sheets, and Looker Studio.",
    path: "/compare",
    locale: asLocale(locale),
  });
}

export default async function CompareIndex() {
  const items = await getAllCompare();
  const crumbs = [{ href: "/", label: "Home" }, { label: "Compare" }];
  return (
    <MarketingShell current="/compare" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">Compare</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">How AXIOM stacks up.</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">
          Honest, side-by-side comparisons. We&rsquo;ll tell you when the other tool is the better choice.
        </p>
        <div className="grid gap-4 md:grid-cols-2 mt-10">
          {items.map((c) => (
            <Link key={c.slug} href={`/compare/${c.slug}`} className="card hover:ring-2 hover:ring-[var(--accent)] transition">
              <h3>AXIOM vs {c.data.competitor}</h3>
              <p>{c.data.description}</p>
            </Link>
          ))}
        </div>
      </section>
    </MarketingShell>
  );
}
