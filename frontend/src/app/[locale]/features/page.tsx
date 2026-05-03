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
  const t = await getTranslations({ locale, namespace: "features" });
  return pageMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: "/features",
    locale: asLocale(locale),
  });
}

export default async function FeaturesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "features" });
  const tNav = await getTranslations({ locale, namespace: "nav" });

  const features = Array.from({ length: 12 }, (_, i) => ({
    h: t(`item${i + 1}H` as `item${number}H`),
    p: t(`item${i + 1}P` as `item${number}P`),
  }));

  const crumbs = [{ href: "/", label: tNav("home") }, { label: tNav("features") }];
  return (
    <MarketingShell current="/features" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("eyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{t("title")}</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">{t("lead")}</p>
        <div className="grid gap-4 md:grid-cols-3 mt-10">
          {features.map((f) => (
            <div key={f.h} className="card">
              <h3>{f.h}</h3>
              <p>{f.p}</p>
            </div>
          ))}
        </div>
        <div className="mt-12 text-center">
          <Link className="btn btn-primary" href={SITE.appUrl}>{t("ctaLaunch")}</Link>
        </div>
      </section>
    </MarketingShell>
  );
}
