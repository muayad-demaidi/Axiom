import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
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
  const t = await getTranslations({ locale, namespace: "about" });
  return pageMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: "/about",
    locale: asLocale(locale),
  });
}

export default async function AboutPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "about" });
  const tNav = await getTranslations({ locale, namespace: "nav" });

  const crumbs = [{ href: "/", label: tNav("home") }, { label: tNav("about") }];
  return (
    <MarketingShell current="/about" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <article className="container-x pt-10 pb-16 max-w-3xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("eyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{t("title")}</h1>
        <div className="prose-mark mt-8">
          <p>{t("p1")}</p>
          <p>{t("p2")}</p>
          <h2>{t("whoTitle")}</h2>
          <ul>
            <li><strong>{t("who1Strong")}</strong> — {t("who1Body")}</li>
            <li><strong>{t("who2Strong")}</strong> — {t("who2Body")}</li>
            <li><strong>{t("who3Strong")}</strong> — {t("who3Body")}</li>
          </ul>
          <h2>{t("principlesTitle")}</h2>
          <ul>
            <li><strong>{t("principle1Strong")}</strong> {t("principle1Body")}</li>
            <li><strong>{t("principle2Strong")}</strong> {t("principle2Body")}</li>
            <li><strong>{t("principle3Strong")}</strong> {t("principle3Body")}</li>
          </ul>
        </div>
        <div className="mt-10 text-center">
          <Link className="btn btn-primary" href={SITE.appUrl}>{t("ctaTrial")}</Link>
        </div>
      </article>
    </MarketingShell>
  );
}
