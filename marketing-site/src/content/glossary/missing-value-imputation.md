---
term: "Missing Value Imputation"
question: "What is missing value imputation?"
shortDef: "Filling in missing data with estimated values so downstream analysis and models can run without dropping rows."
description: "Missing value imputation replaces gaps in a dataset with estimated values. Learn mean/median imputation, KNN, MICE, and when to use which."
answer: "Missing value imputation is the process of filling gaps in a dataset with estimated values so analysis and machine-learning models can use the row instead of dropping it. The right method depends on whether the data is missing completely at random (MCAR), at random (MAR), or not at random (MNAR)."
stats:
  - value: "Listwise deletion"
    label: "can discard up to 60% of rows in real-world surveys, severely biasing results — the original problem imputation was invented to solve."
    source:
      label: "Schafer & Graham, Missing Data: Our View of the State of the Art (2002)"
      url: "https://psycnet.apa.org/doi/10.1037/1082-989X.7.2.147"
  - value: "MICE (m=5)"
    label: "Multiple Imputation by Chained Equations with 5 imputations is the academic gold standard recommended by the FDA for clinical trials."
    source:
      label: "FDA — Guidance on Missing Data in Clinical Trials"
      url: "https://www.fda.gov/regulatory-information/search-fda-guidance-documents"
faq:
  - q: "When is dropping rows OK?"
    a: "When missingness is under ~5% and there's no plausible reason it correlates with the target. Otherwise impute."
  - q: "Is mean imputation bad?"
    a: "It's not bad, it's blunt. It shrinks variance and weakens correlations. Fine for a quick first pass; weak for production models."
  - q: "What is MNAR and why does it matter?"
    a: "Missing Not At Random — the missingness itself depends on the unknown value (e.g., high earners refuse to disclose income). No imputation method fully solves MNAR; you need extra information or a sensitivity analysis."
  - q: "Should I impute the target column?"
    a: "No. Drop rows where the target is missing for training. Imputing the target invents the answer and leaks."
  - q: "Does DataVision Pro impute automatically?"
    a: "Yes — its auto-cleaning includes mean/median/mode imputation as a toggleable substep, and you can insert custom rules (Replace Values, Drop Column) above or below it."
related:
  - "data-cleaning"
  - "outlier-detection"
  - "descriptive-statistics"
  - "predictive-analytics"
updated: "2026-04-15"
relatedGuides:
- how-to-clean-a-messy-csv-in-60-seconds
relatedCompare:
- datavision-pro-vs-excel
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/guides/how-to-clean-a-messy-csv-in-60-seconds">how to clean a messy CSV in 60 seconds</a> · <a href="/compare/datavision-pro-vs-excel">DataVision Pro vs Excel</a>.</p>

## Method ladder (cheap → rigorous)

<ol>
          <li><strong>Drop</strong> — only safe if missingness is &lt;5% and MCAR.</li>
          <li><strong>Constant fill</strong> — 0 / "Unknown" — fast, leaks no info, but biases distributions.</li>
          <li><strong>Mean / median / mode</strong> — preserves central tendency, shrinks variance.</li>
          <li><strong>KNN imputation</strong> — fills based on similar rows; good when features correlate.</li>
          <li><strong>MICE / iterative imputer</strong> — models each missing column from the others; statistically sound.</li>
          <li><strong>Domain rule</strong> — sometimes "missing = no" is the most accurate possible imputation.</li>
        </ol>

## Always add a missingness flag

<p>Whatever you impute, also create a binary <code>was_missing</code> column. Models can learn that "the customer didn't fill in their phone number" is itself predictive — a signal you destroy by silent imputation.</p>
