import type { Metadata } from "next";
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
  return pageMetadata({
    title: "Contact",
    description: "Get in touch with the AXIOM team for support, partnerships, or feedback.",
    path: "/contact",
    locale: asLocale(locale),
  });
}

export default function ContactPage() {
  const crumbs = [{ href: "/", label: "Home" }, { label: "Contact" }];
  return (
    <MarketingShell current="/contact" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16 max-w-2xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">Contact</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">Talk to us.</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg">
          Support, feedback, or partnership — send a message and we&rsquo;ll reply within one business day.
        </p>

        <ContactForm />

        <div className="card mt-6">
          <p className="text-sm text-[var(--text-muted)] mb-2">Prefer email?</p>
          <a className="text-[var(--accent)] text-lg font-semibold" href={`mailto:${SITE.supportEmail}`}>
            {SITE.supportEmail}
          </a>
        </div>
      </section>
    </MarketingShell>
  );
}
