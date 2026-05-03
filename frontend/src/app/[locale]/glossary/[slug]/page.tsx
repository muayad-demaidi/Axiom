import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getGlossaryEntry, listGlossarySlugs } from "@/lib/content";
import { SITE } from "@/lib/site";
import { localizedAlternates } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export const revalidate = 3600;
export const dynamicParams = false;

export async function generateStaticParams() {
  const slugs = await listGlossarySlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; locale?: string }>;
}) {
  const { slug, locale } = await params;
  const entry = await getGlossaryEntry(slug);
  if (!entry) return {};
  const alternates = localizedAlternates(`/glossary/${entry.slug}`, asLocale(locale));
  return {
    title: `${entry.data.term} — ${entry.data.question}`,
    description: entry.data.description,
    alternates,
  };
}

export default async function GlossaryEntryPage({
  params,
}: {
  params: Promise<{ slug: string; locale: string }>;
}) {
  const { slug, locale } = await params;
  const entry = await getGlossaryEntry(slug);
  if (!entry) notFound();
  const t = await getTranslations({ locale, namespace: "glossary" });
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const isAr = false;

  const term = t.has(`items.${entry.slug}.term` as never) ? t(`items.${entry.slug}.term` as never) : entry.data.term;
  const summary = t.has(`items.${entry.slug}.summary` as never) ? t(`items.${entry.slug}.summary` as never) : entry.data.shortDef;
  const crumbs = [
    { href: "/", label: tNav("home") },
    { href: "/glossary", label: tNav("glossary") },
    { label: term },
  ];
  const faqLd = entry.data.faq.length
    ? {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        mainEntity: entry.data.faq.map((f) => ({
          "@type": "Question",
          name: f.q,
          acceptedAnswer: { "@type": "Answer", text: f.a },
        })),
      }
    : null;
  const articleLd = {
    "@context": "https://schema.org",
    "@type": "DefinedTerm",
    name: entry.data.term,
    description: entry.data.shortDef,
    inDefinedTermSet: SITE.url + "/glossary",
    url: `${SITE.url}/glossary/${entry.slug}`,
  };
  const ld = [breadcrumbsJsonLd(crumbs, SITE.url), articleLd, ...(faqLd ? [faqLd] : []), ...(entry.data.jsonLd ?? [])];
  return (
    <MarketingShell current="/glossary" jsonLd={ld}>
      <article className="container-x pt-10 pb-16 max-w-3xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("eyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{term}</h1>
        <p className="mt-3 text-lg text-[var(--text-muted)]">{summary}</p>
        {isAr && (
          <div className="card mt-6 text-sm" role="note" lang="ar" dir="rtl">
            {t("translationInProgress")}
          </div>
        )}
        <div className="prose-mark mt-8" lang="en" dir="ltr" dangerouslySetInnerHTML={{ __html: entry.html }} />
        {entry.data.stats.length > 0 && (
          <section className="mt-10">
            <h2 className="text-2xl font-bold mb-4">{t("byTheNumbers")}</h2>
            <div className="grid gap-4 md:grid-cols-3">
              {entry.data.stats.map((s) => (
                <div key={s.label} className="card">
                  <div className="text-3xl font-bold text-[var(--accent)]">{s.value}</div>
                  <div className="text-sm mt-1" lang="en" dir="ltr">{s.label}</div>
                  <a href={s.source.url} rel="nofollow noopener" className="text-xs text-[var(--text-muted)] mt-2 underline" lang="en" dir="ltr">
                    {t("sourcePrefix", { label: s.source.label })}
                  </a>
                </div>
              ))}
            </div>
          </section>
        )}
        {entry.data.faq.length > 0 && (
          <section className="mt-12">
            <h2 className="text-2xl font-bold mb-4">{t("faqHeading")}</h2>
            <div className="space-y-3" lang="en" dir="ltr">
              {entry.data.faq.map((f) => (
                <details key={f.q} className="card">
                  <summary className="cursor-pointer font-semibold">{f.q}</summary>
                  <p className="mt-2 text-[var(--text-muted)] text-sm">{f.a}</p>
                </details>
              ))}
            </div>
          </section>
        )}
        {(entry.data.relatedGuides.length > 0 || entry.data.relatedCompare.length > 0 || entry.data.related.length > 0) && (
          <section className="mt-12">
            <h2 className="text-2xl font-bold mb-4">{t("relatedHeading")}</h2>
            <ul className="space-y-2 text-[var(--accent)]">
              {entry.data.related.map((r) => (
                <li key={r}><Link href={`/glossary/${r}`}>{t("relatedGlossaryLink", { slug: r })}</Link></li>
              ))}
              {entry.data.relatedGuides.map((r) => (
                <li key={r}><Link href={`/guides/${r}`}>{t("relatedGuideLink", { slug: r })}</Link></li>
              ))}
              {entry.data.relatedCompare.map((r) => (
                <li key={r}><Link href={`/compare/${r}`}>{t("relatedCompareLink", { slug: r })}</Link></li>
              ))}
            </ul>
          </section>
        )}
        <p className="mt-12 text-xs text-[var(--text-muted)]">{t("lastUpdated", { date: entry.data.updated })}</p>
      </article>
    </MarketingShell>
  );
}
