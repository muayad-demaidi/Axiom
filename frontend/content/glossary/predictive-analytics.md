---
term: "Predictive Analytics"
question: "What is predictive analytics?"
shortDef: "Using historical data and statistical or ML models to forecast future outcomes or behaviours."
description: "Predictive analytics uses historical data to forecast future outcomes — sales, churn, demand. Learn the model families, evaluation metrics, and pitfalls."
answer: "Predictive analytics is the practice of using historical data, statistics, and machine learning to forecast future outcomes such as next-quarter revenue, customer churn, equipment failure, or fraud risk. It sits between descriptive analytics (what happened) and prescriptive analytics (what to do about it)."
stats:
  - value: "$22.1B → $67.7B"
    label: "Global predictive-analytics market projected growth between 2023 and 2028, a 25%+ compound annual growth rate."
    source:
      label: "MarketsandMarkets — Predictive Analytics Market 2023"
      url: "https://www.marketsandmarkets.com/Market-Reports/predictive-analytics-market-1181.html"
  - value: "5–25%"
    label: "Typical revenue lift retailers report from churn-prediction-driven retention campaigns vs. blanket campaigns."
    source:
      label: "Bain & Company — The Value of Online Customer Loyalty"
      url: "https://www.bain.com/insights/the-value-of-online-customer-loyalty"
faq:
  - q: "Do I need a data scientist?"
    a: "Not for the common patterns. AXIOM's predictions tab covers linear models and tree-based forecasting in a few clicks."
  - q: "How much history do I need?"
    a: "For seasonal forecasts, at least two full cycles (e.g. 24 months for monthly seasonality). For classification, at least a few hundred examples per class."
  - q: "What's the biggest pitfall?"
    a: "Target leakage — accidentally using a feature that is only known after the outcome occurred. It produces unrealistically good test scores and miserable production performance."
  - q: "How is it different from forecasting?"
    a: "Forecasting is a subset focused on time-series outputs. Predictive analytics also covers classification, ranking, and risk scoring."
  - q: "How do you validate a predictive model?"
    a: "Time-aware holdouts (train on past, test on future), cross-validation, and — crucially — monitoring the live metric after deployment."
related:
  - "k-means-clustering"
  - "data-drift"
  - "outlier-detection"
  - "missing-value-imputation"
updated: "2026-04-15"
relatedGuides:
- how-to-build-a-3-month-sales-forecast
relatedCompare:
- datavision-pro-vs-power-bi
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/guides/how-to-build-a-3-month-sales-forecast">how to build a 3-month sales forecast</a> · <a href="/compare/datavision-pro-vs-power-bi">AXIOM vs Power BI</a>.</p>

## Common model families

<ul>
          <li><strong>Linear regression</strong> — interpretable, fast, baseline.</li>
          <li><strong>Logistic regression</strong> — yes/no outcomes (churn, fraud).</li>
          <li><strong>Tree ensembles</strong> — Random Forest, XGBoost, LightGBM. Strongest default for tabular data.</li>
          <li><strong>Time-series</strong> — ARIMA, Prophet, ETS for forecasting with trend and seasonality.</li>
          <li><strong>Neural networks</strong> — when you have lots of data and weak feature engineering.</li>
        </ul>

## How to know it's working

<p>Pick a metric that matches the business cost: RMSE for forecasts, AUC for ranking, recall@k for fraud, MAPE for finance. A predictive model that improves a metric on a holdout set but never moves a business KPI is a science-fair project, not analytics.</p>
