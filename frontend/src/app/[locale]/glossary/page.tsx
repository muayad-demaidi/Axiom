import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getAllGlossary } from "@/lib/content";
import { SITE } from "@/lib/site";

export const revalidate = 3600;

export const metadata = {
  title: "Glossary — data analytics terms explained",
  description: "Plain-English definitions for the terms data analysts actually use, with stats, FAQs, and how-to context.",
  alternates: { canonical: SITE.url + "/glossary" },
};

export default async function GlossaryIndexPage() {
  const entries = await getAllGlossary();
  const crumbs = [{ href: "/", label: "Home" }, { label: "Glossary" }];
  return (
    <MarketingShell current="/glossary" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">Glossary</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">Data analytics, defined.</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">
          Plain-English explanations of the concepts that show up in every analyst&rsquo;s job —
          with current stats, links to deeper guides, and how AXIOM handles them.
        </p>
        <div className="grid gap-4 md:grid-cols-3 mt-10">
          {entries.map((e) => (
            <Link key={e.slug} href={`/glossary/${e.slug}`} className="card hover:ring-2 hover:ring-[var(--accent)] transition">
              <h3>{e.data.term}</h3>
              <p>{e.data.shortDef}</p>
            </Link>
          ))}
        </div>
      </section>
    </MarketingShell>
  );
}
