import Link from "next/link";
import type { Metadata } from "next";
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
  return pageMetadata({
    title: "Pricing — start free for 60 days",
    description:
      "Three transparent tiers, every account starts with 60 days of full Tier 3 access. No credit card required.",
    path: "/pricing",
    locale: asLocale(locale),
  });
}

const tiers = [
  {
    name: "Tier 1 — Starter", price: "Free",
    summary: "For anyone who wants to try the cleaning + statistics workflow.",
    features: ["Up to 10,000 rows / dataset", "Up to 25 MB upload", "Cleaning + statistics + basic charts", "5 saved analyses", "Community support"],
  },
  {
    name: "Tier 2 — Pro", price: "$19/mo",
    summary: "For analysts who need the full transform & visualisation toolkit.",
    features: ["Up to 250,000 rows / dataset", "Up to 75 MB upload", "All visualisations + transform toolkit", "Unlimited saved analyses", "Time-period comparison", "Email support"],
    highlight: true,
  },
  {
    name: "Tier 3 — Pro+", price: "$49/mo",
    summary: "Predictive ML, AI chat, and reports for teams that ship insight to leadership.",
    features: ["Up to 1,000,000 rows / dataset", "Up to 200 MB upload", "AI chat assistant + GPT auto-reports", "Predictions, K-Means, RandomForest", "PDF export with branding", "Priority support"],
  },
];

const faq = [
  { q: "Do I really get Tier 3 free for 60 days?", a: "Yes. Every new account is granted Tier 3 capabilities for 60 days, no credit card required. After day 60, you choose a plan or downgrade to Tier 1 (free)." },
  { q: "Can I downgrade or cancel anytime?", a: "Yes. Your data stays accessible at the lower-tier limits; nothing is deleted." },
  { q: "Is there a discount for students or non-profits?", a: "Yes — please reach out to support and tell us about your work." },
  { q: "Where is my data stored?", a: "All datasets and accounts are stored in our managed PostgreSQL database. You can delete a dataset or your entire account at any time." },
];

export default function PricingPage() {
  const crumbs = [{ href: "/", label: "Home" }, { label: "Pricing" }];
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
        <span className="eyebrow">Pricing</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">Start free. Stay free if you want.</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">
          Every new account gets <strong>60 days of full Tier 3 access</strong> — predictions,
          AI chat, and exports included. No card on file.
        </p>
        <div className="grid gap-4 md:grid-cols-3 mt-10">
          {tiers.map((t) => (
            <div key={t.name} className={`card flex flex-col ${t.highlight ? "ring-2 ring-[var(--accent)]" : ""}`}>
              <h3 className="text-lg font-bold">{t.name}</h3>
              <div className="text-3xl font-bold my-3">{t.price}</div>
              <p className="text-sm text-[var(--text-muted)] mb-4">{t.summary}</p>
              <ul className="space-y-2 text-sm flex-1">
                {t.features.map((f) => (
                  <li key={f} className="flex gap-2"><span className="text-[var(--accent)]">✓</span>{f}</li>
                ))}
              </ul>
              <Link href={SITE.appUrl} className={`btn mt-5 ${t.highlight ? "btn-primary" : "btn-ghost"}`}>
                Start 60-day free trial →
              </Link>
            </div>
          ))}
        </div>
        <div className="mt-16">
          <FAQ items={faq} />
        </div>
      </section>
    </MarketingShell>
  );
}
