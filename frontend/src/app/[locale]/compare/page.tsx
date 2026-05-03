import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
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
  const t = await getTranslations({ locale, namespace: "compare" });
  return pageMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: "/compare",
    locale: asLocale(locale),
  });
}

export default async function CompareIndex({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "compare" });
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const items = await getAllCompare();
  const crumbs = [{ href: "/", label: tNav("home") }, { label: tNav("compare") }];
  return (
    <MarketingShell current="/compare" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("indexEyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{t("indexTitle")}</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">{t("indexLead")}</p>
        <div className="grid gap-4 md:grid-cols-2 mt-10">
          {items.map((c) => {
            const title = t.has(`items.${c.slug}.title` as never)
              ? t(`items.${c.slug}.title` as never)
              : t("indexCardTitle", { competitor: c.data.competitor });
            const summary = t.has(`items.${c.slug}.summary` as never)
              ? t(`items.${c.slug}.summary` as never)
              : c.data.description;
            return (
              <Link key={c.slug} href={`/compare/${c.slug}`} className="card hover:ring-2 hover:ring-[var(--accent)] transition">
                <h3>{title}</h3>
                <p>{summary}</p>
              </Link>
            );
          })}
        </div>
      </section>
    </MarketingShell>
  );
}
