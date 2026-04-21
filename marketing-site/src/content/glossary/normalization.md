---
term: Normalization
question: What is data normalization?
shortDef: Rescaling numeric features onto a common scale (typically 0–1 or mean 0 / std 1) so they contribute comparably to a model.
description: Data normalization rescales numeric columns so features measured in different units contribute comparably to a model. Learn min-max, z-score, and robust scaling — and when to use each.
answer: Normalization is the process of rescaling numeric features so they share a common range or distribution — typically 0–1 (min-max), mean 0 / std 1 (z-score), or median 0 / IQR 1 (robust scaling). It is required for any model that uses Euclidean distance or gradient descent, including K-Means, KNN, SVMs, and neural networks.
stats:
- value: 10×–100×
  label: Typical convergence speedup for gradient-descent training when input features are normalized to comparable scales.
  source:
    label: LeCun et al., Efficient BackProp (1998)
    url: http://yann.lecun.com/exdb/publis/pdf/lecun-98b.pdf
- value: Z-score = (x − μ) / σ
  label: Standardisation formula — produces a feature with mean 0 and standard deviation 1, the default for scikit-learn's StandardScaler.
  source:
    label: scikit-learn — Preprocessing data
    url: https://scikit-learn.org/stable/modules/preprocessing.html
faq:
- q: Should I normalize the target variable?
  a: For regression, optionally yes — it can stabilise loss values. Always invert the transform before reporting predictions in business units.
- q: Min-max or z-score by default?
  a: Z-score for tabular ML; min-max for image pixels and any input that already has a meaningful bounded range.
- q: Do I refit the scaler on new data?
  a: No. Fit once on training data, then apply the saved scaler to all new data. Refitting leaks information across splits.
- q: What about categorical features?
  a: Don't normalize them. One-hot encode or target-encode first; numeric scaling applies only to true numeric columns.
- q: Does normalization fix skewed distributions?
  a: No — it only rescales. To reduce skew, log-transform or Box-Cox first, then normalize the result.
related:
- k-means-clustering
- data-cleaning
- predictive-analytics
- descriptive-statistics
updated: '2026-04-21'
---

## The three common scalers

<ul>
          <li><strong>Min-max</strong> — maps to [0, 1]. Sensitive to outliers; great for image pixels and bounded inputs.</li>
          <li><strong>Z-score (standardisation)</strong> — mean 0, std 1. The safe default for most tabular ML.</li>
          <li><strong>Robust scaler</strong> — uses median and IQR instead of mean and std. Best when the column has outliers you cannot remove.</li>
        </ul>

## Normalization vs standardisation

<p>Strictly, "normalization" means rescaling to a fixed range (usually 0–1) and "standardisation" means rescaling to mean 0 / std 1. In practice the words are used interchangeably — what matters is that you fit the scaler on training data only and apply it (without refitting) to validation, test, and production data.</p>

## When you do not need it

<p>Tree-based models — Random Forest, XGBoost, LightGBM — are scale-invariant and do not benefit from normalization. Skipping it for trees keeps feature interpretability intact. DataVision Pro applies z-score scaling automatically before K-Means clustering and skips it for tree models.</p>
