import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getGuideEntry, listGuideSlugs } from "@/lib/content";
import { SITE } from "@/lib/site";
import { localizedAlternates } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export const revalidate = 3600;
export const dynamicParams = false;

export async function generateStaticParams() {
  const slugs = await listGuideSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; locale?: string }>;
}) {
  const { slug, locale } = await params;
  const entry = await getGuideEntry(slug);
  if (!entry) return {};
  const alternates = localizedAlternates(`/guides/${entry.slug}`, asLocale(locale));
  return {
    title: entry.data.title,
    description: entry.data.description,
    alternates,
  };
}

export default async function GuideEntryPage({
  params,
}: {
  params: Promise<{ slug: string; locale: string }>;
}) {
  const { slug, locale } = await params;
  const entry = await getGuideEntry(slug);
  if (!entry) notFound();
  const t = await getTranslations({ locale, namespace: "guides" });
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const isAr = false;

  const title = t.has(`items.${entry.slug}.title` as never) ? t(`items.${entry.slug}.title` as never) : entry.data.title;
  const estTime = t.has(`items.${entry.slug}.estTime` as never) ? t(`items.${entry.slug}.estTime` as never) : entry.data.estTime;
  const difficulty = t.has(`items.${entry.slug}.difficulty` as never) ? t(`items.${entry.slug}.difficulty` as never) : entry.data.difficulty;
  const crumbs = [
    { href: "/", label: tNav("home") },
    { href: "/guides", label: tNav("guides") },
    { label: title },
  ];
  const articleLd = {
    "@context": "https://schema.org",
    "@type": "Article",
    headline: entry.data.title,
    description: entry.data.description,
    datePublished: entry.data.updated,
    dateModified: entry.data.updated,
    author: { "@type": "Organization", name: SITE.name },
    url: `${SITE.url}/guides/${entry.slug}`,
  };
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
  const ld = [breadcrumbsJsonLd(crumbs, SITE.url), articleLd, ...(faqLd ? [faqLd] : []), ...(entry.data.jsonLd ?? [])];
  return (
    <MarketingShell current="/guides" jsonLd={ld}>
      <article className="container-x pt-10 pb-16 max-w-3xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("guideEyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{title}</h1>
        <div className="flex gap-3 mt-3 text-xs font-mono text-[var(--text-muted)]">
          <span>{estTime}</span>
          <span>·</span>
          <span>{difficulty}</span>
        </div>
        <p className="mt-4 text-lg text-[var(--text-muted)]" lang="en" dir="ltr">{entry.data.intro}</p>
        {isAr && (
          <div className="card mt-6 text-sm" role="note" lang="ar" dir="rtl">
            {t("translationInProgress")}
          </div>
        )}
        {entry.data.prerequisites.length > 0 && (
          <div className="card mt-6">
            <strong>{t("prerequisitesLabel")}</strong>
            <ul className="list-disc pl-6 mt-2 text-sm text-[var(--text-muted)]" lang="en" dir="ltr">
              {entry.data.prerequisites.map((p) => <li key={p}>{p}</li>)}
            </ul>
          </div>
        )}
        <div className="prose-mark mt-8" lang="en" dir="ltr" dangerouslySetInnerHTML={{ __html: entry.html }} />
        {entry.data.pitfalls.length > 0 && (
          <section className="mt-10">
            <h2 className="text-2xl font-bold mb-4">{t("pitfallsHeading")}</h2>
            <ul className="space-y-2 list-disc pl-6 text-[var(--text-muted)]" lang="en" dir="ltr">
              {entry.data.pitfalls.map((p) => <li key={p}>{p}</li>)}
            </ul>
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
        {(entry.data.relatedGlossary.length > 0 || entry.data.relatedCompare.length > 0) && (
          <section className="mt-12">
            <h2 className="text-2xl font-bold mb-4">{t("relatedHeading")}</h2>
            <ul className="space-y-2 text-[var(--accent)]">
              {entry.data.relatedGlossary.map((r) => (
                <li key={r}><Link href={`/glossary/${r}`}>{t("relatedGlossaryLink", { slug: r })}</Link></li>
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
