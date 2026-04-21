---
term: "Descriptive Statistics"
question: "What is descriptive statistics?"
shortDef: "Summary measures (mean, median, std, percentiles) that describe the central tendency and spread of a dataset."
description: "Descriptive statistics summarise a dataset's central tendency, spread, and shape. Learn the core measures and which ones lie when your data is skewed."
answer: "Descriptive statistics are summary numbers — mean, median, mode, standard deviation, min, max, and percentiles — that describe the shape of a dataset without making predictions. They are the first thing every analyst computes after loading a file because they reveal scale, skew, and obviously broken columns in seconds."
stats:
  - value: "5-number summary"
    label: "min, Q1, median, Q3, max — Tukey's compact descriptor that fits on a box plot and explains a column at a glance."
    source:
      label: "Tukey, Exploratory Data Analysis (1977)"
      url: "https://en.wikipedia.org/wiki/Five-number_summary"
  - value: "Mean ≠ Median"
    label: "When the absolute gap exceeds 10–15% of the standard deviation, the column is meaningfully skewed and the mean alone will mislead."
    source:
      label: "Wilcox, Modern Robust Methods"
      url: "https://link.springer.com/book/10.1007/978-1-4419-5525-8"
faq:
  - q: "Is descriptive statistics the same as inferential statistics?"
    a: "No. Descriptive describes the data you have. Inferential generalises from a sample to a larger population using probability."
  - q: "Should I report mean or median?"
    a: "Report both. Mean is sensitive to outliers; median is robust. The gap between them is itself a useful diagnostic."
  - q: "What's a good standard deviation?"
    a: "There is no universal answer — std is meaningful only relative to the mean (coefficient of variation = std / mean) or to a domain benchmark."
  - q: "Why does DataVision Pro show currency codes in the stats table?"
    a: "Because mean revenue of 1,200 means very different things in JPY vs USD — the unit is part of the answer, not metadata."
  - q: "Are percentiles better than std for skewed data?"
    a: "Usually yes. P50/P90/P99 describe customer experience more honestly than mean ± std when the distribution has a long tail."
related:
  - "data-cleaning"
  - "outlier-detection"
  - "predictive-analytics"
  - "data-drift"
updated: "2026-04-15"
relatedGuides:
- how-to-compare-this-quarter-vs-last-quarter
- how-to-ab-test-a-pricing-change
relatedCompare:
- datavision-pro-vs-excel
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/guides/how-to-compare-this-quarter-vs-last-quarter">how to compare this quarter vs last quarter</a> · <a href="/guides/how-to-ab-test-a-pricing-change">how to A/B test a pricing change</a> · <a href="/compare/datavision-pro-vs-excel">DataVision Pro vs Excel</a>.</p>

## The core measures

<ul>
          <li><strong>Central tendency</strong> — mean, median, mode.</li>
          <li><strong>Spread</strong> — variance, standard deviation, IQR, range.</li>
          <li><strong>Shape</strong> — skewness, kurtosis.</li>
          <li><strong>Position</strong> — percentiles, quartiles.</li>
        </ul>

## When the mean lies

<p>Income, revenue, page-view, and time-on-site distributions are almost always right-skewed. Reporting only the mean overstates the typical experience. Always pair mean with median, or report the full 5-number summary. DataVision Pro's descriptive-statistics table includes both and flags skew automatically.</p>
