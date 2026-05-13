---
term: "Data Cleaning"
question: "What is data cleaning?"
shortDef: "The process of detecting and correcting errors, inconsistencies, missing values, and duplicates in a dataset before analysis."
description: "Data cleaning is the process of fixing or removing incorrect, corrupted, duplicate, or incomplete records so analysis produces trustworthy results. Learn the steps, costs, and tools."
answer: "Data cleaning is the process of identifying and fixing errors, missing values, duplicates, and inconsistencies in a dataset so that downstream analysis, reporting, and machine-learning models produce trustworthy results. It typically includes removing duplicates, standardising formats, handling outliers, imputing missing values, and validating data types."
stats:
  - value: "Up to 80%"
    label: "of a data scientist's time is spent preparing and cleaning data, leaving only ~20% for analysis."
    source:
      label: "Anaconda State of Data Science 2022"
      url: "https://www.anaconda.com/state-of-data-science-2022"
  - value: "$12.9M / year"
    label: "Gartner's estimate of the average annual cost of poor data quality to a single organisation."
    source:
      label: "Gartner — How to Improve Your Data Quality"
      url: "https://www.gartner.com/smarterwithgartner/how-to-improve-your-data-quality"
faq:
  - q: "Is data cleaning the same as data wrangling?"
    a: "No. Cleaning is a subset of wrangling. Wrangling also includes reshaping, joining, and feature engineering. Cleaning specifically targets errors, duplicates, and missing values."
  - q: "Should I clean before or after exploratory analysis?"
    a: "Both. A first pass before EDA fixes obvious errors; a second pass after EDA addresses issues you only see once you start visualising."
  - q: "How much data should I throw away?"
    a: "As little as possible. Prefer imputation, flagging, or quarantine columns over deletion, because deleted rows can introduce sampling bias."
  - q: "Can data cleaning be automated?"
    a: "The mechanical parts (trim, dedupe, type cast, IQR outliers) absolutely. Domain-specific decisions (is a $0 sale a refund or an error?) still need a human."
  - q: "What is a 'cleaning recipe'?"
    a: "A saved, ordered list of cleaning substeps that can be re-applied to a new file with the same schema, ensuring reproducible results month over month."
related:
  - "missing-value-imputation"
  - "outlier-detection"
  - "etl-vs-elt"
  - "descriptive-statistics"
updated: "2026-04-15"
relatedGuides:
- how-to-clean-a-messy-csv-in-60-seconds
relatedCompare:
- axiom.ai-vs-excel
---

<p class="see-also" style="margin:.5rem 0 1.25rem; font-size:.95rem; color:var(--muted,#6b7280);"><strong>See also:</strong> <a href="/guides/how-to-clean-a-messy-csv-in-60-seconds">how to clean a messy CSV in 60 seconds</a> · <a href="/compare/axiom.ai-vs-excel">AXIOM vs Excel</a>.</p>

## How data cleaning works

<p>A practical cleaning pipeline runs in roughly this order:</p>
        <ol>
          <li><strong>Profile</strong> — count rows, columns, missing cells, and duplicates per column.</li>
          <li><strong>Standardise types</strong> — coerce strings that look like dates or currency into the correct type.</li>
          <li><strong>Trim and normalise text</strong> — strip whitespace, fix casing, and collapse encodings.</li>
          <li><strong>Handle missing values</strong> — drop, fill with a constant, or impute using mean/median/mode.</li>
          <li><strong>Detect outliers</strong> — IQR or z-score for numeric columns.</li>
          <li><strong>Deduplicate</strong> — exact and fuzzy match on key columns.</li>
          <li><strong>Validate</strong> — re-profile and confirm all assumptions hold.</li>
        </ol>

## Why it matters for analysts

<p>Garbage in, garbage out is not a cliché — it is a budget item. Analysts who skip cleaning end up debugging KPIs in board meetings instead of trusting them. A repeatable cleaning step keeps every chart, model, and AI summary anchored to the same source of truth.</p>
        <p>In <strong>AXIOM</strong>, the cleaning pipeline runs as an ordered list of toggleable substeps you can reorder (↑/↓) and extend (Trim Whitespace, Drop Column, Rename Column), so the same recipe can be replayed on next month's file in one click.</p>
