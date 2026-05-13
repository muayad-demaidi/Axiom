---
term: Anomaly Detection
question: What is anomaly detection?
shortDef: Identifying observations or patterns that do not conform to expected behaviour, typically signalling fraud, faults, or genuinely new events.
description: Anomaly detection identifies observations that violate an expected pattern, signalling fraud, faults, or new behaviour. Learn the difference vs outlier detection, the main algorithm families, and how to evaluate them.
answer: 'Anomaly detection is the practice of identifying observations or patterns that violate expected behaviour — fraudulent transactions, failing equipment, sudden traffic spikes. Unlike outlier detection (which is purely statistical), anomaly detection is contextual: a $50 sale at 3 a.m. may be normal in one segment and an alarm in another.'
stats:
- value: $485B
  label: Estimated global cost of payments fraud in 2023 — the single largest commercial application of anomaly detection.
  source:
    label: Nilson Report — Card Fraud Worldwide (Issue 1232, 2023)
    url: https://nilsonreport.com/
- value: Precision@k
  label: The most-used anomaly-detection metric in production, because alert fatigue (false positives) costs more than missed alerts in most ops teams.
  source:
    label: Aggarwal, Outlier Analysis (2nd ed., 2017)
    url: https://link.springer.com/book/10.1007/978-3-319-47578-3
faq:
- q: Is anomaly detection supervised or unsupervised?
  a: Usually unsupervised because labelled anomalies are rare. Semi-supervised setups (train on known-good data, flag deviations) are common in fraud and IoT.
- q: How do I avoid alert fatigue?
  a: Threshold for precision, not recall. Tune the score cutoff so the top-k alerts a human can actually triage are mostly real.
- q: Does seasonality cause false alarms?
  a: Yes — a Monday-morning traffic spike is a routine pattern, not an anomaly. Use seasonal decomposition or forecast-residual methods to handle it.
- q: Can I use the same method for fraud and equipment failure?
  a: The math overlaps (Isolation Forest works for both), but the features and review workflows differ enormously. Treat them as distinct projects.
- q: How is this different from outlier detection?
  a: Outlier detection is statistical and unconditional. Anomaly detection is contextual and considers time, segment, and expected patterns.
related:
- outlier-detection
- k-means-clustering
- predictive-analytics
- data-drift
updated: '2026-04-21'
relatedGuides:
- how-to-detect-outliers-in-sales-data
relatedCompare:
- axiom.ai-vs-metabase
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/guides/how-to-detect-outliers-in-sales-data">how to detect outliers in sales data</a> · <a href="/compare/axiom.ai-vs-metabase">AXIOM vs Metabase</a>.</p>

## Anomaly vs outlier

<p>Outliers are points that sit far from the statistical centre of a single distribution. Anomalies are points that violate an <em>expected pattern</em> — which may be a function of time, segment, or other features. All anomalies are usually outliers in some projection of the data; not all outliers are anomalies.</p>

## Algorithm families

<ul>
          <li><strong>Statistical</strong> — z-score, IQR, EWMA control charts. Fast, interpretable, ideal for univariate streams.</li>
          <li><strong>Distance / density</strong> — k-NN, LOF, DBSCAN. Great for low-to-medium-dimensional unlabeled data.</li>
          <li><strong>Tree-based</strong> — Isolation Forest. Strong default for tabular anomaly detection.</li>
          <li><strong>Reconstruction-based</strong> — autoencoders trained on "normal" data flag inputs they reconstruct poorly.</li>
          <li><strong>Forecast-residual</strong> — fit a time-series model and alert when actuals diverge from prediction.</li>
        </ul>

## How to evaluate without labels

<p>True anomaly labels are rare. Two practical substitutes:</p>
        <ul>
          <li><strong>Precision@k</strong> — have a human review the top-k flagged events and score how many were real.</li>
          <li><strong>Injected anomalies</strong> — synthesise known anomalies into a holdout window and measure recall.</li>
        </ul>
        <p>AXIOM's K-Means risk clustering view doubles as a coarse anomaly detector — points that sit far from any cluster centroid are the operational candidates worth investigating first.</p>
