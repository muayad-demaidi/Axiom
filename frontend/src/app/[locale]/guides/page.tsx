import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { getAllGuides } from "@/lib/content";
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
  const t = await getTranslations({ locale, namespace: "guides" });
  return pageMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: "/guides",
    locale: asLocale(locale),
  });
}

export default async function GuidesIndex({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "guides" });
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const guides = await getAllGuides();
  const crumbs = [{ href: "/", label: tNav("home") }, { label: tNav("guides") }];
  return (
    <MarketingShell current="/guides" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("indexEyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{t("indexTitle")}</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">{t("indexLead")}</p>
        <div className="grid gap-4 md:grid-cols-2 mt-10">
          {guides.map((g) => {
            const title = t.has(`items.${g.slug}.title` as never) ? t(`items.${g.slug}.title` as never) : g.data.title;
            const summary = t.has(`items.${g.slug}.summary` as never) ? t(`items.${g.slug}.summary` as never) : g.data.description;
            const estTime = t.has(`items.${g.slug}.estTime` as never) ? t(`items.${g.slug}.estTime` as never) : g.data.estTime;
            const difficulty = t.has(`items.${g.slug}.difficulty` as never) ? t(`items.${g.slug}.difficulty` as never) : g.data.difficulty;
            return (
              <Link key={g.slug} href={`/guides/${g.slug}`} className="card hover:ring-2 hover:ring-[var(--accent)] transition">
                <div className="flex gap-2 mb-2 text-xs font-mono text-[var(--text-muted)]">
                  <span>{estTime}</span>
                  <span>·</span>
                  <span>{difficulty}</span>
                </div>
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
