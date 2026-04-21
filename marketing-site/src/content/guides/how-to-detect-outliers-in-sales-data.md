---
title: "How to detect outliers in sales data"
description: "A practical guide to spotting outliers in sales data using IQR, z-score, and K-Means clustering — without writing code."
intro: "To detect outliers in sales data: load the dataset, run descriptive statistics to see the distribution, apply IQR (Tukey's 1.5×) or z-score thresholds to flag candidates, then use K-Means clustering to separate one-off weird transactions from emerging patterns. Always investigate before deleting — outliers often contain the most valuable signal."
estTime: "5 minutes"
difficulty: "Intermediate"
prerequisites:
  - "A cleaned sales dataset (date, customer, product, quantity, revenue)."
  - "Familiarity with the difference between an outlier and a typo."
pitfalls:
  - "Using z-score on heavily skewed sales data — it under-flags genuine outliers."
  - "Deleting outliers without checking whether they correlate with a known event (Black Friday, a new SKU launch)."
  - "Running K-Means on un-scaled features — revenue in dollars will dominate quantity in units."
faq:
  - q: "Should I winsorise?"
    a: "Winsorising (capping at the 1st and 99th percentile) is fine for downstream linear models that are sensitive to outliers, but only after you've documented why each capped value was anomalous."
  - q: "How many outliers are 'too many'?"
    a: "Roughly 0.7% of points exceed |z|>3 in a normal distribution. If your column has 5%+ outliers, the distribution is not normal and you should switch to IQR-based methods."
  - q: "Can outliers signal fraud?"
    a: "Yes — most fraud-detection systems start with a simple outlier rule before adding ML. A single $50,000 transaction from a normally $50/day customer is the textbook signal."
updated: "2026-04-15"
relatedGlossary:
- outlier-detection
- k-means-clustering
- anomaly-detection
- normalization
relatedCompare:
- datavision-pro-vs-excel
- datavision-pro-vs-tableau
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/glossary/outlier-detection">outlier detection</a> · <a href="/glossary/k-means-clustering">k-means clustering</a> · <a href="/glossary/anomaly-detection">anomaly detection</a> · <a href="/glossary/normalization">normalization</a>.</p>

## Profile the revenue column

<p>Open the <strong>Statistics</strong> tab and look at the 5-number summary for revenue. A median of $480 with a max of $1,250,000 instantly tells you the right tail is doing something interesting.</p>

## Visualise with a box plot

<p>In the <strong>Visualisations</strong> tab, build a box plot of revenue, optionally split by region or product category. Anything plotted beyond the whiskers (1.5×IQR above Q3 or below Q1) is a Tukey outlier.</p>

## Cross-check with z-scores

<p>Add a calculated column <code>z = (revenue − mean) / std</code>. Rows with |z| &gt; 3 are statistical outliers under a normal-distribution assumption. If your data is heavily skewed (most sales data is), trust the IQR result more.</p>

## Cluster to find new patterns

<p>Open the <strong>ML &amp; Clustering</strong> tab and run K-Means with K = 3 on revenue + quantity + customer-tenure. If a cluster of 50 customers all sit in the "outlier" zone, that's not noise — that's a segment.</p>

## Decide: drop, flag, or escalate

<p>Three buckets: <em>impossible</em> values (negative quantity → drop), <em>plausible but rare</em> (one-time bulk order → flag and keep), <em>pattern-forming</em> (new high-value segment → escalate to sales).</p>
