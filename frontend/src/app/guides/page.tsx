import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getAllGuides } from "@/lib/content";
import { SITE } from "@/lib/site";

export const revalidate = 3600;

export const metadata = {
  title: "Guides — practical data analysis walkthroughs",
  description: "Step-by-step walkthroughs for cleaning, analysing, and acting on data with AXIOM.",
  alternates: { canonical: SITE.url + "/guides" },
};

export default async function GuidesIndex() {
  const guides = await getAllGuides();
  const crumbs = [{ href: "/", label: "Home" }, { label: "Guides" }];
  return (
    <MarketingShell current="/guides" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">Guides</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">Step-by-step playbooks.</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">
          Practical walkthroughs that take you from a messy spreadsheet to an actionable answer
          — using AXIOM&rsquo;s built-in cleaning, statistics, and AI assistant.
        </p>
        <div className="grid gap-4 md:grid-cols-2 mt-10">
          {guides.map((g) => (
            <Link key={g.slug} href={`/guides/${g.slug}`} className="card hover:ring-2 hover:ring-[var(--accent)] transition">
              <div className="flex gap-2 mb-2 text-xs font-mono text-[var(--text-muted)]">
                <span>{g.data.estTime}</span>
                <span>·</span>
                <span>{g.data.difficulty}</span>
              </div>
              <h3>{g.data.title}</h3>
              <p>{g.data.description}</p>
            </Link>
          ))}
        </div>
      </section>
    </MarketingShell>
  );
}
