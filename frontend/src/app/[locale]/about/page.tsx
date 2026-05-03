import Link from "next/link";
import type { Metadata } from "next";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { SITE } from "@/lib/site";
import { pageMetadata } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  return pageMetadata({
    title: "About — building the analyst's missing copilot",
    description:
      "AXIOM is an analyst-built workspace that automates the boring 80% of data work and frees the human for the part that actually moves the business.",
    path: "/about",
    locale: asLocale(locale),
  });
}

export default function AboutPage() {
  const crumbs = [{ href: "/", label: "Home" }, { label: "About" }];
  return (
    <MarketingShell current="/about" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <article className="container-x pt-10 pb-16 max-w-3xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">About AXIOM</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">Built by analysts who got tired of the cleanup tax.</h1>
        <div className="prose-mark mt-8">
          <p>AXIOM started as one person&rsquo;s frustration with the gap between &ldquo;here is a CSV&rdquo; and &ldquo;here is what to do about it.&rdquo; That gap is usually filled with hours of cleaning, formatting, googling, and Excel formulas — and once it&rsquo;s done, the actual analytical thinking takes ten minutes.</p>
          <p>So we built the workspace we wanted: one place that ingests any CSV or Excel, runs a transparent cleaning pipeline you can audit step by step, computes the statistics that matter, draws restrained charts that don&rsquo;t look like a 2003 BI dashboard, runs ML when you need it, and lets you ask the data questions in plain English.</p>
          <h2>Who we serve</h2>
          <ul>
            <li><strong>Analysts &amp; ops people</strong> — clean, transform, profile, and ship findings without leaving the browser.</li>
            <li><strong>Founders &amp; PMs</strong> — get answers from your data without booking a meeting with the data team.</li>
            <li><strong>Students &amp; researchers</strong> — focus on the question, not the cleanup.</li>
          </ul>
          <h2>Our principles</h2>
          <ul>
            <li><strong>Transparency over magic.</strong> Every cleaning step, every transform, every ML decision is visible and toggleable.</li>
            <li><strong>Plain English by default.</strong> If a number can be explained in a sentence, it should be.</li>
            <li><strong>Performance is a feature.</strong> If a click takes more than a second, we treat it as a bug.</li>
          </ul>
        </div>
        <div className="mt-10 text-center">
          <Link className="btn btn-primary" href={SITE.appUrl}>Try AXIOM free for 60 days →</Link>
        </div>
      </article>
    </MarketingShell>
  );
}
