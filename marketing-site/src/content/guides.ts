export type Step = { name: string; html: string };
export type Guide = {
  slug: string;
  title: string;
  description: string;
  intro: string; // 40-60 word direct answer
  estTime: string; // e.g. "60 seconds"
  difficulty: "Beginner" | "Intermediate" | "Advanced";
  prerequisites: string[];
  steps: Step[];
  pitfalls: string[];
  faq: { q: string; a: string }[];
  updated: string;
};

export const GUIDES: Guide[] = [
  {
    slug: "how-to-clean-a-messy-csv-in-60-seconds",
    title: "How to clean a messy CSV in 60 seconds",
    description:
      "A 60-second walkthrough for turning a messy CSV — duplicates, missing values, mixed types, stray whitespace — into a clean, analysis-ready dataset using DataVision Pro.",
    intro:
      "To clean a messy CSV in 60 seconds: upload it, run auto-clean (which removes duplicates, trims whitespace, infers types, fills missing values, and flags outliers as a single ordered pipeline you can toggle), preview the change at each step, then save the result as a reusable cleaning recipe for next month's file.",
    estTime: "60 seconds",
    difficulty: "Beginner",
    prerequisites: [
      "A free DataVision Pro account (60-day Tier 3 trial included).",
      "A CSV or XLSX file under 200 MB.",
    ],
    steps: [
      {
        name: "Upload your file",
        html: `<p>From the dashboard, click <strong>Upload Dataset</strong> and drop the file. DataVision Pro automatically detects the delimiter, encoding (UTF-8, Latin-1, Windows-1252), and header row.</p>`,
      },
      {
        name: "Run auto-clean",
        html: `<p>Open the <strong>Cleaning</strong> tab and toggle on the default substeps: <em>Trim Whitespace → Drop Duplicates → Infer Types → Impute Missing Values → Flag Outliers</em>. Each substep runs in order; the preview pane shows row count, missing-cell count, and changed columns before vs after.</p>`,
      },
      {
        name: "Insert custom substeps",
        html: `<p>Need to drop a column or rename one? Click <strong>Insert Substep</strong> between any two existing steps and pick <em>Drop Column</em>, <em>Rename Column</em>, or <em>Replace Values</em>. Reorder with the ↑/↓ arrows. Order matters: trim before dedupe, dedupe before impute.</p>`,
      },
      {
        name: "Inspect and verify",
        html: `<p>Switch to the <strong>Statistics</strong> tab and confirm the descriptive stats look sane: no negative ages, plausible mins/maxes, currency columns showing currency codes, dates in your preferred format.</p>`,
      },
      {
        name: "Save it as a recipe",
        html: `<p>Click <strong>Save Recipe</strong>. Next month, upload the new file and apply the saved recipe — the same pipeline runs in one click. That's the difference between cleaning <em>once</em> and cleaning <em>forever</em>.</p>`,
      },
    ],
    pitfalls: [
      "Imputing before dropping duplicates inflates the imputed values with duplicate rows.",
      "Flagging outliers before fixing types means numeric columns stored as strings get skipped.",
      "Forgetting to save the recipe means you'll re-do all of this next month.",
    ],
    faq: [
      { q: "What if my CSV has multiple header rows?", a: "Use the Insert Substep menu to drop the rows above the real header, or open the file in Excel/Sheets, fix the header, and re-upload." },
      { q: "Will it handle European decimal separators?", a: "Yes — DataVision Pro infers comma-vs-period decimals per column during type inference." },
      { q: "Can I undo a step?", a: "Yes. Cleaning is non-destructive: you can toggle any substep off, reorder it, or insert a new one and the pipeline replays from scratch." },
      { q: "Does it work for Excel files with multiple sheets?", a: "Yes — choose the sheet at upload time. Each sheet becomes a separate dataset." },
    ],
    updated: "2026-04-15",
  },
  {
    slug: "how-to-detect-outliers-in-sales-data",
    title: "How to detect outliers in sales data",
    description:
      "A practical guide to spotting outliers in sales data using IQR, z-score, and K-Means clustering — without writing code.",
    intro:
      "To detect outliers in sales data: load the dataset, run descriptive statistics to see the distribution, apply IQR (Tukey's 1.5×) or z-score thresholds to flag candidates, then use K-Means clustering to separate one-off weird transactions from emerging patterns. Always investigate before deleting — outliers often contain the most valuable signal.",
    estTime: "5 minutes",
    difficulty: "Intermediate",
    prerequisites: [
      "A cleaned sales dataset (date, customer, product, quantity, revenue).",
      "Familiarity with the difference between an outlier and a typo.",
    ],
    steps: [
      {
        name: "Profile the revenue column",
        html: `<p>Open the <strong>Statistics</strong> tab and look at the 5-number summary for revenue. A median of $480 with a max of $1,250,000 instantly tells you the right tail is doing something interesting.</p>`,
      },
      {
        name: "Visualise with a box plot",
        html: `<p>In the <strong>Visualisations</strong> tab, build a box plot of revenue, optionally split by region or product category. Anything plotted beyond the whiskers (1.5×IQR above Q3 or below Q1) is a Tukey outlier.</p>`,
      },
      {
        name: "Cross-check with z-scores",
        html: `<p>Add a calculated column <code>z = (revenue − mean) / std</code>. Rows with |z| &gt; 3 are statistical outliers under a normal-distribution assumption. If your data is heavily skewed (most sales data is), trust the IQR result more.</p>`,
      },
      {
        name: "Cluster to find new patterns",
        html: `<p>Open the <strong>ML &amp; Clustering</strong> tab and run K-Means with K = 3 on revenue + quantity + customer-tenure. If a cluster of 50 customers all sit in the "outlier" zone, that's not noise — that's a segment.</p>`,
      },
      {
        name: "Decide: drop, flag, or escalate",
        html: `<p>Three buckets: <em>impossible</em> values (negative quantity → drop), <em>plausible but rare</em> (one-time bulk order → flag and keep), <em>pattern-forming</em> (new high-value segment → escalate to sales).</p>`,
      },
    ],
    pitfalls: [
      "Using z-score on heavily skewed sales data — it under-flags genuine outliers.",
      "Deleting outliers without checking whether they correlate with a known event (Black Friday, a new SKU launch).",
      "Running K-Means on un-scaled features — revenue in dollars will dominate quantity in units.",
    ],
    faq: [
      { q: "Should I winsorise?", a: "Winsorising (capping at the 1st and 99th percentile) is fine for downstream linear models that are sensitive to outliers, but only after you've documented why each capped value was anomalous." },
      { q: "How many outliers are 'too many'?", a: "Roughly 0.7% of points exceed |z|>3 in a normal distribution. If your column has 5%+ outliers, the distribution is not normal and you should switch to IQR-based methods." },
      { q: "Can outliers signal fraud?", a: "Yes — most fraud-detection systems start with a simple outlier rule before adding ML. A single $50,000 transaction from a normally $50/day customer is the textbook signal." },
    ],
    updated: "2026-04-15",
  },
  {
    slug: "how-to-build-a-3-month-sales-forecast",
    title: "How to build a 3-month sales forecast (no code)",
    description:
      "Step-by-step: turn 24 months of sales history into a defensible 3-month forecast using DataVision Pro's predictions tab — with honest accuracy bounds.",
    intro:
      "To build a 3-month sales forecast: gather at least 24 months of monthly sales (two full seasonal cycles), load it into DataVision Pro, fit a linear-trend or RandomForest model in the Predictions tab, hold out the last three months to measure error, then apply the validated model to forecast the next three months — and report the error band, not a single number.",
    estTime: "10 minutes",
    difficulty: "Intermediate",
    prerequisites: [
      "≥ 24 months of monthly sales data (date, revenue).",
      "Knowledge of obvious external events (promotions, launches) so you can mark them as features.",
    ],
    steps: [
      {
        name: "Prepare the time series",
        html: `<p>Aggregate the sales table to one row per month per segment. Confirm there are no gaps; if a month is missing, fill with 0 explicitly so the model knows it was zero, not unknown.</p>`,
      },
      {
        name: "Hold out the last 3 months",
        html: `<p>In the <strong>Predictions</strong> tab, set the holdout to the most recent 3 months. The model sees only the first 21 months and predicts the held-out months — this is your honest accuracy test.</p>`,
      },
      {
        name: "Try linear, then RandomForest",
        html: `<p>Start with a linear trend model. If the holdout MAPE (mean absolute percentage error) is &gt; 15%, switch to RandomForest, which captures non-linear seasonality better. Pick the simpler model whenever the error gap is &lt; 2 percentage points.</p>`,
      },
      {
        name: "Refit on all 24 months and forecast forward",
        html: `<p>Once you've picked a model, refit it on all 24 months and forecast the next 3. Always report the forecast as a range (point estimate ± holdout MAPE), not a single confident number.</p>`,
      },
      {
        name: "Re-check monthly for data drift",
        html: `<p>Once a forecast is in production, run the same model next month and compare. If MAPE doubles, you have data drift — investigate before trusting the next forecast.</p>`,
      },
    ],
    pitfalls: [
      "Forecasting from 6 months of history — the model has no chance of learning seasonality.",
      "Reporting a single forecast number to leadership without an error band invites a board-meeting cross-examination.",
      "Including post-holdout features (e.g., this month's marketing spend) leaks the future into the past.",
    ],
    faq: [
      { q: "Why 24 months minimum?", a: "Monthly sales typically have annual seasonality. The model needs to see at least two full cycles to distinguish trend from season." },
      { q: "Should I use external regressors (weather, ads spend)?", a: "Yes if they are known in advance for the forecast window. If you're forecasting March, you can use planned March ads spend; you cannot use March weather (you don't know it yet)." },
      { q: "What's a good MAPE for sales?", a: "5–10% is excellent for established products; 15–25% is realistic for new products or volatile categories; > 30% means the signal is weak and the model is mostly noise." },
    ],
    updated: "2026-04-15",
  },
];

export const getGuide = (slug: string) => GUIDES.find((g) => g.slug === slug);
