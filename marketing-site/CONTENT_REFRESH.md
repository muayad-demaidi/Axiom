# Quarterly Content Refresh Checklist

The marketing site cites third-party stats and vendor pricing that go stale
within 6–12 months. To keep the site (and the AI engines that quote it)
trustworthy, we refresh every entry in `src/content/` once per quarter.

**Cadence:** Run this checklist on the first business week of every quarter
(Jan / Apr / Jul / Oct).

## Step 0 — Find what's stale

```bash
node marketing-site/scripts/check-content-freshness.mjs            # default: flag entries older than 6 months
node marketing-site/scripts/check-content-freshness.mjs --months=3 # tighter window
```

The script exits non-zero when any entry is older than the threshold, so it
can also run as a CI gate on the marketing-site build job.

## Step 1 — Comparison pages (`src/content/compare/*.md`)

For each entry, re-verify against the vendor's **live public pricing page**:

| Field | Source of truth |
|---|---|
| Tableau seat pricing (Creator / Explorer / Viewer / Tableau+) | https://www.tableau.com/pricing |
| Power BI Pro / PPU / Premium / Fabric F-SKUs | https://www.microsoft.com/power-platform/products/power-bi/pricing |
| Microsoft 365 Copilot price | https://www.microsoft.com/microsoft-365/business/copilot |
| Looker Studio Pro per-project price | https://cloud.google.com/looker-studio/pricing |
| Metabase Cloud (Starter / Pro / Enterprise) | https://www.metabase.com/pricing |

**Required actions per entry:**

- [ ] Re-quote any dollar amount in `rows[]` and `faq[]` against the live page.
- [ ] Resolve every `[verify]` / `[verify against current ... pricing]` marker
      with a concrete current figure. **No `[verify]` markers should remain
      after a quarterly pass** — the freshness script greps for them and
      fails the build if any survive.
- [ ] Bump `updated:` to today (`YYYY-MM-DD`).

## Step 2 — Glossary (`src/content/glossary/*.md`)

For each entry, re-verify the items in `stats[]`:

- [ ] Open every `source.url` and confirm it still resolves and still backs
      the `value` / `label` we cite.
- [ ] If the cited report has been superseded (e.g. "State of Data Science 2022"
      has a 2025 edition), update both the `value` and the `source`.
- [ ] Spot-check market-size and cost-of-X figures (Gartner, MarketsAndMarkets,
      Nilson, Crowe) — these are typically refreshed annually.
- [ ] Bump `updated:` on any entry whose `stats[]`, `faq[]`, or `sections[]`
      content changed.

## Step 3 — Guides (`src/content/guides/*.md`)

Guides are the most stable layer (they describe product workflows), so the
quarterly pass is lighter:

- [ ] Walk every `steps[].html` against the current product UI. Tab names,
      button labels, and substep names must still match.
- [ ] Re-confirm pricing/limit references in `prerequisites[]` (e.g.
      "60-day Tier 3 trial", "200 MB", "1,000,000 rows").
- [ ] Bump `updated:` on any entry whose copy changed.

## Step 4 — Build & ship

- [ ] `cd marketing-site && npm run build` — confirm no broken links or
      missing JSON-LD.
- [ ] Open the deployed Comparison and Glossary index pages and confirm the
      "Updated" dates render correctly.
- [ ] File any genuinely new third-party finds (e.g. a competitor announces a
      new tier mid-quarter) in the SEO agent's draft queue.

## Done looks like

- Zero `[verify]` markers anywhere under `src/content/`.
- `check-content-freshness.mjs` exits 0 with the default 6-month threshold.
- Every entry whose copy was touched this quarter has its `updated:` field
  bumped to a date inside the current quarter.
