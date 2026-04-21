---
term: Time Series Analysis
question: What is time series analysis?
shortDef: Statistical methods for analysing data points indexed in time order to find trend, seasonality, and forecast future values.
description: Time series analysis finds trend, seasonality, and autocorrelation in data ordered by time, then uses them to forecast. Learn decomposition, ARIMA, Prophet, and the holdout discipline that keeps forecasts honest.
answer: Time series analysis is the study of data points collected sequentially over time — sales by day, temperature by hour, page views by minute. It decomposes the series into trend, seasonality, and residual components, models the dependency between consecutive observations, and uses the result to forecast future values with an explicit error band.
stats:
- value: 2 full cycles
  label: Minimum history required for a model to learn seasonality reliably — e.g. 24 months of monthly data for annual seasonality.
  source:
    label: 'Hyndman & Athanasopoulos, Forecasting: Principles and Practice (3rd ed.)'
    url: https://otexts.com/fpp3/
- value: MAPE 5–10%
  label: Industry benchmark for an excellent monthly demand forecast on established products; new products typically land at 15–25%.
  source:
    label: Institute of Business Forecasting & Planning — Forecast Accuracy Benchmarks
    url: https://ibf.org/knowledge/journal-of-business-forecasting/
faq:
- q: Is time series the same as regression?
  a: No — regression assumes independent observations. Time series observations are correlated with their own past, which requires different validation and model families.
- q: Do I need to make the series stationary?
  a: ARIMA-family models need stationarity (differencing usually achieves it). Prophet and tree-based models do not.
- q: How do I handle missing dates?
  a: Fill explicit zeros for periods where the count was genuinely zero, and impute or interpolate periods where the data was simply not collected. The two are very different.
- q: Can I forecast a single number?
  a: You can, but you shouldn't. Always report a range — point estimate ± holdout error — so consumers know how much uncertainty to budget for.
- q: What about external regressors like marketing spend?
  a: Useful only if their future values are known at forecast time. Planned spend works; reactive spend that depends on sales does not.
related:
- predictive-analytics
- data-drift
- descriptive-statistics
- data-cleaning
updated: '2026-04-21'
---

## The classic decomposition

<p>Every time series can be split into three pieces:</p>
        <ul>
          <li><strong>Trend</strong> — the long-run direction (growing, shrinking, flat).</li>
          <li><strong>Seasonality</strong> — repeating patterns at a fixed period (weekly, monthly, annual).</li>
          <li><strong>Residual</strong> — what's left after removing trend and seasonality; ideally pure noise.</li>
        </ul>
        <p>Looking at the decomposition before modelling tells you whether to use additive (constant seasonality) or multiplicative (seasonality grows with the level) models.</p>

## Common model families

<ul>
          <li><strong>Naive / seasonal naive</strong> — the baseline every other model must beat.</li>
          <li><strong>Exponential smoothing (ETS)</strong> — fast, robust, great for short series with seasonality.</li>
          <li><strong>ARIMA / SARIMA</strong> — captures autocorrelation; needs a stationary series.</li>
          <li><strong>Prophet</strong> — Meta's open-source library; tolerates missing data and holiday effects.</li>
          <li><strong>Tree-based regressors with lag features</strong> — Random Forest / XGBoost on lagged columns; the modern default for tabular forecasting.</li>
        </ul>

## The non-negotiable: time-aware holdouts

<p>Never shuffle a time series before splitting. Train on the past, test on the future. DataVision Pro's predictions tab enforces this by holding out the most recent N periods and reporting MAPE on that window — the only honest accuracy estimate for forecasting.</p>
