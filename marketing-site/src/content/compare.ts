export type Row = { feature: string; us: string; them: string };
export type Compare = {
  slug: string;
  competitor: string;
  title: string;
  description: string;
  intro: string; // 40-60 word direct answer
  bestFor: { us: string; them: string };
  rows: Row[];
  whenToChoose: { us: string[]; them: string[] };
  faq: { q: string; a: string }[];
  updated: string;
};

export const COMPARE: Compare[] = [
  {
    slug: "datavision-pro-vs-tableau",
    competitor: "Tableau",
    title: "DataVision Pro vs Tableau",
    description:
      "DataVision Pro vs Tableau — an honest, side-by-side comparison of pricing, AI features, learning curve, and ideal users. No fluff, no fake testimonials.",
    intro:
      "DataVision Pro is an AI-first analytics platform built around one-click cleaning, statistics, and natural-language insights. Tableau is a mature, dashboard-first BI platform that excels at curated, enterprise-grade visual analytics. The right pick depends on whether you need fast answers from raw files (DataVision Pro) or governed dashboards across many sources (Tableau).",
    bestFor: {
      us: "Analysts who upload CSV/Excel files and need clean data, statistics, ML, and AI explanations in one place — fast.",
      them: "BI teams building governed, reusable dashboards for hundreds of business users on top of a curated data warehouse.",
    },
    rows: [
      { feature: "Primary use case", us: "Ad-hoc analysis of files", them: "Enterprise BI dashboards" },
      { feature: "Setup time", us: "Sign up → upload → insights in minutes", them: "Server install + data modelling first; days to weeks" },
      { feature: "Auto data cleaning", us: "Built-in toggleable cleaning pipeline", them: "Tableau Prep is a separate paid product" },
      { feature: "AI chat over your data", us: "Built-in (GPT-powered)", them: "Tableau Pulse / Einstein, separately licensed [verify]" },
      { feature: "ML & clustering", us: "K-Means + RandomForest in-app", them: "External via Tableau Einstein or R/Python integrations" },
      { feature: "Pricing model", us: "60-day free Tier 3 trial; tiered free access", them: "Subscription seat-based, per Tableau public pricing" },
      { feature: "Best with", us: "CSV, Excel, ad-hoc analysis", them: "Modeled warehouse data (Snowflake, BigQuery)" },
      { feature: "Mobile / responsive", us: "Web app, mobile-friendly", them: "Native mobile apps + Tableau Server" },
      { feature: "Learning curve", us: "No drag-and-drop required", them: "Steeper — VizQL, calculated fields, LOD expressions" },
    ],
    whenToChoose: {
      us: [
        "You work in CSV / Excel and want answers, not pixel-perfect dashboards.",
        "You want AI-generated insights and recommendations alongside the chart.",
        "You're a single analyst or small team without a BI engineer.",
        "You need cleaning, stats, and ML in one tool with no extra licences.",
      ],
      them: [
        "You're standing up enterprise BI for hundreds of users on a governed warehouse.",
        "You need granular row-level security, version control, and certified data sources.",
        "You have, or are willing to hire, dedicated Tableau developers.",
        "Your stakeholders demand pixel-perfect, reusable visualisations.",
      ],
    },
    faq: [
      { q: "Is DataVision Pro a Tableau replacement?", a: "For ad-hoc file analysis, yes. For enterprise BI on top of a curated warehouse with hundreds of viewers, Tableau is still the heavier-duty platform." },
      { q: "Can I use both?", a: "Absolutely. Many teams use DataVision Pro for fast exploration and prototyping, then push the validated dataset and metric definitions into Tableau for company-wide dashboards." },
      { q: "Which is cheaper for a 5-person team?", a: "DataVision Pro — 60-day full-feature trial and free tiers afterward. Tableau Creator licences run several hundred dollars per user per year. [verify against current Tableau pricing]" },
      { q: "Does DataVision Pro connect to a warehouse?", a: "Today it imports CSV / Excel uploads. Direct warehouse connectors are on the roadmap." },
    ],
    updated: "2026-04-15",
  },
  {
    slug: "datavision-pro-vs-power-bi",
    competitor: "Power BI",
    title: "DataVision Pro vs Power BI",
    description:
      "DataVision Pro vs Microsoft Power BI — compare AI features, ease of use, file-based analysis, and ideal team size. No fabricated metrics.",
    intro:
      "DataVision Pro is a browser-first analytics tool focused on uploading a file and getting cleaned data, statistics, ML, and AI insights immediately. Power BI is Microsoft's full BI platform, deeply integrated with Excel, Microsoft 365, and Azure. Pick DataVision Pro for speed and AI; pick Power BI for ecosystem fit inside a Microsoft shop.",
    bestFor: {
      us: "Teams that live in spreadsheets and want AI-explained analysis without modelling a dataset first.",
      them: "Organisations standardised on Microsoft 365 / Azure that need DAX-powered, governed BI across the company.",
    },
    rows: [
      { feature: "File upload analysis", us: "Drag CSV/XLSX → instant analysis", them: "Power Query → load → model → visualise" },
      { feature: "Cleaning pipeline", us: "Toggleable, reorderable substeps", them: "Power Query (M language)" },
      { feature: "AI insights", us: "GPT-powered chat + auto report", them: "Copilot for Power BI (separate licence) [verify]" },
      { feature: "Predictive models", us: "Built-in linear / RandomForest / K-Means", them: "Requires Azure ML or R/Python visuals" },
      { feature: "Microsoft 365 integration", us: "Email exports + CSV downloads", them: "Native — Teams, SharePoint, Excel" },
      { feature: "Mobile editing", us: "Browser-based, responsive", them: "View on mobile; authoring is desktop-only (Windows)" },
      { feature: "Pricing entry point", us: "60-day free Tier 3 trial", them: "Power BI Pro per-user / Premium per-capacity" },
      { feature: "Learning curve", us: "No DAX, no formula language", them: "DAX + M required for non-trivial work" },
    ],
    whenToChoose: {
      us: [
        "Your data lives in spreadsheets and you want results without a modelling step.",
        "You want AI summaries and recommendations baked into every chart.",
        "You're not on a Windows desktop, or you work cross-platform.",
        "You don't have time to learn DAX.",
      ],
      them: [
        "You're a Microsoft 365 / Azure shop with existing Power BI investment.",
        "You need DAX-grade modelling and row-level security at enterprise scale.",
        "Your reports must live next to Teams, SharePoint, and Excel.",
        "You have a BI team that already speaks DAX and M.",
      ],
    },
    faq: [
      { q: "Can I open a Power BI .pbix in DataVision Pro?", a: "No. DataVision Pro consumes CSV and Excel files directly. Export your Power BI dataset to CSV/XLSX to bring it in." },
      { q: "Does DataVision Pro need Windows?", a: "No. It runs in any modern browser on Mac, Linux, ChromeOS, Windows, and tablets." },
      { q: "Is Power BI free?", a: "Power BI Desktop is free; sharing and collaboration require Power BI Pro or Premium licences. [verify against current Microsoft pricing]" },
      { q: "Which has better AI?", a: "Both ship AI features. DataVision Pro builds AI into every analysis page out of the box; Power BI Copilot is powerful but typically requires additional licences and a Premium capacity." },
    ],
    updated: "2026-04-15",
  },
  {
    slug: "datavision-pro-vs-excel",
    competitor: "Excel",
    title: "DataVision Pro vs Excel",
    description:
      "DataVision Pro vs Excel — when to leave the spreadsheet behind for AI cleaning, ML, and reproducible analysis on larger files.",
    intro:
      "Excel is the world's most beloved analytics tool — and at large file sizes, repeated cleaning, or when you need real ML, it starts to creak. DataVision Pro picks up where Excel slows down: ingest large CSVs, run automated cleaning, generate predictions, and explain results with AI — without writing a single VBA macro.",
    bestFor: {
      us: "Analysts pushing past Excel's row limits, or anyone who reruns the same cleaning pipeline every month.",
      them: "Quick calculations, simple lookups, financial modelling, and anything under ~100k rows.",
    },
    rows: [
      { feature: "Max practical rows", us: "Up to 1,000,000 (Tier 3)", them: "1,048,576 hard cap; degrades well before that" },
      { feature: "File size", us: "Up to 200 MB (Tier 3)", them: "Practical limit ~50 MB before instability" },
      { feature: "Repeatable cleaning", us: "Saved cleaning recipes", them: "Manual or VBA / Power Query" },
      { feature: "Built-in ML", us: "K-Means, RandomForest, linear models", them: "None natively (Analysis ToolPak is descriptive only)" },
      { feature: "AI chat over data", us: "Built-in", them: "Copilot in Excel 365 (separate licence) [verify]" },
      { feature: "Time-period comparison", us: "Built-in dataset history", them: "Manual workbook compare" },
      { feature: "Collaboration", us: "Web link, role-based access", them: "Excellent via Microsoft 365 / Sheets" },
      { feature: "Audit trail", us: "Step history per dataset", them: "Cell history limited; tracked changes patchy" },
    ],
    whenToChoose: {
      us: [
        "Your file no longer opens cleanly in Excel.",
        "You repeat the same cleaning every week / month.",
        "You want AI to write the analysis paragraph for you.",
        "You need clustering or prediction without leaving the analysis tool.",
      ],
      them: [
        "Your file is small (<50 MB) and one-off.",
        "You need pivot tables, VLOOKUP, or financial functions interactively.",
        "Your team's entire workflow is built on Excel and Microsoft 365.",
        "You need cell-level formulas more than statistical analysis.",
      ],
    },
    faq: [
      { q: "Can DataVision Pro export back to Excel?", a: "Yes — analysed datasets and reports export to CSV and Excel formats." },
      { q: "Does it replace pivot tables?", a: "It replaces the analysis use of pivot tables (group-by, summarise, chart). For interactive cell-level pivoting, Excel is still excellent." },
      { q: "What about Google Sheets?", a: "Same trade-offs apply. Sheets struggles past ~50k rows; DataVision Pro is comfortable into the millions." },
      { q: "Do I lose my Excel skills?", a: "Not at all — the cleaning steps map 1:1 to operations you already know (filter, replace, drop column, dedupe). You just stop maintaining macros to run them." },
    ],
    updated: "2026-04-15",
  },
  {
    slug: "datavision-pro-vs-looker-studio",
    competitor: "Looker Studio",
    title: "DataVision Pro vs Looker Studio",
    description:
      "DataVision Pro vs Google Looker Studio — compare AI features, file-based analysis, dashboard governance, and pricing. Honest trade-offs, no fabricated metrics.",
    intro:
      "DataVision Pro is an AI-first analytics platform built around uploading a file and getting cleaned data, statistics, ML, and AI insights immediately. Looker Studio (formerly Google Data Studio) is a free dashboard tool tightly integrated with the Google ecosystem — Sheets, BigQuery, Google Ads, GA4. Pick DataVision Pro for fast file-based analysis with AI; pick Looker Studio for free shareable dashboards on Google data sources.",
    bestFor: {
      us: "Analysts who upload CSV/Excel files and want AI-explained cleaning, statistics, and ML in one tool.",
      them: "Teams that live in Google Sheets, BigQuery, Google Ads, or GA4 and need free, shareable dashboards.",
    },
    rows: [
      { feature: "Primary use case", us: "Ad-hoc analysis of files", them: "Dashboards over Google data sources" },
      { feature: "Setup time", us: "Sign up → upload → insights in minutes", them: "Connect data source → model → build dashboard" },
      { feature: "Auto data cleaning", us: "Built-in toggleable cleaning pipeline", them: "Limited — calculated fields and data blending only" },
      { feature: "AI chat over your data", us: "Built-in (GPT-powered)", them: "Gemini in Looker Studio Pro [verify against current Google pricing]" },
      { feature: "Built-in ML", us: "K-Means + RandomForest + linear models", them: "None natively; requires BigQuery ML or Vertex AI" },
      { feature: "Best data sources", us: "CSV, Excel uploads", them: "Google Sheets, BigQuery, Google Ads, GA4 (150+ connectors)" },
      { feature: "Pricing entry point", us: "60-day free Tier 3 trial; tiered free access", them: "Free; Looker Studio Pro adds enterprise features" },
      { feature: "Dashboard sharing", us: "Web link, role-based access", them: "Native Google Drive sharing — links, viewers, editors" },
      { feature: "Refresh schedule", us: "Re-upload or re-import on demand", them: "Live connections refresh automatically" },
    ],
    whenToChoose: {
      us: [
        "Your data lives in flat files (CSV/Excel), not Google warehouses.",
        "You want AI summaries and recommendations baked into every chart.",
        "You need cleaning, descriptive statistics, and ML in one tool with no extra licences.",
        "You don't need always-live dashboard refresh — periodic uploads are fine.",
      ],
      them: [
        "Your data already lives in Google Sheets, BigQuery, GA4, or Google Ads.",
        "You need free, shareable, always-live dashboards more than AI cleaning or ML.",
        "Your stakeholders are used to Google's editing UX (Docs, Sheets, Slides).",
        "You're standing up marketing or product reporting on a Google stack.",
      ],
    },
    faq: [
      { q: "Is Looker Studio really free?", a: "Yes — the standard product is free for any Google account. Looker Studio Pro adds enterprise features (team workspaces, asset management, support) at a per-project monthly fee. [verify against current Google pricing]" },
      { q: "Does DataVision Pro connect to BigQuery?", a: "Today it consumes CSV/Excel uploads. Direct warehouse connectors are on the roadmap. For now, export the relevant slice from BigQuery to CSV and upload it." },
      { q: "Which is better for AI?", a: "DataVision Pro builds AI into every analysis page out of the box. Looker Studio's Gemini features sit behind the Pro tier and focus on chart-suggestion and natural-language querying." },
      { q: "Can I use both?", a: "Yes — many teams use Looker Studio for live shareable dashboards over GA4/Google Ads, and DataVision Pro for deeper ad-hoc analysis on extracts." },
    ],
    updated: "2026-04-21",
  },
  {
    slug: "datavision-pro-vs-metabase",
    competitor: "Metabase",
    title: "DataVision Pro vs Metabase",
    description:
      "DataVision Pro vs Metabase — compare AI features, file-based analysis, self-service BI, and hosting. An honest side-by-side, no fabricated lift numbers.",
    intro:
      "DataVision Pro is a hosted AI analytics platform focused on uploading a file and getting cleaned data, statistics, ML, and AI insights immediately. Metabase is an open-source self-service BI tool that points at your database and lets non-engineers build questions and dashboards in a friendly UI. Pick DataVision Pro for AI-first file analysis; pick Metabase for self-hosted dashboards over a SQL database.",
    bestFor: {
      us: "Analysts who upload files and want AI-explained cleaning, stats, and ML without hosting infrastructure.",
      them: "Teams with a Postgres / MySQL / warehouse who want self-service exploration and dashboards on top of it.",
    },
    rows: [
      { feature: "Primary use case", us: "Ad-hoc file analysis with AI", them: "Self-service BI on a SQL database" },
      { feature: "Hosting", us: "Hosted SaaS", them: "Self-host (open-source) or Metabase Cloud" },
      { feature: "Source data", us: "CSV / Excel uploads", them: "Direct connection to 20+ databases" },
      { feature: "Auto data cleaning", us: "Built-in toggleable cleaning pipeline", them: "Not really — Metabase assumes the warehouse is already clean" },
      { feature: "AI features", us: "GPT-powered chat + auto-generated reports", them: "Metabot AI for natural-language questions [verify against current Metabase tier]" },
      { feature: "Built-in ML", us: "K-Means + RandomForest + linear models", them: "None — relies on SQL and your warehouse's ML if any" },
      { feature: "Pricing", us: "60-day free Tier 3 trial; tiered free access", them: "Open-source free; Pro and Enterprise editions per Metabase pricing" },
      { feature: "Best for", us: "Analysts working from extracts", them: "Engineering-adjacent teams with a database" },
      { feature: "Learning curve", us: "No SQL required", them: "Question-builder is no-code; deeper analysis often requires SQL" },
    ],
    whenToChoose: {
      us: [
        "Your data lives in CSV/Excel exports, not a queryable database.",
        "You want AI to explain and summarise every chart automatically.",
        "You need cleaning + stats + ML in one place without hosting anything.",
        "You don't have an engineer available to install or maintain a BI server.",
      ],
      them: [
        "You already run Postgres, MySQL, Snowflake, BigQuery, or Redshift.",
        "You want a free, self-hosted BI layer your team can extend.",
        "Your stakeholders are happy writing SQL or click-built questions.",
        "You need fine-grained permissions and audit logs that come with self-hosting.",
      ],
    },
    faq: [
      { q: "Is Metabase free?", a: "The open-source edition is free to self-host. Metabase Cloud and Pro/Enterprise editions add managed hosting, SSO, and advanced permissions at per-user pricing. [verify against current Metabase pricing]" },
      { q: "Can DataVision Pro connect to my Postgres?", a: "Today it consumes CSV/Excel uploads. Direct database connectors are on the roadmap. For now, export the slice you need and upload it." },
      { q: "Which is better for AI?", a: "DataVision Pro builds GPT-powered analysis into every page by default. Metabase's Metabot is focused on natural-language SQL question generation; both are useful in different ways." },
      { q: "Can I use both?", a: "Yes — Metabase is excellent for always-on dashboards over your warehouse; DataVision Pro is excellent for AI-driven deep-dives on the extracts your team needs to investigate." },
    ],
    updated: "2026-04-21",
  },
];

export const getCompare = (slug: string) => COMPARE.find((c) => c.slug === slug);
