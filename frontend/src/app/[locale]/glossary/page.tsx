import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getAllGlossary } from "@/lib/content";
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
  const t = await getTranslations({ locale, namespace: "glossary" });
  return pageMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: "/glossary",
    locale: asLocale(locale),
  });
}

export default async function GlossaryIndexPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "glossary" });
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const entries = await getAllGlossary();
  const crumbs = [{ href: "/", label: tNav("home") }, { label: tNav("glossary") }];
  return (
    <MarketingShell current="/glossary" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("eyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{t("indexTitle")}</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">{t("indexLead")}</p>
        <div className="grid gap-4 md:grid-cols-3 mt-10">
          {entries.map((e) => {
            const term = t.has(`items.${e.slug}.term` as never) ? t(`items.${e.slug}.term` as never) : e.data.term;
            const summary = t.has(`items.${e.slug}.summary` as never) ? t(`items.${e.slug}.summary` as never) : e.data.shortDef;
            return (
              <Link key={e.slug} href={`/glossary/${e.slug}`} className="card hover:ring-2 hover:ring-[var(--accent)] transition">
                <h3>{term}</h3>
                <p>{summary}</p>
              </Link>
            );
          })}
        </div>
      </section>
    </MarketingShell>
  );
}
