---
title: How to compare this quarter vs last quarter (without lying with averages)
description: A practical guide to a defensible quarter-over-quarter comparison — same-day windows, mix-shift checks, and confidence intervals — using AXIOM's time-period view.
intro: 'To compare this quarter vs last quarter honestly: align both windows to the same number of business days, hold the customer mix constant where possible, report median alongside mean (revenue distributions are skewed), check for a mix shift that explains the headline change, and surface the result with a confidence interval — not a single percent number that hides the variance.'
estTime: 10 minutes
difficulty: Intermediate
prerequisites:
- A transaction or order-line dataset with a date column and at least one revenue/quantity column.
- Knowledge of any obvious external events in either window (a launch, a holiday calendar shift, a pricing change).
pitfalls:
- Comparing calendar quarters of different length without normalising — a 92-day quarter beats an 89-day quarter on volume alone.
- Reporting only the mean when the distribution is right-skewed (most revenue data is) — the median tells the typical-customer story.
- Ignoring a mix shift — a country, channel, or segment composition change can fully explain the headline number with no underlying performance change.
- Cherry-picking the comparison window after seeing the data; pre-declare it.
faq:
- q: Should I compare quarter-over-quarter or year-over-year?
  a: Both, when possible. QoQ catches recent momentum; YoY controls for seasonality. Reporting only one is a half-answer.
- q: What if the two windows have very different sizes?
  a: Normalise by days, customers, or sessions before comparing. Report the per-unit metric, not the totals.
- q: Is a confidence interval really needed for QoQ?
  a: Yes — without it, leadership cannot tell a real swing from random variation, and you'll spend the next quarter explaining noise as strategy.
- q: Does AXIOM detect mix shifts automatically?
  a: Yes — the time-period comparison surfaces grouped share-of-total alongside the headline metric so a composition change is visible at a glance.
updated: '2026-04-21'
relatedGlossary:
- descriptive-statistics
- data-drift
- ab-testing
relatedCompare:
- datavision-pro-vs-tableau
- datavision-pro-vs-power-bi
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/glossary/descriptive-statistics">descriptive statistics</a> · <a href="/glossary/data-drift">data drift</a> · <a href="/glossary/ab-testing">A/B testing</a>.</p>

## Align the windows

<p>Compare like with like: same number of business days, same days of week. Q1 has fewer days than Q4; February is short; Easter and Lunar New Year shift between months. In AXIOM, set both windows to the same length (e.g. trailing 90 days) rather than calendar quarters when the calendars don't match.</p>

## Profile both windows separately

<p>Open the <strong>Statistics</strong> tab on each window and compare the 5-number summary side-by-side. A higher mean with an unchanged median tells you the tail moved, not the typical customer — that is a mix shift, not growth.</p>

## Check the mix

<p>Group by the dimensions that matter (country, channel, segment, product line) and compare the share of revenue per group. If the country mix shifted from 70/30 to 50/50, the headline change is partly composition, not performance. AXIOM's tabular comparison view shows both shares side-by-side for a one-glance check.</p>

## Compute the lift with a confidence interval

<p>Use the AI chat or the descriptive statistics view to compute mean RPC (revenue per customer) and a 95% confidence interval for the difference. A "+8% QoQ" headline with a CI of [-1%, +17%] is too noisy to act on; the same lift with a CI of [+5%, +11%] is a real signal.</p>

## Cross-check with a holdout-style sanity test

<p>Pick a stable segment that should not have changed (e.g. existing customers in your largest country with no pricing change) and run the same comparison. If that segment also shows a big swing, suspect a data issue (missing days, late-arriving orders) rather than business performance.</p>

## Write the summary in three lines

<p>Report (1) the headline change with its confidence interval, (2) what mix change explains how much of it, and (3) which segments drove the residual real change. Three lines is enough — anything longer is hiding the answer.</p>
