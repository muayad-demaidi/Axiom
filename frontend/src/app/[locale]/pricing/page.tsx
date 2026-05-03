import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { FAQ } from "@/components/FAQ";
import { SITE } from "@/lib/site";
import { pageMetadata } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "pricing" });
  return pageMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: "/pricing",
    locale: asLocale(locale),
  });
}

export default async function PricingPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "pricing" });
  const tNav = await getTranslations({ locale, namespace: "nav" });

  const tiers = [
    {
      name: t("tier1Name"),
      price: t("freePrice"),
      summary: t("tier1Summary"),
      features: [t("tier1F1"), t("tier1F2"), t("tier1F3"), t("tier1F4"), t("tier1F5")],
    },
    {
      name: t("tier2Name"),
      price: t("tier2Price"),
      summary: t("tier2Summary"),
      features: [t("tier2F1"), t("tier2F2"), t("tier2F3"), t("tier2F4"), t("tier2F5"), t("tier2F6")],
      highlight: true,
    },
    {
      name: t("tier3Name"),
      price: t("tier3Price"),
      summary: t("tier3Summary"),
      features: [t("tier3F1"), t("tier3F2"), t("tier3F3"), t("tier3F4"), t("tier3F5"), t("tier3F6")],
    },
  ];

  const faq = [
    { q: t("faq1Q"), a: t("faq1A") },
    { q: t("faq2Q"), a: t("faq2A") },
    { q: t("faq3Q"), a: t("faq3A") },
    { q: t("faq4Q"), a: t("faq4A") },
  ];

  const crumbs = [{ href: "/", label: tNav("home") }, { label: tNav("pricing") }];
  const faqLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faq.map((f) => ({
      "@type": "Question",
      name: f.q,
      acceptedAnswer: { "@type": "Answer", text: f.a },
    })),
  };
  return (
    <MarketingShell current="/pricing" jsonLd={[breadcrumbsJsonLd(crumbs, SITE.url), faqLd]}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("eyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{t("title")}</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">
          {t("leadBefore")}
          <strong>{t("leadStrong")}</strong>
          {t("leadAfter")}
        </p>
        <div className="grid gap-4 md:grid-cols-3 mt-10">
          {tiers.map((tier) => (
            <div
              key={tier.name}
              className={`card flex flex-col ${tier.highlight ? "ring-2 ring-[var(--accent)]" : ""}`}
            >
              <h3 className="text-lg font-bold">{tier.name}</h3>
              <div className="text-3xl font-bold my-3">{tier.price}</div>
              <p className="text-sm text-[var(--text-muted)] mb-4">{tier.summary}</p>
              <ul className="space-y-2 text-sm flex-1">
                {tier.features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span className="text-[var(--accent)]">✓</span>
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                href={SITE.appUrl}
                className={`btn mt-5 ${tier.highlight ? "btn-primary" : "btn-ghost"}`}
              >
                {t("ctaTrial")}
              </Link>
            </div>
          ))}
        </div>
        <div className="mt-16">
          <FAQ items={faq} title={t("faqTitle")} />
        </div>
      </section>
    </MarketingShell>
  );
}
