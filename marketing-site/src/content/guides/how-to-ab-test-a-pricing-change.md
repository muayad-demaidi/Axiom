---
title: How to A/B test a pricing change
description: 'Step-by-step: design, size, and analyse an A/B test on a pricing change without statistical bait-and-switch. Includes power analysis, sample size, and how to read the result honestly.'
intro: 'To A/B test a pricing change: pre-declare the metric (revenue per visitor, not conversion rate alone), power-analyse the sample size you need, randomise at the user level, run for at least one full week without peeking, then load both arms into DataVision Pro and report the lift with a confidence interval — never just a p-value.'
estTime: 15 minutes setup + 1–4 weeks runtime
difficulty: Intermediate
prerequisites:
- An experimentation platform or simple split mechanism that can randomise at the user level.
- A baseline conversion / revenue-per-visitor figure from the last 4 weeks.
- An estimate of the smallest effect size you'd act on (e.g. +3% revenue per visitor).
pitfalls:
- Peeking at results and stopping early — doubles the false-positive rate.
- Reporting conversion rate alone on a pricing test (it almost always falls when prices rise).
- Running concurrent overlapping tests without orthogonal randomisation; you'll measure the combination, not each change.
- Ignoring sample-ratio mismatch — a broken split silently invalidates the result.
faq:
- q: Can I run a pricing test for just a weekend?
  a: Almost never. Weekend traffic is unrepresentative of weekday traffic, and short tests under-sample the population. Run for at least one full week, ideally two.
- q: Is a p-value of 0.04 enough to ship?
  a: It crosses convention but is weak evidence. Pair it with the confidence interval and the commercial significance of the effect before deciding.
- q: Should I segment the result by country / device?
  a: Pre-declare any segmentation you'll perform. Slicing the data after the fact (HARKing) inflates false positives. If you must explore, treat segment results as hypotheses for the next test.
- q: Does DataVision Pro run the experiment for me?
  a: No — it analyses the data after you've collected it. Pair it with your existing experimentation platform or a simple hashed split in your application code.
updated: '2026-04-21'
relatedGlossary:
- ab-testing
- descriptive-statistics
- predictive-analytics
relatedCompare:
- datavision-pro-vs-tableau
- datavision-pro-vs-looker-studio
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/glossary/ab-testing">A/B testing</a> · <a href="/glossary/descriptive-statistics">descriptive statistics</a> · <a href="/glossary/predictive-analytics">predictive analytics</a>.</p>

## Pick the right metric

<p>Conversion rate alone is a trap on a pricing test — a higher price almost always converts worse and yet often produces more revenue. Use <strong>revenue per visitor</strong> (RPV) as the primary metric, with conversion rate and AOV as guardrails.</p>

## Run a power analysis

<p>Use the rule of thumb <code>n ≈ 16 · σ² / δ²</code> per arm, where δ is the minimum detectable effect in the same units as the metric and σ is the standard deviation. For a typical e-commerce baseline, detecting a 3% RPV lift commonly needs tens of thousands of visitors per arm. If you cannot reach that, the test will be under-powered — fix the design before launching.</p>

## Randomise at the user level

<p>Bucket each visitor by a hashed user ID (or session ID for logged-out traffic) so the same person sees a consistent variant across visits. Verify the split lands at the expected ratio after 24 hours — a 50/50 design that drifts to 47/53 is a sample-ratio mismatch and the result is not trustworthy.</p>

## Run for at least one full business cycle, no peeking

<p>Run for a minimum of seven full days — and longer if your business has a monthly cycle (B2B, payroll, subscription renewals). Resist checking results daily and stopping when you "see significance"; naive peeking inflates the false-positive rate well above 5%.</p>

## Analyse in DataVision Pro

<p>Export both arms as a CSV with columns <code>variant, user_id, revenue, converted</code>. Upload to DataVision Pro, run the descriptive statistics tab to compare RPV by variant, and use the AI chat to compute the lift, the 95% confidence interval, and a sanity-check p-value. Report all three — never just one.</p>

## Make the call honestly

<p>Roll out only if the confidence interval excludes zero <em>and</em> the lower bound is large enough to be commercially meaningful. A statistically significant +0.4% lift on a metric you need 3% on is a "no go", not a "ship it".</p>
