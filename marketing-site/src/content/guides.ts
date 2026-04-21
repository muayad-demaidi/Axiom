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
  jsonLd?: Record<string, unknown>[]; // optional JSON-LD blocks emitted by the SEO/GEO agent
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
  {
    slug: "how-to-ab-test-a-pricing-change",
    title: "How to A/B test a pricing change",
    description:
      "Step-by-step: design, size, and analyse an A/B test on a pricing change without statistical bait-and-switch. Includes power analysis, sample size, and how to read the result honestly.",
    intro:
      "To A/B test a pricing change: pre-declare the metric (revenue per visitor, not conversion rate alone), power-analyse the sample size you need, randomise at the user level, run for at least one full week without peeking, then load both arms into DataVision Pro and report the lift with a confidence interval — never just a p-value.",
    estTime: "15 minutes setup + 1–4 weeks runtime",
    difficulty: "Intermediate",
    prerequisites: [
      "An experimentation platform or simple split mechanism that can randomise at the user level.",
      "A baseline conversion / revenue-per-visitor figure from the last 4 weeks.",
      "An estimate of the smallest effect size you'd act on (e.g. +3% revenue per visitor).",
    ],
    steps: [
      {
        name: "Pick the right metric",
        html: `<p>Conversion rate alone is a trap on a pricing test — a higher price almost always converts worse and yet often produces more revenue. Use <strong>revenue per visitor</strong> (RPV) as the primary metric, with conversion rate and AOV as guardrails.</p>`,
      },
      {
        name: "Run a power analysis",
        html: `<p>Use the rule of thumb <code>n ≈ 16 · σ² / δ²</code> per arm, where δ is the minimum detectable effect in the same units as the metric and σ is the standard deviation. For a typical e-commerce baseline, detecting a 3% RPV lift commonly needs tens of thousands of visitors per arm. If you cannot reach that, the test will be under-powered — fix the design before launching.</p>`,
      },
      {
        name: "Randomise at the user level",
        html: `<p>Bucket each visitor by a hashed user ID (or session ID for logged-out traffic) so the same person sees a consistent variant across visits. Verify the split lands at the expected ratio after 24 hours — a 50/50 design that drifts to 47/53 is a sample-ratio mismatch and the result is not trustworthy.</p>`,
      },
      {
        name: "Run for at least one full business cycle, no peeking",
        html: `<p>Run for a minimum of seven full days — and longer if your business has a monthly cycle (B2B, payroll, subscription renewals). Resist checking results daily and stopping when you "see significance"; naive peeking inflates the false-positive rate well above 5%.</p>`,
      },
      {
        name: "Analyse in DataVision Pro",
        html: `<p>Export both arms as a CSV with columns <code>variant, user_id, revenue, converted</code>. Upload to DataVision Pro, run the descriptive statistics tab to compare RPV by variant, and use the AI chat to compute the lift, the 95% confidence interval, and a sanity-check p-value. Report all three — never just one.</p>`,
      },
      {
        name: "Make the call honestly",
        html: `<p>Roll out only if the confidence interval excludes zero <em>and</em> the lower bound is large enough to be commercially meaningful. A statistically significant +0.4% lift on a metric you need 3% on is a "no go", not a "ship it".</p>`,
      },
    ],
    pitfalls: [
      "Peeking at results and stopping early — doubles the false-positive rate.",
      "Reporting conversion rate alone on a pricing test (it almost always falls when prices rise).",
      "Running concurrent overlapping tests without orthogonal randomisation; you'll measure the combination, not each change.",
      "Ignoring sample-ratio mismatch — a broken split silently invalidates the result.",
    ],
    faq: [
      { q: "Can I run a pricing test for just a weekend?", a: "Almost never. Weekend traffic is unrepresentative of weekday traffic, and short tests under-sample the population. Run for at least one full week, ideally two." },
      { q: "Is a p-value of 0.04 enough to ship?", a: "It crosses convention but is weak evidence. Pair it with the confidence interval and the commercial significance of the effect before deciding." },
      { q: "Should I segment the result by country / device?", a: "Pre-declare any segmentation you'll perform. Slicing the data after the fact (HARKing) inflates false positives. If you must explore, treat segment results as hypotheses for the next test." },
      { q: "Does DataVision Pro run the experiment for me?", a: "No — it analyses the data after you've collected it. Pair it with your existing experimentation platform or a simple hashed split in your application code." },
    ],
    updated: "2026-04-21",
  },
  {
    slug: "how-to-compare-this-quarter-vs-last-quarter",
    title: "How to compare this quarter vs last quarter (without lying with averages)",
    description:
      "A practical guide to a defensible quarter-over-quarter comparison — same-day windows, mix-shift checks, and confidence intervals — using DataVision Pro's time-period view.",
    intro:
      "To compare this quarter vs last quarter honestly: align both windows to the same number of business days, hold the customer mix constant where possible, report median alongside mean (revenue distributions are skewed), check for a mix shift that explains the headline change, and surface the result with a confidence interval — not a single percent number that hides the variance.",
    estTime: "10 minutes",
    difficulty: "Intermediate",
    prerequisites: [
      "A transaction or order-line dataset with a date column and at least one revenue/quantity column.",
      "Knowledge of any obvious external events in either window (a launch, a holiday calendar shift, a pricing change).",
    ],
    steps: [
      {
        name: "Align the windows",
        html: `<p>Compare like with like: same number of business days, same days of week. Q1 has fewer days than Q4; February is short; Easter and Lunar New Year shift between months. In DataVision Pro, set both windows to the same length (e.g. trailing 90 days) rather than calendar quarters when the calendars don't match.</p>`,
      },
      {
        name: "Profile both windows separately",
        html: `<p>Open the <strong>Statistics</strong> tab on each window and compare the 5-number summary side-by-side. A higher mean with an unchanged median tells you the tail moved, not the typical customer — that is a mix shift, not growth.</p>`,
      },
      {
        name: "Check the mix",
        html: `<p>Group by the dimensions that matter (country, channel, segment, product line) and compare the share of revenue per group. If the country mix shifted from 70/30 to 50/50, the headline change is partly composition, not performance. DataVision Pro's tabular comparison view shows both shares side-by-side for a one-glance check.</p>`,
      },
      {
        name: "Compute the lift with a confidence interval",
        html: `<p>Use the AI chat or the descriptive statistics view to compute mean RPC (revenue per customer) and a 95% confidence interval for the difference. A "+8% QoQ" headline with a CI of [-1%, +17%] is too noisy to act on; the same lift with a CI of [+5%, +11%] is a real signal.</p>`,
      },
      {
        name: "Cross-check with a holdout-style sanity test",
        html: `<p>Pick a stable segment that should not have changed (e.g. existing customers in your largest country with no pricing change) and run the same comparison. If that segment also shows a big swing, suspect a data issue (missing days, late-arriving orders) rather than business performance.</p>`,
      },
      {
        name: "Write the summary in three lines",
        html: `<p>Report (1) the headline change with its confidence interval, (2) what mix change explains how much of it, and (3) which segments drove the residual real change. Three lines is enough — anything longer is hiding the answer.</p>`,
      },
    ],
    pitfalls: [
      "Comparing calendar quarters of different length without normalising — a 92-day quarter beats an 89-day quarter on volume alone.",
      "Reporting only the mean when the distribution is right-skewed (most revenue data is) — the median tells the typical-customer story.",
      "Ignoring a mix shift — a country, channel, or segment composition change can fully explain the headline number with no underlying performance change.",
      "Cherry-picking the comparison window after seeing the data; pre-declare it.",
    ],
    faq: [
      { q: "Should I compare quarter-over-quarter or year-over-year?", a: "Both, when possible. QoQ catches recent momentum; YoY controls for seasonality. Reporting only one is a half-answer." },
      { q: "What if the two windows have very different sizes?", a: "Normalise by days, customers, or sessions before comparing. Report the per-unit metric, not the totals." },
      { q: "Is a confidence interval really needed for QoQ?", a: "Yes — without it, leadership cannot tell a real swing from random variation, and you'll spend the next quarter explaining noise as strategy." },
      { q: "Does DataVision Pro detect mix shifts automatically?", a: "Yes — the time-period comparison surfaces grouped share-of-total alongside the headline metric so a composition change is visible at a glance." },
    ],
    updated: "2026-04-21",
  },
];

export const getGuide = (slug: string) => GUIDES.find((g) => g.slug === slug);
