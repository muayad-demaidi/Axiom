import Link from "next/link";
import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { FAQ } from "@/components/FAQ";
import { DataStreamBackground } from "@/components/DataStreamBackground";
import { SITE } from "@/lib/site";
import { pageMetadata } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const t = await getTranslations("marketing");
  const { locale } = await params;
  return pageMetadata({
    title: t("homeTitle"),
    description: SITE.description,
    path: "/",
    locale: asLocale(locale),
  });
}

export default async function HomePage() {
  const t = await getTranslations("marketing");
  const faq = [
    { q: t("faqQ1"), a: t("faqA1") },
    { q: t("faqQ2"), a: t("faqA2") },
    { q: t("faqQ3"), a: t("faqA3") },
    { q: t("faqQ4"), a: t("faqA4") },
    { q: t("faqQ5"), a: t("faqA5") },
  ];
  const softwareLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "AXIOM",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    url: SITE.url,
    description: SITE.description,
    offers: {
      "@type": "Offer",
      price: "0",
      priceCurrency: "USD",
      description: t("offerDescription"),
    },
    featureList: [
      "Auto data cleaning pipeline",
      "Descriptive statistics",
      "Interactive visualizations",
      "ML & K-Means clustering",
      "Predictive analytics",
      "AI chat assistant",
      "Time-period comparison",
      "Export reports",
    ],
  };
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
    <>
      <div className="fixed inset-0 z-0 pointer-events-none overflow-hidden" aria-hidden="true">
        <DataStreamBackground />
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse 70% 50% at 50% 40%, color-mix(in srgb, var(--surface) 65%, transparent) 0%, color-mix(in srgb, var(--surface) 30%, transparent) 55%, transparent 100%)",
          }}
        />
      </div>
      <div className="relative z-10">
      <MarketingShell current="/" jsonLd={[softwareLd, faqLd]}>
      <section className="relative overflow-hidden min-h-[560px] md:min-h-[640px] flex items-center">
        <div className="container-x relative py-16 md:py-20 text-center w-full">
          <span className="eyebrow">{t("eyebrowVersion")}</span>
          <h1 className="text-4xl md:text-6xl font-bold mt-3 leading-tight">
            {t("heroPart1")} <span className="text-[var(--accent)]">{t("heroPart2")}</span>{" "}
            {t("heroPart3")} <span className="text-[var(--accent)]">{t("heroPart4")}</span>.
          </h1>
          <p className="mt-6 max-w-2xl mx-auto text-[var(--text-muted)] text-lg">
            {t("heroSubtitle")}
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link className="btn btn-primary" href={SITE.appUrl}>{t("ctaLaunch")}</Link>
            <Link className="btn btn-ghost" href="/features">{t("ctaSeeFeatures")}</Link>
          </div>
          <p className="mt-3 text-xs text-[var(--text-muted)]">{t("noCardNote")}</p>
        </div>
      </section>

      <section className="container-x py-16">
        <span className="eyebrow">{t("whyEyebrow")}</span>
        <h2 className="text-2xl md:text-3xl font-bold mt-2 mb-8">
          {t("whyTitle")}
        </h2>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="card"><h3>{t("whyCleanTitle")}</h3><p>{t("whyCleanBody")}</p></div>
          <div className="card"><h3>{t("whyStatsTitle")}</h3><p>{t("whyStatsBody")}</p></div>
          <div className="card"><h3>{t("whyMlTitle")}</h3><p>{t("whyMlBody")}</p></div>
          <div className="card">
            <h3>{t("whyAiTitle")}</h3>
            <p dangerouslySetInnerHTML={{ __html: t.raw("whyAiBodyHtml") }} />
          </div>
        </div>
      </section>

      <section className="container-x py-16">
        <span className="eyebrow">{t("howEyebrow")}</span>
        <h2 className="text-2xl md:text-3xl font-bold mt-2 mb-8">{t("howTitle")}</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card"><h3>{t("howStep1Title")}</h3><p>{t("howStep1Body")}</p></div>
          <div className="card"><h3>{t("howStep2Title")}</h3><p>{t("howStep2Body")}</p></div>
          <div className="card"><h3>{t("howStep3Title")}</h3><p>{t("howStep3Body")}</p></div>
        </div>
      </section>

      <section className="container-x py-16">
        <FAQ items={faq} />
      </section>

      <section className="container-x py-16">
        <div className="card text-center">
          <h2 className="text-2xl font-bold mb-2">{t("ctaTitle")}</h2>
          <p className="text-[var(--text-muted)] mb-4">{t("ctaSubtitle")}</p>
          <Link className="btn btn-primary" href={SITE.appUrl}>{t("ctaButton")}</Link>
        </div>
      </section>
    </MarketingShell>
      </div>
    </>
  );
}
