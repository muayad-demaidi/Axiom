import Link from "next/link";
import { notFound } from "next/navigation";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getCompareEntry, listCompareSlugs } from "@/lib/content";
import { SITE } from "@/lib/site";
import { localizedAlternates } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export const revalidate = 3600;
export const dynamicParams = false;

export async function generateStaticParams() {
  const slugs = await listCompareSlugs();
  return slugs.map((slug) => ({ slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug: string; locale?: string }>;
}) {
  const { slug, locale } = await params;
  const entry = await getCompareEntry(slug);
  if (!entry) return {};
  const alternates = localizedAlternates(`/compare/${entry.slug}`, asLocale(locale));
  return {
    title: entry.data.title,
    description: entry.data.description,
    alternates,
  };
}

export default async function CompareEntryPage({
  params,
}: {
  params: Promise<{ slug: string; locale: string }>;
}) {
  const { slug, locale } = await params;
  const entry = await getCompareEntry(slug);
  if (!entry) notFound();
  const t = await getTranslations({ locale, namespace: "compare" });
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const isAr = asLocale(locale) === "ar";

  const title = t.has(`items.${entry.slug}.title` as never) ? t(`items.${entry.slug}.title` as never) : entry.data.title;
  const crumbs = [
    { href: "/", label: tNav("home") },
    { href: "/compare", label: tNav("compare") },
    { label: t("vsLabel", { competitor: entry.data.competitor }) },
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
  const ld = [breadcrumbsJsonLd(crumbs, SITE.url), ...(faqLd ? [faqLd] : [])];
  return (
    <MarketingShell current="/compare" jsonLd={ld}>
      <article className="container-x pt-10 pb-16 max-w-4xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("entryEyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{title}</h1>
        <p className="mt-4 text-lg text-[var(--text-muted)]" lang="en" dir="ltr">{entry.data.intro}</p>
        {isAr && (
          <div className="card mt-6 text-sm" role="note" lang="ar" dir="rtl">
            {t("translationInProgress")}
          </div>
        )}
        <div className="grid gap-4 md:grid-cols-2 mt-8">
          <div className="card">
            <span className="eyebrow">{t("bestForUs")}</span>
            <p className="mt-2" lang="en" dir="ltr">{entry.data.bestFor.us}</p>
          </div>
          <div className="card">
            <span className="eyebrow">{t("bestForThem", { competitor: entry.data.competitor })}</span>
            <p className="mt-2" lang="en" dir="ltr">{entry.data.bestFor.them}</p>
          </div>
        </div>
        {entry.data.rows.length > 0 && (
          <section className="mt-12">
            <h2 className="text-2xl font-bold mb-4">{t("featureByFeature")}</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-[var(--border)] rounded">
                <thead>
                  <tr className="bg-[var(--surface-alt)]">
                    <th className="text-left p-3 border-b border-[var(--border)]">{t("featureCol")}</th>
                    <th className="text-left p-3 border-b border-[var(--border)]">{t("axiomCol")}</th>
                    <th className="text-left p-3 border-b border-[var(--border)]">{entry.data.competitor}</th>
                  </tr>
                </thead>
                <tbody lang="en" dir="ltr">
                  {entry.data.rows.map((r, i) => (
                    <tr key={i} className="border-b border-[var(--border)]">
                      <td className="p-3 font-medium">{r.feature}</td>
                      <td className="p-3 text-[var(--text-muted)]">{r.us}</td>
                      <td className="p-3 text-[var(--text-muted)]">{r.them}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
        <section className="mt-12 grid gap-4 md:grid-cols-2">
          <div className="card">
            <h3 className="font-bold mb-2">{t("chooseAxiomWhen")}</h3>
            <ul className="space-y-2 text-sm text-[var(--text-muted)]" lang="en" dir="ltr">
              {entry.data.whenToChoose.us.map((u, i) => <li key={i}>• {u}</li>)}
            </ul>
          </div>
          <div className="card">
            <h3 className="font-bold mb-2">{t("chooseThemWhen", { competitor: entry.data.competitor })}</h3>
            <ul className="space-y-2 text-sm text-[var(--text-muted)]" lang="en" dir="ltr">
              {entry.data.whenToChoose.them.map((u, i) => <li key={i}>• {u}</li>)}
            </ul>
          </div>
        </section>
        <div className="prose-mark mt-12" lang="en" dir="ltr" dangerouslySetInnerHTML={{ __html: entry.html }} />
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
        {(entry.data.relatedGlossary.length > 0 || entry.data.relatedGuides.length > 0) && (
          <section className="mt-12">
            <h2 className="text-2xl font-bold mb-4">{t("relatedHeading")}</h2>
            <ul className="space-y-2 text-[var(--accent)]">
              {entry.data.relatedGlossary.map((r) => (
                <li key={r}><Link href={`/glossary/${r}`}>{t("relatedGlossaryLink", { slug: r })}</Link></li>
              ))}
              {entry.data.relatedGuides.map((r) => (
                <li key={r}><Link href={`/guides/${r}`}>{t("relatedGuideLink", { slug: r })}</Link></li>
              ))}
            </ul>
          </section>
        )}
        <p className="mt-12 text-xs text-[var(--text-muted)]">{t("lastUpdated", { date: entry.data.updated })}</p>
      </article>
    </MarketingShell>
  );
}
