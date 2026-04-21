---
term: "Data Drift"
question: "What is data drift?"
shortDef: "A change over time in the statistical properties of input data that degrades a model's accuracy."
description: "Data drift is when the distribution of incoming data shifts from what a model was trained on, silently degrading accuracy. Learn the types, detection methods, and mitigations."
answer: "Data drift is the change over time in the statistical properties of input features — for example, a customer-age distribution that shifts from a mean of 32 to a mean of 41. Drift causes machine-learning models to silently lose accuracy because the patterns they learned no longer reflect production data."
stats:
  - value: "91%"
    label: "of ML models degrade in performance over time once deployed, according to a 2022 production-ML survey."
    source:
      label: "MIT Sloan / Scientific Reports — AI model degradation (2022)"
      url: "https://www.nature.com/articles/s41598-022-15245-z"
  - value: "Population Stability Index (PSI) > 0.2"
    label: "is the credit-risk industry's standard threshold for declaring a feature has materially drifted and a model rebuild is needed."
    source:
      label: "Karakoulas, PSI in credit scoring"
      url: "https://en.wikipedia.org/wiki/Population_stability_index"
faq:
  - q: "Is data drift the same as concept drift?"
    a: "Concept drift is one type of data drift — specifically when the relationship between inputs and the target changes. Data drift is the umbrella term."
  - q: "How often should I check for drift?"
    a: "Match the cadence of business decisions. Weekly is a good default for most operational ML; daily for fraud and ads."
  - q: "Will more data fix drift?"
    a: "Only if the new data reflects the new world. Stale training data of any size cannot fix drift — recency matters more than volume."
  - q: "What's a good drift dashboard?"
    a: "PSI per feature with a colour-coded threshold (green < 0.1, amber 0.1–0.2, red > 0.2) plus a chart of model accuracy on a holdout slice."
  - q: "Does drift apply to non-ML analytics?"
    a: "Yes — even simple KPI dashboards can mislead when the underlying customer mix shifts. Drift is a data problem, not just an ML problem."
related:
  - "predictive-analytics"
  - "data-cleaning"
  - "descriptive-statistics"
  - "k-means-clustering"
updated: "2026-04-15"
---

## Three flavours of drift

<ul>
          <li><strong>Covariate drift</strong> — P(X) changes (your inputs look different).</li>
          <li><strong>Prior probability drift</strong> — P(Y) changes (the base rate of the target shifts).</li>
          <li><strong>Concept drift</strong> — P(Y|X) changes (the relationship itself moves — the rules of the game change).</li>
        </ul>

## How to detect it

<p>Compare a recent window of production data against the training reference window using:</p>
        <ul>
          <li>Population Stability Index (PSI) — bin-based, easy to threshold.</li>
          <li>Kolmogorov–Smirnov test — for continuous features.</li>
          <li>Chi-square test — for categorical features.</li>
          <li>Wasserstein / Jensen–Shannon distance — for full-distribution comparisons.</li>
        </ul>

## What to do about it

<p>Retrain on a sliding window, add monitoring alerts at PSI thresholds, or switch to an online-learning model. In DataVision Pro, the time-period comparison view lets analysts spot drift visually before it shows up in business KPIs.</p>
