---
term: "K-Means Clustering"
question: "What is K-Means clustering?"
shortDef: "An unsupervised algorithm that groups observations into K clusters by minimising within-cluster variance."
description: "K-Means clustering partitions a dataset into K groups based on feature similarity. Learn how it works, how to pick K, and where it breaks down."
answer: "K-Means clustering is an unsupervised learning algorithm that partitions a dataset into K non-overlapping groups by iteratively assigning each point to the nearest cluster centroid and then recomputing centroids until they stabilise. It is fast, simple, and works best on numerical features that form roughly spherical clusters of similar size."
stats:
  - value: "1957"
    label: "Year Stuart Lloyd developed the original K-Means algorithm at Bell Labs — it remains the most widely-taught clustering method today."
    source:
      label: "Lloyd, Least squares quantization in PCM (Bell Labs, 1957)"
      url: "https://en.wikipedia.org/wiki/K-means_clustering#History"
  - value: "O(n · k · i · d)"
    label: "Time complexity per Lloyd iteration — roughly linear in data size, which is why it scales to millions of rows where hierarchical clustering cannot."
    source:
      label: "Scikit-learn — K-Means complexity"
      url: "https://scikit-learn.org/stable/modules/clustering.html#k-means"
faq:
  - q: "Does K-Means need scaled features?"
    a: "Yes. Because it uses Euclidean distance, a column in dollars will dominate a column in fractions. Standardise (z-score) or min-max scale before fitting."
  - q: "Is K-Means deterministic?"
    a: "No — initial centroids are random. Set a fixed random_state or use multiple restarts (n_init in scikit-learn) to get reproducible clusters."
  - q: "Can K-Means handle categorical data?"
    a: "Not natively. One-hot encode and scale, or use k-modes / k-prototypes for mixed types."
  - q: "How many points do I need?"
    a: "Rule of thumb: at least 30 points per cluster, ideally hundreds. Below that, cluster centroids are noisy."
  - q: "What's the difference between K-Means and KNN?"
    a: "K-Means is unsupervised clustering. KNN is supervised classification. They share the letter K and not much else."
related:
  - "outlier-detection"
  - "predictive-analytics"
  - "descriptive-statistics"
  - "data-drift"
updated: "2026-04-15"
---

## How it works (Lloyd's algorithm)

<ol>
          <li>Pick K initial centroids (random or k-means++).</li>
          <li>Assign every point to its nearest centroid.</li>
          <li>Recompute each centroid as the mean of its assigned points.</li>
          <li>Repeat 2–3 until assignments stop changing or a max-iteration cap is hit.</li>
        </ol>

## How to pick K

<ul>
          <li><strong>Elbow method</strong> — plot inertia vs K and pick the elbow.</li>
          <li><strong>Silhouette score</strong> — pick K that maximises average silhouette (-1 to 1).</li>
          <li><strong>Domain knowledge</strong> — sometimes "high / medium / low risk" forces K = 3 regardless of statistics.</li>
        </ul>

## Where K-Means breaks

<p>K-Means struggles with non-spherical clusters, very different cluster sizes, and mixed numeric/categorical data. For those cases prefer DBSCAN, Gaussian Mixture Models, or k-prototypes. DataVision Pro uses K-Means specifically for risk clustering, where 3–5 spherical groups (low/medium/high) match the business question.</p>
