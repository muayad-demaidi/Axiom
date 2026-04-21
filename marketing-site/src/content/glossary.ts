export type FAQ = { q: string; a: string };
export type Source = { label: string; url: string };
export type Section = { heading: string; html: string };
export type GlossaryEntry = {
  slug: string;
  term: string;
  question: string;
  shortDef: string;
  description: string; // meta description
  answer: string; // 40-60 word direct answer
  stats: { value: string; label: string; source: Source }[];
  sections: Section[];
  faq: FAQ[];
  related: string[]; // slugs
  updated: string;
  jsonLd?: Record<string, unknown>[]; // optional JSON-LD blocks emitted by the SEO/GEO agent
};

export const GLOSSARY: GlossaryEntry[] = [
  {
    slug: "data-cleaning",
    term: "Data Cleaning",
    question: "What is data cleaning?",
    shortDef:
      "The process of detecting and correcting errors, inconsistencies, missing values, and duplicates in a dataset before analysis.",
    description:
      "Data cleaning is the process of fixing or removing incorrect, corrupted, duplicate, or incomplete records so analysis produces trustworthy results. Learn the steps, costs, and tools.",
    answer:
      "Data cleaning is the process of identifying and fixing errors, missing values, duplicates, and inconsistencies in a dataset so that downstream analysis, reporting, and machine-learning models produce trustworthy results. It typically includes removing duplicates, standardising formats, handling outliers, imputing missing values, and validating data types.",
    stats: [
      {
        value: "Up to 80%",
        label: "of a data scientist's time is spent preparing and cleaning data, leaving only ~20% for analysis.",
        source: { label: "Anaconda State of Data Science 2022", url: "https://www.anaconda.com/state-of-data-science-2022" },
      },
      {
        value: "$12.9M / year",
        label: "Gartner's estimate of the average annual cost of poor data quality to a single organisation.",
        source: { label: "Gartner — How to Improve Your Data Quality", url: "https://www.gartner.com/smarterwithgartner/how-to-improve-your-data-quality" },
      },
    ],
    sections: [
      {
        heading: "How data cleaning works",
        html: `<p>A practical cleaning pipeline runs in roughly this order:</p>
        <ol>
          <li><strong>Profile</strong> — count rows, columns, missing cells, and duplicates per column.</li>
          <li><strong>Standardise types</strong> — coerce strings that look like dates or currency into the correct type.</li>
          <li><strong>Trim and normalise text</strong> — strip whitespace, fix casing, and collapse encodings.</li>
          <li><strong>Handle missing values</strong> — drop, fill with a constant, or impute using mean/median/mode.</li>
          <li><strong>Detect outliers</strong> — IQR or z-score for numeric columns.</li>
          <li><strong>Deduplicate</strong> — exact and fuzzy match on key columns.</li>
          <li><strong>Validate</strong> — re-profile and confirm all assumptions hold.</li>
        </ol>`,
      },
      {
        heading: "Why it matters for analysts",
        html: `<p>Garbage in, garbage out is not a cliché — it is a budget item. Analysts who skip cleaning end up debugging KPIs in board meetings instead of trusting them. A repeatable cleaning step keeps every chart, model, and AI summary anchored to the same source of truth.</p>
        <p>In <strong>DataVision Pro</strong>, the cleaning pipeline runs as an ordered list of toggleable substeps you can reorder (↑/↓) and extend (Trim Whitespace, Drop Column, Rename Column), so the same recipe can be replayed on next month's file in one click.</p>`,
      },
    ],
    faq: [
      {
        q: "Is data cleaning the same as data wrangling?",
        a: "No. Cleaning is a subset of wrangling. Wrangling also includes reshaping, joining, and feature engineering. Cleaning specifically targets errors, duplicates, and missing values.",
      },
      {
        q: "Should I clean before or after exploratory analysis?",
        a: "Both. A first pass before EDA fixes obvious errors; a second pass after EDA addresses issues you only see once you start visualising.",
      },
      {
        q: "How much data should I throw away?",
        a: "As little as possible. Prefer imputation, flagging, or quarantine columns over deletion, because deleted rows can introduce sampling bias.",
      },
      {
        q: "Can data cleaning be automated?",
        a: "The mechanical parts (trim, dedupe, type cast, IQR outliers) absolutely. Domain-specific decisions (is a $0 sale a refund or an error?) still need a human.",
      },
      {
        q: "What is a 'cleaning recipe'?",
        a: "A saved, ordered list of cleaning substeps that can be re-applied to a new file with the same schema, ensuring reproducible results month over month.",
      },
    ],
    related: ["missing-value-imputation", "outlier-detection", "etl-vs-elt", "descriptive-statistics"],
    updated: "2026-04-15",
  },
  {
    slug: "outlier-detection",
    term: "Outlier Detection",
    question: "What is outlier detection?",
    shortDef:
      "Statistical techniques for finding observations that lie an abnormal distance from the rest of a dataset.",
    description:
      "Outlier detection identifies data points that deviate significantly from the rest of the dataset. Learn IQR, z-score, and ML-based methods, and when to drop vs. investigate.",
    answer:
      "Outlier detection is the process of identifying observations that differ significantly from other points in a dataset, often signalling errors, fraud, or genuinely interesting events. Common techniques include the interquartile range (IQR) rule, z-scores, isolation forests, and DBSCAN. Outliers are not always bad — sometimes they are the entire signal.",
    stats: [
      {
        value: "1.5 × IQR",
        label: "Tukey's classic threshold for flagging a point as an outlier in a box plot — still the most-used rule in industry.",
        source: { label: "Tukey, Exploratory Data Analysis (1977)", url: "https://en.wikipedia.org/wiki/Outlier#Tukey%27s_fences" },
      },
      {
        value: "$5.4 trillion",
        label: "Estimated global cost of fraud in 2023 — a category that lives or dies on outlier detection.",
        source: { label: "Crowe Global Fraud Report 2023", url: "https://www.crowe.com/global/insights/financial-cost-of-fraud-2023" },
      },
    ],
    sections: [
      {
        heading: "How it works",
        html: `<p>Three families of methods cover ~90% of business cases:</p>
        <ul>
          <li><strong>Statistical</strong> — IQR rule, z-score (|z| &gt; 3), or modified z-score for skewed data.</li>
          <li><strong>Distance-based</strong> — k-nearest-neighbour distance, DBSCAN density, or Mahalanobis distance for multivariate cases.</li>
          <li><strong>Model-based</strong> — Isolation Forest and One-Class SVM for high-dimensional unlabeled data.</li>
        </ul>`,
      },
      {
        heading: "When to drop and when to investigate",
        html: `<p>Drop only if you can prove the value is impossible (negative age, future timestamp). Investigate when the value is merely surprising — a $50,000 order from a normally-$500 customer is an outlier you want to <em>understand</em>, not delete.</p>
        <p>DataVision Pro shows enhanced outlier detection with box plots and K-Means risk clustering side-by-side, so you can see whether a point is a single weird record or a whole cluster of new behaviour.</p>`,
      },
    ],
    faq: [
      { q: "What's the difference between an outlier and an anomaly?", a: "Outliers are statistical — they sit far from the distribution. Anomalies are contextual — they violate an expected pattern. All anomalies are usually outliers, but not vice versa." },
      { q: "Is z-score or IQR better?", a: "IQR is more robust to non-normal data. Z-score assumes a roughly normal distribution; if your data is skewed (revenue, page views), prefer IQR or modified z-score." },
      { q: "Should I remove outliers before training a model?", a: "It depends. Tree-based models (Random Forest, XGBoost) tolerate outliers; linear regression and k-means are highly sensitive." },
      { q: "How does DBSCAN find outliers?", a: "DBSCAN labels points that have fewer than min_samples neighbours within ε as 'noise' — a natural outlier flag with no need to set thresholds per column." },
      { q: "Can outliers be useful?", a: "Yes — fraud, intrusion, equipment failure, and viral content are all outliers. The signal often lives in the tail." },
    ],
    related: ["data-cleaning", "k-means-clustering", "descriptive-statistics", "predictive-analytics"],
    updated: "2026-04-15",
  },
  {
    slug: "k-means-clustering",
    term: "K-Means Clustering",
    question: "What is K-Means clustering?",
    shortDef:
      "An unsupervised algorithm that groups observations into K clusters by minimising within-cluster variance.",
    description:
      "K-Means clustering partitions a dataset into K groups based on feature similarity. Learn how it works, how to pick K, and where it breaks down.",
    answer:
      "K-Means clustering is an unsupervised learning algorithm that partitions a dataset into K non-overlapping groups by iteratively assigning each point to the nearest cluster centroid and then recomputing centroids until they stabilise. It is fast, simple, and works best on numerical features that form roughly spherical clusters of similar size.",
    stats: [
      {
        value: "1957",
        label: "Year Stuart Lloyd developed the original K-Means algorithm at Bell Labs — it remains the most widely-taught clustering method today.",
        source: { label: "Lloyd, Least squares quantization in PCM (Bell Labs, 1957)", url: "https://en.wikipedia.org/wiki/K-means_clustering#History" },
      },
      {
        value: "O(n · k · i · d)",
        label: "Time complexity per Lloyd iteration — roughly linear in data size, which is why it scales to millions of rows where hierarchical clustering cannot.",
        source: { label: "Scikit-learn — K-Means complexity", url: "https://scikit-learn.org/stable/modules/clustering.html#k-means" },
      },
    ],
    sections: [
      {
        heading: "How it works (Lloyd's algorithm)",
        html: `<ol>
          <li>Pick K initial centroids (random or k-means++).</li>
          <li>Assign every point to its nearest centroid.</li>
          <li>Recompute each centroid as the mean of its assigned points.</li>
          <li>Repeat 2–3 until assignments stop changing or a max-iteration cap is hit.</li>
        </ol>`,
      },
      {
        heading: "How to pick K",
        html: `<ul>
          <li><strong>Elbow method</strong> — plot inertia vs K and pick the elbow.</li>
          <li><strong>Silhouette score</strong> — pick K that maximises average silhouette (-1 to 1).</li>
          <li><strong>Domain knowledge</strong> — sometimes "high / medium / low risk" forces K = 3 regardless of statistics.</li>
        </ul>`,
      },
      {
        heading: "Where K-Means breaks",
        html: `<p>K-Means struggles with non-spherical clusters, very different cluster sizes, and mixed numeric/categorical data. For those cases prefer DBSCAN, Gaussian Mixture Models, or k-prototypes. DataVision Pro uses K-Means specifically for risk clustering, where 3–5 spherical groups (low/medium/high) match the business question.</p>`,
      },
    ],
    faq: [
      { q: "Does K-Means need scaled features?", a: "Yes. Because it uses Euclidean distance, a column in dollars will dominate a column in fractions. Standardise (z-score) or min-max scale before fitting." },
      { q: "Is K-Means deterministic?", a: "No — initial centroids are random. Set a fixed random_state or use multiple restarts (n_init in scikit-learn) to get reproducible clusters." },
      { q: "Can K-Means handle categorical data?", a: "Not natively. One-hot encode and scale, or use k-modes / k-prototypes for mixed types." },
      { q: "How many points do I need?", a: "Rule of thumb: at least 30 points per cluster, ideally hundreds. Below that, cluster centroids are noisy." },
      { q: "What's the difference between K-Means and KNN?", a: "K-Means is unsupervised clustering. KNN is supervised classification. They share the letter K and not much else." },
    ],
    related: ["outlier-detection", "predictive-analytics", "descriptive-statistics", "data-drift"],
    updated: "2026-04-15",
  },
  {
    slug: "data-drift",
    term: "Data Drift",
    question: "What is data drift?",
    shortDef:
      "A change over time in the statistical properties of input data that degrades a model's accuracy.",
    description:
      "Data drift is when the distribution of incoming data shifts from what a model was trained on, silently degrading accuracy. Learn the types, detection methods, and mitigations.",
    answer:
      "Data drift is the change over time in the statistical properties of input features — for example, a customer-age distribution that shifts from a mean of 32 to a mean of 41. Drift causes machine-learning models to silently lose accuracy because the patterns they learned no longer reflect production data.",
    stats: [
      {
        value: "91%",
        label: "of ML models degrade in performance over time once deployed, according to a 2022 production-ML survey.",
        source: { label: "MIT Sloan / Scientific Reports — AI model degradation (2022)", url: "https://www.nature.com/articles/s41598-022-15245-z" },
      },
      {
        value: "Population Stability Index (PSI) > 0.2",
        label: "is the credit-risk industry's standard threshold for declaring a feature has materially drifted and a model rebuild is needed.",
        source: { label: "Karakoulas, PSI in credit scoring", url: "https://en.wikipedia.org/wiki/Population_stability_index" },
      },
    ],
    sections: [
      {
        heading: "Three flavours of drift",
        html: `<ul>
          <li><strong>Covariate drift</strong> — P(X) changes (your inputs look different).</li>
          <li><strong>Prior probability drift</strong> — P(Y) changes (the base rate of the target shifts).</li>
          <li><strong>Concept drift</strong> — P(Y|X) changes (the relationship itself moves — the rules of the game change).</li>
        </ul>`,
      },
      {
        heading: "How to detect it",
        html: `<p>Compare a recent window of production data against the training reference window using:</p>
        <ul>
          <li>Population Stability Index (PSI) — bin-based, easy to threshold.</li>
          <li>Kolmogorov–Smirnov test — for continuous features.</li>
          <li>Chi-square test — for categorical features.</li>
          <li>Wasserstein / Jensen–Shannon distance — for full-distribution comparisons.</li>
        </ul>`,
      },
      {
        heading: "What to do about it",
        html: `<p>Retrain on a sliding window, add monitoring alerts at PSI thresholds, or switch to an online-learning model. In DataVision Pro, the time-period comparison view lets analysts spot drift visually before it shows up in business KPIs.</p>`,
      },
    ],
    faq: [
      { q: "Is data drift the same as concept drift?", a: "Concept drift is one type of data drift — specifically when the relationship between inputs and the target changes. Data drift is the umbrella term." },
      { q: "How often should I check for drift?", a: "Match the cadence of business decisions. Weekly is a good default for most operational ML; daily for fraud and ads." },
      { q: "Will more data fix drift?", a: "Only if the new data reflects the new world. Stale training data of any size cannot fix drift — recency matters more than volume." },
      { q: "What's a good drift dashboard?", a: "PSI per feature with a colour-coded threshold (green < 0.1, amber 0.1–0.2, red > 0.2) plus a chart of model accuracy on a holdout slice." },
      { q: "Does drift apply to non-ML analytics?", a: "Yes — even simple KPI dashboards can mislead when the underlying customer mix shifts. Drift is a data problem, not just an ML problem." },
    ],
    related: ["predictive-analytics", "data-cleaning", "descriptive-statistics", "k-means-clustering"],
    updated: "2026-04-15",
  },
  {
    slug: "etl-vs-elt",
    term: "ETL vs ELT",
    question: "What is the difference between ETL and ELT?",
    shortDef:
      "Two patterns for moving data into a warehouse — ETL transforms before loading, ELT loads first and transforms inside the warehouse.",
    description:
      "ETL transforms data before loading it into a warehouse; ELT loads raw data first and transforms in-warehouse. Learn the trade-offs in cost, governance, and speed.",
    answer:
      "ETL (Extract, Transform, Load) cleans and reshapes data on a separate server before loading it into a warehouse, which suits regulated industries with on-premise constraints. ELT (Extract, Load, Transform) loads raw data first and uses the warehouse's compute (Snowflake, BigQuery, Databricks) to transform it — faster, cheaper at scale, and the modern default.",
    stats: [
      {
        value: "~$3 per TB",
        label: "Approximate Snowflake credit cost of an ELT transform pass on warehouse-native compute, often cheaper than running a dedicated ETL fleet.",
        source: { label: "Snowflake pricing (Standard edition, 2024)", url: "https://www.snowflake.com/pricing/" },
      },
      {
        value: "78%",
        label: "of new data-warehouse projects in 2023 chose an ELT-first architecture per dbt Labs' State of Analytics Engineering.",
        source: { label: "dbt Labs — State of Analytics Engineering 2023", url: "https://www.getdbt.com/state-of-analytics-engineering-2023" },
      },
    ],
    sections: [
      {
        heading: "Side-by-side comparison",
        html: `<table class="compare">
          <thead><tr><th>Aspect</th><th>ETL</th><th>ELT</th></tr></thead>
          <tbody>
            <tr><td>Where transforms run</td><td>Dedicated ETL server</td><td>Inside the warehouse</td></tr>
            <tr><td>Storage shape</td><td>Only modeled data lands</td><td>Raw + modeled both land</td></tr>
            <tr><td>Reprocessing</td><td>Re-extract from source</td><td>Re-run SQL on raw layer</td></tr>
            <tr><td>Tooling</td><td>Informatica, Talend, SSIS</td><td>dbt, Dataform, SQLMesh</td></tr>
            <tr><td>Best for</td><td>Regulated, on-prem, slow source systems</td><td>Cloud warehouses, agile teams</td></tr>
          </tbody>
        </table>`,
      },
      {
        heading: "Why the world moved to ELT",
        html: `<p>Three things flipped the default: (1) cloud warehouses made compute cheap and elastic, (2) keeping raw data became a competitive advantage for retroactive analysis, and (3) dbt made transform-as-SQL the lingua franca of analytics engineering.</p>`,
      },
    ],
    faq: [
      { q: "Is ELT always cheaper?", a: "No. For tiny datasets and infrequent runs, a small ETL server is cheaper than warm warehouse compute. ELT wins at scale and on bursty workloads." },
      { q: "Can I mix ETL and ELT?", a: "Yes — many teams ETL the lightweight transforms (PII masking, deduping) and ELT the heavyweight ones (joins, aggregations). It's called ETLT." },
      { q: "Where does DataVision Pro fit?", a: "DataVision Pro is downstream of both — it consumes a clean CSV/Excel extract and runs the analysis layer, freeing your warehouse from BI workloads." },
      { q: "Is reverse ETL the opposite?", a: "Not the opposite — reverse ETL pushes warehouse data back into operational tools (CRM, ad platforms). It complements ELT rather than replacing it." },
      { q: "Which is better for compliance?", a: "ETL historically wins because sensitive fields can be masked before they ever land in the warehouse. ELT can match it with column-level encryption + masking policies." },
    ],
    related: ["data-cleaning", "descriptive-statistics", "predictive-analytics", "data-drift"],
    updated: "2026-04-15",
  },
  {
    slug: "descriptive-statistics",
    term: "Descriptive Statistics",
    question: "What is descriptive statistics?",
    shortDef:
      "Summary measures (mean, median, std, percentiles) that describe the central tendency and spread of a dataset.",
    description:
      "Descriptive statistics summarise a dataset's central tendency, spread, and shape. Learn the core measures and which ones lie when your data is skewed.",
    answer:
      "Descriptive statistics are summary numbers — mean, median, mode, standard deviation, min, max, and percentiles — that describe the shape of a dataset without making predictions. They are the first thing every analyst computes after loading a file because they reveal scale, skew, and obviously broken columns in seconds.",
    stats: [
      {
        value: "5-number summary",
        label: "min, Q1, median, Q3, max — Tukey's compact descriptor that fits on a box plot and explains a column at a glance.",
        source: { label: "Tukey, Exploratory Data Analysis (1977)", url: "https://en.wikipedia.org/wiki/Five-number_summary" },
      },
      {
        value: "Mean ≠ Median",
        label: "When the absolute gap exceeds 10–15% of the standard deviation, the column is meaningfully skewed and the mean alone will mislead.",
        source: { label: "Wilcox, Modern Robust Methods", url: "https://link.springer.com/book/10.1007/978-1-4419-5525-8" },
      },
    ],
    sections: [
      {
        heading: "The core measures",
        html: `<ul>
          <li><strong>Central tendency</strong> — mean, median, mode.</li>
          <li><strong>Spread</strong> — variance, standard deviation, IQR, range.</li>
          <li><strong>Shape</strong> — skewness, kurtosis.</li>
          <li><strong>Position</strong> — percentiles, quartiles.</li>
        </ul>`,
      },
      {
        heading: "When the mean lies",
        html: `<p>Income, revenue, page-view, and time-on-site distributions are almost always right-skewed. Reporting only the mean overstates the typical experience. Always pair mean with median, or report the full 5-number summary. DataVision Pro's descriptive-statistics table includes both and flags skew automatically.</p>`,
      },
    ],
    faq: [
      { q: "Is descriptive statistics the same as inferential statistics?", a: "No. Descriptive describes the data you have. Inferential generalises from a sample to a larger population using probability." },
      { q: "Should I report mean or median?", a: "Report both. Mean is sensitive to outliers; median is robust. The gap between them is itself a useful diagnostic." },
      { q: "What's a good standard deviation?", a: "There is no universal answer — std is meaningful only relative to the mean (coefficient of variation = std / mean) or to a domain benchmark." },
      { q: "Why does DataVision Pro show currency codes in the stats table?", a: "Because mean revenue of 1,200 means very different things in JPY vs USD — the unit is part of the answer, not metadata." },
      { q: "Are percentiles better than std for skewed data?", a: "Usually yes. P50/P90/P99 describe customer experience more honestly than mean ± std when the distribution has a long tail." },
    ],
    related: ["data-cleaning", "outlier-detection", "predictive-analytics", "data-drift"],
    updated: "2026-04-15",
  },
  {
    slug: "predictive-analytics",
    term: "Predictive Analytics",
    question: "What is predictive analytics?",
    shortDef:
      "Using historical data and statistical or ML models to forecast future outcomes or behaviours.",
    description:
      "Predictive analytics uses historical data to forecast future outcomes — sales, churn, demand. Learn the model families, evaluation metrics, and pitfalls.",
    answer:
      "Predictive analytics is the practice of using historical data, statistics, and machine learning to forecast future outcomes such as next-quarter revenue, customer churn, equipment failure, or fraud risk. It sits between descriptive analytics (what happened) and prescriptive analytics (what to do about it).",
    stats: [
      {
        value: "$22.1B → $67.7B",
        label: "Global predictive-analytics market projected growth between 2023 and 2028, a 25%+ compound annual growth rate.",
        source: { label: "MarketsandMarkets — Predictive Analytics Market 2023", url: "https://www.marketsandmarkets.com/Market-Reports/predictive-analytics-market-1181.html" },
      },
      {
        value: "5–25%",
        label: "Typical revenue lift retailers report from churn-prediction-driven retention campaigns vs. blanket campaigns.",
        source: { label: "Bain & Company — The Value of Online Customer Loyalty", url: "https://www.bain.com/insights/the-value-of-online-customer-loyalty" },
      },
    ],
    sections: [
      {
        heading: "Common model families",
        html: `<ul>
          <li><strong>Linear regression</strong> — interpretable, fast, baseline.</li>
          <li><strong>Logistic regression</strong> — yes/no outcomes (churn, fraud).</li>
          <li><strong>Tree ensembles</strong> — Random Forest, XGBoost, LightGBM. Strongest default for tabular data.</li>
          <li><strong>Time-series</strong> — ARIMA, Prophet, ETS for forecasting with trend and seasonality.</li>
          <li><strong>Neural networks</strong> — when you have lots of data and weak feature engineering.</li>
        </ul>`,
      },
      {
        heading: "How to know it's working",
        html: `<p>Pick a metric that matches the business cost: RMSE for forecasts, AUC for ranking, recall@k for fraud, MAPE for finance. A predictive model that improves a metric on a holdout set but never moves a business KPI is a science-fair project, not analytics.</p>`,
      },
    ],
    faq: [
      { q: "Do I need a data scientist?", a: "Not for the common patterns. DataVision Pro's predictions tab covers linear models and tree-based forecasting in a few clicks." },
      { q: "How much history do I need?", a: "For seasonal forecasts, at least two full cycles (e.g. 24 months for monthly seasonality). For classification, at least a few hundred examples per class." },
      { q: "What's the biggest pitfall?", a: "Target leakage — accidentally using a feature that is only known after the outcome occurred. It produces unrealistically good test scores and miserable production performance." },
      { q: "How is it different from forecasting?", a: "Forecasting is a subset focused on time-series outputs. Predictive analytics also covers classification, ranking, and risk scoring." },
      { q: "How do you validate a predictive model?", a: "Time-aware holdouts (train on past, test on future), cross-validation, and — crucially — monitoring the live metric after deployment." },
    ],
    related: ["k-means-clustering", "data-drift", "outlier-detection", "missing-value-imputation"],
    updated: "2026-04-15",
  },
  {
    slug: "missing-value-imputation",
    term: "Missing Value Imputation",
    question: "What is missing value imputation?",
    shortDef:
      "Filling in missing data with estimated values so downstream analysis and models can run without dropping rows.",
    description:
      "Missing value imputation replaces gaps in a dataset with estimated values. Learn mean/median imputation, KNN, MICE, and when to use which.",
    answer:
      "Missing value imputation is the process of filling gaps in a dataset with estimated values so analysis and machine-learning models can use the row instead of dropping it. The right method depends on whether the data is missing completely at random (MCAR), at random (MAR), or not at random (MNAR).",
    stats: [
      {
        value: "Listwise deletion",
        label: "can discard up to 60% of rows in real-world surveys, severely biasing results — the original problem imputation was invented to solve.",
        source: { label: "Schafer & Graham, Missing Data: Our View of the State of the Art (2002)", url: "https://psycnet.apa.org/doi/10.1037/1082-989X.7.2.147" },
      },
      {
        value: "MICE (m=5)",
        label: "Multiple Imputation by Chained Equations with 5 imputations is the academic gold standard recommended by the FDA for clinical trials.",
        source: { label: "FDA — Guidance on Missing Data in Clinical Trials", url: "https://www.fda.gov/regulatory-information/search-fda-guidance-documents" },
      },
    ],
    sections: [
      {
        heading: "Method ladder (cheap → rigorous)",
        html: `<ol>
          <li><strong>Drop</strong> — only safe if missingness is &lt;5% and MCAR.</li>
          <li><strong>Constant fill</strong> — 0 / "Unknown" — fast, leaks no info, but biases distributions.</li>
          <li><strong>Mean / median / mode</strong> — preserves central tendency, shrinks variance.</li>
          <li><strong>KNN imputation</strong> — fills based on similar rows; good when features correlate.</li>
          <li><strong>MICE / iterative imputer</strong> — models each missing column from the others; statistically sound.</li>
          <li><strong>Domain rule</strong> — sometimes "missing = no" is the most accurate possible imputation.</li>
        </ol>`,
      },
      {
        heading: "Always add a missingness flag",
        html: `<p>Whatever you impute, also create a binary <code>was_missing</code> column. Models can learn that "the customer didn't fill in their phone number" is itself predictive — a signal you destroy by silent imputation.</p>`,
      },
    ],
    faq: [
      { q: "When is dropping rows OK?", a: "When missingness is under ~5% and there's no plausible reason it correlates with the target. Otherwise impute." },
      { q: "Is mean imputation bad?", a: "It's not bad, it's blunt. It shrinks variance and weakens correlations. Fine for a quick first pass; weak for production models." },
      { q: "What is MNAR and why does it matter?", a: "Missing Not At Random — the missingness itself depends on the unknown value (e.g., high earners refuse to disclose income). No imputation method fully solves MNAR; you need extra information or a sensitivity analysis." },
      { q: "Should I impute the target column?", a: "No. Drop rows where the target is missing for training. Imputing the target invents the answer and leaks." },
      { q: "Does DataVision Pro impute automatically?", a: "Yes — its auto-cleaning includes mean/median/mode imputation as a toggleable substep, and you can insert custom rules (Replace Values, Drop Column) above or below it." },
    ],
    related: ["data-cleaning", "outlier-detection", "descriptive-statistics", "predictive-analytics"],
    updated: "2026-04-15",
  },
  {
    slug: "normalization",
    term: "Normalization",
    question: "What is data normalization?",
    shortDef:
      "Rescaling numeric features onto a common scale (typically 0–1 or mean 0 / std 1) so they contribute comparably to a model.",
    description:
      "Data normalization rescales numeric columns so features measured in different units contribute comparably to a model. Learn min-max, z-score, and robust scaling — and when to use each.",
    answer:
      "Normalization is the process of rescaling numeric features so they share a common range or distribution — typically 0–1 (min-max), mean 0 / std 1 (z-score), or median 0 / IQR 1 (robust scaling). It is required for any model that uses Euclidean distance or gradient descent, including K-Means, KNN, SVMs, and neural networks.",
    stats: [
      {
        value: "10×–100×",
        label: "Typical convergence speedup for gradient-descent training when input features are normalized to comparable scales.",
        source: { label: "LeCun et al., Efficient BackProp (1998)", url: "http://yann.lecun.com/exdb/publis/pdf/lecun-98b.pdf" },
      },
      {
        value: "Z-score = (x − μ) / σ",
        label: "Standardisation formula — produces a feature with mean 0 and standard deviation 1, the default for scikit-learn's StandardScaler.",
        source: { label: "scikit-learn — Preprocessing data", url: "https://scikit-learn.org/stable/modules/preprocessing.html" },
      },
    ],
    sections: [
      {
        heading: "The three common scalers",
        html: `<ul>
          <li><strong>Min-max</strong> — maps to [0, 1]. Sensitive to outliers; great for image pixels and bounded inputs.</li>
          <li><strong>Z-score (standardisation)</strong> — mean 0, std 1. The safe default for most tabular ML.</li>
          <li><strong>Robust scaler</strong> — uses median and IQR instead of mean and std. Best when the column has outliers you cannot remove.</li>
        </ul>`,
      },
      {
        heading: "Normalization vs standardisation",
        html: `<p>Strictly, "normalization" means rescaling to a fixed range (usually 0–1) and "standardisation" means rescaling to mean 0 / std 1. In practice the words are used interchangeably — what matters is that you fit the scaler on training data only and apply it (without refitting) to validation, test, and production data.</p>`,
      },
      {
        heading: "When you do not need it",
        html: `<p>Tree-based models — Random Forest, XGBoost, LightGBM — are scale-invariant and do not benefit from normalization. Skipping it for trees keeps feature interpretability intact. DataVision Pro applies z-score scaling automatically before K-Means clustering and skips it for tree models.</p>`,
      },
    ],
    faq: [
      { q: "Should I normalize the target variable?", a: "For regression, optionally yes — it can stabilise loss values. Always invert the transform before reporting predictions in business units." },
      { q: "Min-max or z-score by default?", a: "Z-score for tabular ML; min-max for image pixels and any input that already has a meaningful bounded range." },
      { q: "Do I refit the scaler on new data?", a: "No. Fit once on training data, then apply the saved scaler to all new data. Refitting leaks information across splits." },
      { q: "What about categorical features?", a: "Don't normalize them. One-hot encode or target-encode first; numeric scaling applies only to true numeric columns." },
      { q: "Does normalization fix skewed distributions?", a: "No — it only rescales. To reduce skew, log-transform or Box-Cox first, then normalize the result." },
    ],
    related: ["k-means-clustering", "data-cleaning", "predictive-analytics", "descriptive-statistics"],
    updated: "2026-04-21",
  },
  {
    slug: "time-series",
    term: "Time Series Analysis",
    question: "What is time series analysis?",
    shortDef:
      "Statistical methods for analysing data points indexed in time order to find trend, seasonality, and forecast future values.",
    description:
      "Time series analysis finds trend, seasonality, and autocorrelation in data ordered by time, then uses them to forecast. Learn decomposition, ARIMA, Prophet, and the holdout discipline that keeps forecasts honest.",
    answer:
      "Time series analysis is the study of data points collected sequentially over time — sales by day, temperature by hour, page views by minute. It decomposes the series into trend, seasonality, and residual components, models the dependency between consecutive observations, and uses the result to forecast future values with an explicit error band.",
    stats: [
      {
        value: "2 full cycles",
        label: "Minimum history required for a model to learn seasonality reliably — e.g. 24 months of monthly data for annual seasonality.",
        source: { label: "Hyndman & Athanasopoulos, Forecasting: Principles and Practice (3rd ed.)", url: "https://otexts.com/fpp3/" },
      },
      {
        value: "MAPE 5–10%",
        label: "Industry benchmark for an excellent monthly demand forecast on established products; new products typically land at 15–25%.",
        source: { label: "Institute of Business Forecasting & Planning — Forecast Accuracy Benchmarks", url: "https://ibf.org/knowledge/journal-of-business-forecasting/" },
      },
    ],
    sections: [
      {
        heading: "The classic decomposition",
        html: `<p>Every time series can be split into three pieces:</p>
        <ul>
          <li><strong>Trend</strong> — the long-run direction (growing, shrinking, flat).</li>
          <li><strong>Seasonality</strong> — repeating patterns at a fixed period (weekly, monthly, annual).</li>
          <li><strong>Residual</strong> — what's left after removing trend and seasonality; ideally pure noise.</li>
        </ul>
        <p>Looking at the decomposition before modelling tells you whether to use additive (constant seasonality) or multiplicative (seasonality grows with the level) models.</p>`,
      },
      {
        heading: "Common model families",
        html: `<ul>
          <li><strong>Naive / seasonal naive</strong> — the baseline every other model must beat.</li>
          <li><strong>Exponential smoothing (ETS)</strong> — fast, robust, great for short series with seasonality.</li>
          <li><strong>ARIMA / SARIMA</strong> — captures autocorrelation; needs a stationary series.</li>
          <li><strong>Prophet</strong> — Meta's open-source library; tolerates missing data and holiday effects.</li>
          <li><strong>Tree-based regressors with lag features</strong> — Random Forest / XGBoost on lagged columns; the modern default for tabular forecasting.</li>
        </ul>`,
      },
      {
        heading: "The non-negotiable: time-aware holdouts",
        html: `<p>Never shuffle a time series before splitting. Train on the past, test on the future. DataVision Pro's predictions tab enforces this by holding out the most recent N periods and reporting MAPE on that window — the only honest accuracy estimate for forecasting.</p>`,
      },
    ],
    faq: [
      { q: "Is time series the same as regression?", a: "No — regression assumes independent observations. Time series observations are correlated with their own past, which requires different validation and model families." },
      { q: "Do I need to make the series stationary?", a: "ARIMA-family models need stationarity (differencing usually achieves it). Prophet and tree-based models do not." },
      { q: "How do I handle missing dates?", a: "Fill explicit zeros for periods where the count was genuinely zero, and impute or interpolate periods where the data was simply not collected. The two are very different." },
      { q: "Can I forecast a single number?", a: "You can, but you shouldn't. Always report a range — point estimate ± holdout error — so consumers know how much uncertainty to budget for." },
      { q: "What about external regressors like marketing spend?", a: "Useful only if their future values are known at forecast time. Planned spend works; reactive spend that depends on sales does not." },
    ],
    related: ["predictive-analytics", "data-drift", "descriptive-statistics", "data-cleaning"],
    updated: "2026-04-21",
  },
  {
    slug: "ab-testing",
    term: "A/B Testing",
    question: "What is A/B testing?",
    shortDef:
      "A controlled experiment that randomly splits users between two versions and measures which produces a better outcome on a chosen metric.",
    description:
      "A/B testing randomly splits users between two variants and measures which produces a better outcome. Learn power analysis, sample-size calculation, p-values, and the pitfalls that invalidate most tests.",
    answer:
      "A/B testing is a controlled experiment that randomly assigns users to one of two variants (control A, treatment B) and measures which produces a better outcome on a pre-declared metric. Done right it provides causal evidence; done wrong — peeking, multiple comparisons, under-powering — it produces confident-looking conclusions that do not replicate.",
    stats: [
      {
        value: "10–20%",
        label: "Typical share of A/B tests at mature experimentation programs that show a statistically significant lift — most ideas don't beat control.",
        source: { label: "Kohavi, Tang & Xu — Trustworthy Online Controlled Experiments (2020)", url: "https://experimentguide.com" },
      },
      {
        value: "n ≈ 16 · σ² / δ²",
        label: "Per-arm sample-size approximation for detecting effect δ with 80% power at α = 0.05 — the formula every PM should memorise.",
        source: { label: "Lehr's rule of thumb, NIST/SEMATECH e-Handbook of Statistical Methods", url: "https://www.itl.nist.gov/div898/handbook/" },
      },
    ],
    sections: [
      {
        heading: "How to run a trustworthy test",
        html: `<ol>
          <li><strong>Pre-register</strong> the hypothesis, primary metric, and minimum detectable effect.</li>
          <li><strong>Power-analyse</strong> to compute the sample size you need before launching.</li>
          <li><strong>Randomise</strong> at the right unit (user, session, or device — never request).</li>
          <li><strong>Don't peek</strong> — checking results daily and stopping when you "see significance" inflates the false-positive rate well above 5%.</li>
          <li><strong>Run for full business cycles</strong> — at least one full week to capture weekday vs weekend behaviour.</li>
          <li><strong>Report effect size with a confidence interval</strong>, not just a p-value.</li>
        </ol>`,
      },
      {
        heading: "What invalidates most tests",
        html: `<ul>
          <li><strong>Sample-ratio mismatch</strong> — if your 50/50 split lands at 48/52, the randomisation is broken and the result is suspect.</li>
          <li><strong>Novelty and primacy effects</strong> — short tests on UX changes capture reaction, not long-run behaviour.</li>
          <li><strong>Multiple comparisons</strong> — testing 10 metrics at α = 0.05 yields one false positive on average per test.</li>
          <li><strong>Interaction with concurrent tests</strong> — overlapping experiments need orthogonal randomisation or you measure their combination.</li>
        </ul>`,
      },
    ],
    faq: [
      { q: "What sample size do I need?", a: "It depends on baseline rate, minimum detectable effect, and desired power. For a 5% baseline conversion and a 1-percentage-point lift at 80% power, you need roughly 30,000 users per arm." },
      { q: "Is p < 0.05 enough?", a: "It's the convention, not the truth. Pair it with a confidence interval, a pre-registered hypothesis, and a sanity check that the lift is large enough to matter commercially." },
      { q: "Can I stop early if I see a winner?", a: "Only with a sequential test design (e.g. group-sequential or always-valid p-values). Naive early stopping doubles your false-positive rate." },
      { q: "Is A/B testing the same as multivariate testing?", a: "No. A/B compares two versions; multivariate tests several factors simultaneously to find the best combination — and needs much larger samples." },
      { q: "Can I A/B test in DataVision Pro?", a: "DataVision Pro analyses the results of an A/B test you've already run — load both arms, compute lift, confidence interval, and statistical significance side-by-side using the time-period comparison view." },
    ],
    related: ["descriptive-statistics", "predictive-analytics", "data-drift", "outlier-detection"],
    updated: "2026-04-21",
  },
  {
    slug: "anomaly-detection",
    term: "Anomaly Detection",
    question: "What is anomaly detection?",
    shortDef:
      "Identifying observations or patterns that do not conform to expected behaviour, typically signalling fraud, faults, or genuinely new events.",
    description:
      "Anomaly detection identifies observations that violate an expected pattern, signalling fraud, faults, or new behaviour. Learn the difference vs outlier detection, the main algorithm families, and how to evaluate them.",
    answer:
      "Anomaly detection is the practice of identifying observations or patterns that violate expected behaviour — fraudulent transactions, failing equipment, sudden traffic spikes. Unlike outlier detection (which is purely statistical), anomaly detection is contextual: a $50 sale at 3 a.m. may be normal in one segment and an alarm in another.",
    stats: [
      {
        value: "$485B",
        label: "Estimated global cost of payments fraud in 2023 — the single largest commercial application of anomaly detection.",
        source: { label: "Nilson Report — Card Fraud Worldwide (Issue 1232, 2023)", url: "https://nilsonreport.com/" },
      },
      {
        value: "Precision@k",
        label: "The most-used anomaly-detection metric in production, because alert fatigue (false positives) costs more than missed alerts in most ops teams.",
        source: { label: "Aggarwal, Outlier Analysis (2nd ed., 2017)", url: "https://link.springer.com/book/10.1007/978-3-319-47578-3" },
      },
    ],
    sections: [
      {
        heading: "Anomaly vs outlier",
        html: `<p>Outliers are points that sit far from the statistical centre of a single distribution. Anomalies are points that violate an <em>expected pattern</em> — which may be a function of time, segment, or other features. All anomalies are usually outliers in some projection of the data; not all outliers are anomalies.</p>`,
      },
      {
        heading: "Algorithm families",
        html: `<ul>
          <li><strong>Statistical</strong> — z-score, IQR, EWMA control charts. Fast, interpretable, ideal for univariate streams.</li>
          <li><strong>Distance / density</strong> — k-NN, LOF, DBSCAN. Great for low-to-medium-dimensional unlabeled data.</li>
          <li><strong>Tree-based</strong> — Isolation Forest. Strong default for tabular anomaly detection.</li>
          <li><strong>Reconstruction-based</strong> — autoencoders trained on "normal" data flag inputs they reconstruct poorly.</li>
          <li><strong>Forecast-residual</strong> — fit a time-series model and alert when actuals diverge from prediction.</li>
        </ul>`,
      },
      {
        heading: "How to evaluate without labels",
        html: `<p>True anomaly labels are rare. Two practical substitutes:</p>
        <ul>
          <li><strong>Precision@k</strong> — have a human review the top-k flagged events and score how many were real.</li>
          <li><strong>Injected anomalies</strong> — synthesise known anomalies into a holdout window and measure recall.</li>
        </ul>
        <p>DataVision Pro's K-Means risk clustering view doubles as a coarse anomaly detector — points that sit far from any cluster centroid are the operational candidates worth investigating first.</p>`,
      },
    ],
    faq: [
      { q: "Is anomaly detection supervised or unsupervised?", a: "Usually unsupervised because labelled anomalies are rare. Semi-supervised setups (train on known-good data, flag deviations) are common in fraud and IoT." },
      { q: "How do I avoid alert fatigue?", a: "Threshold for precision, not recall. Tune the score cutoff so the top-k alerts a human can actually triage are mostly real." },
      { q: "Does seasonality cause false alarms?", a: "Yes — a Monday-morning traffic spike is a routine pattern, not an anomaly. Use seasonal decomposition or forecast-residual methods to handle it." },
      { q: "Can I use the same method for fraud and equipment failure?", a: "The math overlaps (Isolation Forest works for both), but the features and review workflows differ enormously. Treat them as distinct projects." },
      { q: "How is this different from outlier detection?", a: "Outlier detection is statistical and unconditional. Anomaly detection is contextual and considers time, segment, and expected patterns." },
    ],
    related: ["outlier-detection", "k-means-clustering", "predictive-analytics", "data-drift"],
    updated: "2026-04-21",
  },
];

export const getEntry = (slug: string) => GLOSSARY.find((e) => e.slug === slug);
