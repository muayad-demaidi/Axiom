---
term: "Outlier Detection"
question: "What is outlier detection?"
shortDef: "Statistical techniques for finding observations that lie an abnormal distance from the rest of a dataset."
description: "Outlier detection identifies data points that deviate significantly from the rest of the dataset. Learn IQR, z-score, and ML-based methods, and when to drop vs. investigate."
answer: "Outlier detection is the process of identifying observations that differ significantly from other points in a dataset, often signalling errors, fraud, or genuinely interesting events. Common techniques include the interquartile range (IQR) rule, z-scores, isolation forests, and DBSCAN. Outliers are not always bad — sometimes they are the entire signal."
stats:
  - value: "1.5 × IQR"
    label: "Tukey's classic threshold for flagging a point as an outlier in a box plot — still the most-used rule in industry."
    source:
      label: "Tukey, Exploratory Data Analysis (1977)"
      url: "https://en.wikipedia.org/wiki/Outlier#Tukey%27s_fences"
  - value: "$5.4 trillion"
    label: "Estimated global cost of fraud in 2023 — a category that lives or dies on outlier detection."
    source:
      label: "Crowe Global Fraud Report 2023"
      url: "https://www.crowe.com/global/insights/financial-cost-of-fraud-2023"
faq:
  - q: "What's the difference between an outlier and an anomaly?"
    a: "Outliers are statistical — they sit far from the distribution. Anomalies are contextual — they violate an expected pattern. All anomalies are usually outliers, but not vice versa."
  - q: "Is z-score or IQR better?"
    a: "IQR is more robust to non-normal data. Z-score assumes a roughly normal distribution; if your data is skewed (revenue, page views), prefer IQR or modified z-score."
  - q: "Should I remove outliers before training a model?"
    a: "It depends. Tree-based models (Random Forest, XGBoost) tolerate outliers; linear regression and k-means are highly sensitive."
  - q: "How does DBSCAN find outliers?"
    a: "DBSCAN labels points that have fewer than min_samples neighbours within ε as 'noise' — a natural outlier flag with no need to set thresholds per column."
  - q: "Can outliers be useful?"
    a: "Yes — fraud, intrusion, equipment failure, and viral content are all outliers. The signal often lives in the tail."
related:
  - "data-cleaning"
  - "k-means-clustering"
  - "descriptive-statistics"
  - "predictive-analytics"
updated: "2026-04-15"
relatedGuides:
- how-to-detect-outliers-in-sales-data
relatedCompare:
- datavision-pro-vs-excel
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/guides/how-to-detect-outliers-in-sales-data">how to detect outliers in sales data</a> · <a href="/compare/datavision-pro-vs-excel">AXIOM vs Excel</a>.</p>

## How it works

<p>Three families of methods cover ~90% of business cases:</p>
        <ul>
          <li><strong>Statistical</strong> — IQR rule, z-score (|z| &gt; 3), or modified z-score for skewed data.</li>
          <li><strong>Distance-based</strong> — k-nearest-neighbour distance, DBSCAN density, or Mahalanobis distance for multivariate cases.</li>
          <li><strong>Model-based</strong> — Isolation Forest and One-Class SVM for high-dimensional unlabeled data.</li>
        </ul>

## When to drop and when to investigate

<p>Drop only if you can prove the value is impossible (negative age, future timestamp). Investigate when the value is merely surprising — a $50,000 order from a normally-$500 customer is an outlier you want to <em>understand</em>, not delete.</p>
        <p>AXIOM shows enhanced outlier detection with box plots and K-Means risk clustering side-by-side, so you can see whether a point is a single weird record or a whole cluster of new behaviour.</p>
