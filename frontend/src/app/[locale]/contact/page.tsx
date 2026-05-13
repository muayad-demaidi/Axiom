import type { Metadata } from "next";
import { getTranslations } from "next-intl/server";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { SITE } from "@/lib/site";
import { ContactForm } from "@/components/ContactForm";
import { pageMetadata } from "@/lib/seo";
import { asLocale } from "@/i18n/config";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "contact" });
  return pageMetadata({
    title: t("metaTitle"),
    description: t("metaDescription"),
    path: "/contact",
    locale: asLocale(locale),
  });
}

export default async function ContactPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "contact" });
  const tNav = await getTranslations({ locale, namespace: "nav" });
  const crumbs = [{ href: "/", label: tNav("home") }, { label: tNav("contact") }];
  return (
    <MarketingShell current="/contact" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16 max-w-2xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">{t("eyebrow")}</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">{t("title")}</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg">{t("lead")}</p>

        <ContactForm />

        <div className="card mt-6">
          <p className="text-sm text-[var(--text-muted)] mb-2">{t("preferEmail")}</p>
          <a
            className="text-[var(--accent)] text-lg font-semibold"
            href={`mailto:${SITE.supportEmail}`}
          >
            {SITE.supportEmail}
          </a>
        </div>
      </section>
    </MarketingShell>
  );
}
