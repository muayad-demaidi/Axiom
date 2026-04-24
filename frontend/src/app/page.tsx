import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";
import { FAQ } from "@/components/FAQ";
import { DataStreamBackground } from "@/components/DataStreamBackground";
import { SITE } from "@/lib/site";

const faq = [
  { q: "Do I need to install anything?", a: "No. AXIOM runs in any modern browser on Mac, Windows, Linux, ChromeOS, or tablet." },
  { q: "What file formats are supported?", a: "CSV and Excel (.xlsx). Files up to 200 MB and 1,000,000 rows on Tier 3." },
  { q: "Is there a free trial?", a: "Yes — every new account gets 60 days of full Tier 3 access (AI chat, predictions, ML, and exports). No credit card required." },
  { q: "Where is my data stored?", a: "Your uploaded datasets are stored in our managed PostgreSQL database, accessible only to your account. You can delete a dataset at any time." },
  { q: "Do I need to know SQL or Python?", a: "No. The whole platform is built around clicking, toggling, and asking questions in plain English." },
];

export const metadata = {
  title: "AXIOM — Intelligent data analytics, no code required",
  description: SITE.description,
  alternates: { canonical: SITE.url + "/" },
};

export default function HomePage() {
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
      description: "60-day free trial with full Tier 3 access",
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
    <MarketingShell current="/" jsonLd={[softwareLd, faqLd]}>
      <section className="relative overflow-hidden">
        <DataStreamBackground />
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse at center, var(--surface) 0%, color-mix(in srgb, var(--surface) 70%, transparent) 45%, transparent 80%)",
          }}
          aria-hidden="true"
        />
        <div className="container-x relative py-20 md:py-28 text-center">
          <span className="eyebrow">AXIOM · v2026.4</span>
          <h1 className="text-4xl md:text-6xl font-bold mt-3 leading-tight">
            From <span className="text-[var(--accent)]">raw spreadsheet</span> to clean,
            AI-explained insight in <span className="text-[var(--accent)]">seconds</span>.
          </h1>
          <p className="mt-6 max-w-2xl mx-auto text-[var(--text-muted)] text-lg">
            Upload a CSV or Excel file. AXIOM automatically cleans, profiles, and analyses it —
            then explains what matters in plain English with built-in AI chat, predictions, and clustering.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            <Link className="btn btn-primary" href={SITE.appUrl}>Launch the app — 60 days free →</Link>
            <Link className="btn btn-ghost" href="/features">See features</Link>
          </div>
          <p className="mt-3 text-xs text-[var(--text-muted)]">No credit card. Full Tier 3 features during the trial.</p>
        </div>
      </section>

      <section className="container-x py-16">
        <span className="eyebrow">Why AXIOM</span>
        <h2 className="text-2xl md:text-3xl font-bold mt-2 mb-8">
          Analysts spend up to 80% of their time cleaning data. We built the other 80% back.
        </h2>
        <div className="grid gap-4 md:grid-cols-4">
          <div className="card"><h3>Auto-cleaning pipeline</h3><p>Trim, dedupe, infer types, impute missing values, and flag outliers as an ordered, reorderable list of toggleable substeps.</p></div>
          <div className="card"><h3>Statistics & profiling</h3><p>Descriptive stats, correlations, and distributions on every column — with currency codes and your preferred number/date formats applied automatically.</p></div>
          <div className="card"><h3>ML & clustering</h3><p>K-Means risk clustering, RandomForest predictions, enhanced outlier detection — without leaving the analysis page.</p></div>
          <div className="card"><h3>AI that knows your data</h3><p>Built-in GPT chat that answers questions about <em>your</em> dataset, plus auto-generated reports with recommendations.</p></div>
        </div>
      </section>

      <section className="container-x py-16">
        <span className="eyebrow">How it works</span>
        <h2 className="text-2xl md:text-3xl font-bold mt-2 mb-8">Three clicks, not three sprints.</h2>
        <div className="grid gap-4 md:grid-cols-3">
          <div className="card"><h3>1. Upload</h3><p>Drag any CSV or Excel file (up to 200 MB on Tier 3). Encoding and delimiter are detected automatically.</p></div>
          <div className="card"><h3>2. Auto-analyse</h3><p>Cleaning, statistics, charts, ML, and predictions run on demand — toggleable step by step so you stay in control.</p></div>
          <div className="card"><h3>3. Ask anything</h3><p>Chat with the AI assistant in natural language. Export a polished report when leadership needs an answer.</p></div>
        </div>
      </section>

      <section className="container-x py-16">
        <FAQ items={faq} />
      </section>

      <section className="container-x py-16">
        <div className="card text-center">
          <h2 className="text-2xl font-bold mb-2">Ready to stop wrangling and start analysing?</h2>
          <p className="text-[var(--text-muted)] mb-4">60 days of full Tier 3 access. No credit card.</p>
          <Link className="btn btn-primary" href={SITE.appUrl}>Launch the app →</Link>
        </div>
      </section>
    </MarketingShell>
  );
}
