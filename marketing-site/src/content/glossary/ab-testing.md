---
term: A/B Testing
question: What is A/B testing?
shortDef: A controlled experiment that randomly splits users between two versions and measures which produces a better outcome on a chosen metric.
description: A/B testing randomly splits users between two variants and measures which produces a better outcome. Learn power analysis, sample-size calculation, p-values, and the pitfalls that invalidate most tests.
answer: A/B testing is a controlled experiment that randomly assigns users to one of two variants (control A, treatment B) and measures which produces a better outcome on a pre-declared metric. Done right it provides causal evidence; done wrong — peeking, multiple comparisons, under-powering — it produces confident-looking conclusions that do not replicate.
stats:
- value: 10–20%
  label: Typical share of A/B tests at mature experimentation programs that show a statistically significant lift — most ideas don't beat control.
  source:
    label: Kohavi, Tang & Xu — Trustworthy Online Controlled Experiments (2020)
    url: https://experimentguide.com
- value: n ≈ 16 · σ² / δ²
  label: Per-arm sample-size approximation for detecting effect δ with 80% power at α = 0.05 — the formula every PM should memorise.
  source:
    label: Lehr's rule of thumb, NIST/SEMATECH e-Handbook of Statistical Methods
    url: https://www.itl.nist.gov/div898/handbook/
faq:
- q: What sample size do I need?
  a: It depends on baseline rate, minimum detectable effect, and desired power. For a 5% baseline conversion and a 1-percentage-point lift at 80% power, you need roughly 30,000 users per arm.
- q: Is p < 0.05 enough?
  a: It's the convention, not the truth. Pair it with a confidence interval, a pre-registered hypothesis, and a sanity check that the lift is large enough to matter commercially.
- q: Can I stop early if I see a winner?
  a: Only with a sequential test design (e.g. group-sequential or always-valid p-values). Naive early stopping doubles your false-positive rate.
- q: Is A/B testing the same as multivariate testing?
  a: No. A/B compares two versions; multivariate tests several factors simultaneously to find the best combination — and needs much larger samples.
- q: Can I A/B test in AXIOM?
  a: AXIOM analyses the results of an A/B test you've already run — load both arms, compute lift, confidence interval, and statistical significance side-by-side using the time-period comparison view.
related:
- descriptive-statistics
- predictive-analytics
- data-drift
- outlier-detection
updated: '2026-04-21'
relatedGuides:
- how-to-ab-test-a-pricing-change
- how-to-compare-this-quarter-vs-last-quarter
relatedCompare:
- axiom.ai-vs-tableau
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/guides/how-to-ab-test-a-pricing-change">how to A/B test a pricing change</a> · <a href="/guides/how-to-compare-this-quarter-vs-last-quarter">how to compare this quarter vs last quarter</a> · <a href="/compare/axiom.ai-vs-tableau">AXIOM vs Tableau</a>.</p>

## How to run a trustworthy test

<ol>
          <li><strong>Pre-register</strong> the hypothesis, primary metric, and minimum detectable effect.</li>
          <li><strong>Power-analyse</strong> to compute the sample size you need before launching.</li>
          <li><strong>Randomise</strong> at the right unit (user, session, or device — never request).</li>
          <li><strong>Don't peek</strong> — checking results daily and stopping when you "see significance" inflates the false-positive rate well above 5%.</li>
          <li><strong>Run for full business cycles</strong> — at least one full week to capture weekday vs weekend behaviour.</li>
          <li><strong>Report effect size with a confidence interval</strong>, not just a p-value.</li>
        </ol>

## What invalidates most tests

<ul>
          <li><strong>Sample-ratio mismatch</strong> — if your 50/50 split lands at 48/52, the randomisation is broken and the result is suspect.</li>
          <li><strong>Novelty and primacy effects</strong> — short tests on UX changes capture reaction, not long-run behaviour.</li>
          <li><strong>Multiple comparisons</strong> — testing 10 metrics at α = 0.05 yields one false positive on average per test.</li>
          <li><strong>Interaction with concurrent tests</strong> — overlapping experiments need orthogonal randomisation or you measure their combination.</li>
        </ul>
