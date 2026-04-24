import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";
import { Breadcrumbs, breadcrumbsJsonLd } from "@/components/Breadcrumbs";
import { SITE } from "@/lib/site";

export const metadata = {
  title: "Features — every analysis tool, one workspace",
  description:
    "Auto cleaning pipeline, descriptive stats, visualizations, ML & K-Means clustering, predictions, and an AI assistant — all in one no-code workspace.",
  alternates: { canonical: SITE.url + "/features" },
};

const features = [
  { h: "Auto-cleaning pipeline", p: "Trim, dedupe, infer types, impute missing, and flag outliers as ordered, toggleable substeps with per-step impact metrics. Save as a reusable recipe." },
  { h: "Transform Toolkit", p: "Power Query–style: add column from examples, merge, split, replace, conditional column, group by — all reorderable in the Applied Steps editor." },
  { h: "Descriptive statistics", p: "Mean, median, mode, std, variance, skew, kurtosis, missing %, with currency codes and your number/date format applied automatically." },
  { h: "Correlations & distributions", p: "Find strong correlations and distribution shape across every numeric column in seconds." },
  { h: "Visualizations", p: "Bar, scatter, box, pie, line, heatmap — built with restrained, on-brand palettes. No 3D pie charts." },
  { h: "Time-period saving & comparison", p: "Save snapshots of your dataset and diff Q1 vs Q2 (or any range) on every column." },
  { h: "Predictions", p: "Linear models, trend analysis, growth metrics, CAGR — explained in plain English alongside the numbers." },
  { h: "ML & clustering", p: "K-Means risk clustering, RandomForest predictions, enhanced outlier detection, categorical insights." },
  { h: "AI chat assistant", p: "GPT-powered chat that knows your dataset. Ask questions, drive cleaning, generate reports — in any language." },
  { h: "Reports & PDF export", p: "Auto-generated executive summary with key findings, recommendations, and methodological caveats. PDF download." },
  { h: "Projects as folders", p: "Group datasets, chats, and saved analyses by project. Each project keeps its own context — no spillover." },
  { h: "Two product modes", p: "Guided Mode for non-specialists (chat-first). Expert Mode for the full dashboard with chat side-panel. Mode preference is per project." },
];

export default function FeaturesPage() {
  const crumbs = [{ href: "/", label: "Home" }, { label: "Features" }];
  return (
    <MarketingShell current="/features" jsonLd={breadcrumbsJsonLd(crumbs, SITE.url)}>
      <section className="container-x pt-10 pb-16">
        <Breadcrumbs items={crumbs} />
        <span className="eyebrow">Features</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">Every analysis tool, one workspace.</h1>
        <p className="mt-4 text-[var(--text-muted)] text-lg max-w-3xl">
          AXIOM bundles cleaning, transformation, statistics, visualizations, predictions, ML,
          and an AI chat assistant — all on the same project context, all reachable in two clicks.
        </p>
        <div className="grid gap-4 md:grid-cols-3 mt-10">
          {features.map((f) => (
            <div key={f.h} className="card">
              <h3>{f.h}</h3>
              <p>{f.p}</p>
            </div>
          ))}
        </div>
        <div className="mt-12 text-center">
          <Link className="btn btn-primary" href={SITE.appUrl}>Launch the app →</Link>
        </div>
      </section>
    </MarketingShell>
  );
}
