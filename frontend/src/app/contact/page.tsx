import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { SITE } from "@/lib/site";

export const metadata = {
  title: "Contact",
  description: "Get in touch with the AXIOM team for support, partnerships, or feedback.",
  alternates: { canonical: SITE.url + "/contact" },
};

export default function ContactPage() {
  const crumbs = [{ href: "/", label: "Home" }, { label: "Contact" }];
  return (
    <MarketingShell current="/contact" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16 max-w-2xl">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">Contact</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">Talk to us.</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg">
          Support, feedback, or partnership — email us and we&rsquo;ll reply within one business day.
        </p>
        <div className="card mt-8">
          <p className="text-sm text-[var(--text-muted)] mb-2">Email</p>
          <a className="text-[var(--accent)] text-lg font-semibold" href={`mailto:${SITE.supportEmail}`}>
            {SITE.supportEmail}
          </a>
        </div>
      </section>
    </MarketingShell>
  );
}
