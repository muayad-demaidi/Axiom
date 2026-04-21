---
title: "How to build a 3-month sales forecast (no code)"
description: "Step-by-step: turn 24 months of sales history into a defensible 3-month forecast using DataVision Pro's predictions tab — with honest accuracy bounds."
intro: "To build a 3-month sales forecast: gather at least 24 months of monthly sales (two full seasonal cycles), load it into DataVision Pro, fit a linear-trend or RandomForest model in the Predictions tab, hold out the last three months to measure error, then apply the validated model to forecast the next three months — and report the error band, not a single number."
estTime: "10 minutes"
difficulty: "Intermediate"
prerequisites:
  - "≥ 24 months of monthly sales data (date, revenue)."
  - "Knowledge of obvious external events (promotions, launches) so you can mark them as features."
pitfalls:
  - "Forecasting from 6 months of history — the model has no chance of learning seasonality."
  - "Reporting a single forecast number to leadership without an error band invites a board-meeting cross-examination."
  - "Including post-holdout features (e.g., this month's marketing spend) leaks the future into the past."
faq:
  - q: "Why 24 months minimum?"
    a: "Monthly sales typically have annual seasonality. The model needs to see at least two full cycles to distinguish trend from season."
  - q: "Should I use external regressors (weather, ads spend)?"
    a: "Yes if they are known in advance for the forecast window. If you're forecasting March, you can use planned March ads spend; you cannot use March weather (you don't know it yet)."
  - q: "What's a good MAPE for sales?"
    a: "5–10% is excellent for established products; 15–25% is realistic for new products or volatile categories; > 30% means the signal is weak and the model is mostly noise."
updated: "2026-04-15"
relatedGlossary:
- predictive-analytics
- time-series
- data-drift
relatedCompare:
- datavision-pro-vs-power-bi
- datavision-pro-vs-looker-studio
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/glossary/predictive-analytics">predictive analytics</a> · <a href="/glossary/time-series">time series</a> · <a href="/glossary/data-drift">data drift</a>.</p>

## Prepare the time series

<p>Aggregate the sales table to one row per month per segment. Confirm there are no gaps; if a month is missing, fill with 0 explicitly so the model knows it was zero, not unknown.</p>

## Hold out the last 3 months

<p>In the <strong>Predictions</strong> tab, set the holdout to the most recent 3 months. The model sees only the first 21 months and predicts the held-out months — this is your honest accuracy test.</p>

## Try linear, then RandomForest

<p>Start with a linear trend model. If the holdout MAPE (mean absolute percentage error) is &gt; 15%, switch to RandomForest, which captures non-linear seasonality better. Pick the simpler model whenever the error gap is &lt; 2 percentage points.</p>

## Refit on all 24 months and forecast forward

<p>Once you've picked a model, refit it on all 24 months and forecast the next 3. Always report the forecast as a range (point estimate ± holdout MAPE), not a single confident number.</p>

## Re-check monthly for data drift

<p>Once a forecast is in production, run the same model next month and compare. If MAPE doubles, you have data drift — investigate before trusting the next forecast.</p>
