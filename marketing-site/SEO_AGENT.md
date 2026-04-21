# Weekly SEO / GEO Automation Agent — Operator Guide

This document explains the weekly background agent that keeps the marketing
site fresh for search engines and AI engines (ChatGPT, Perplexity, Google AI
Overviews). The agent is purely additive: it never touches the Streamlit
data/ML modules, and it never publishes a page without a human approving it
(unless you explicitly toggle auto-publish on).

## What it does, end to end

Every week (Mondays 08:00 UTC by default) the agent:

1. **Researches trends** from free sources — Reddit (`r/dataisbeautiful`,
   `r/datascience`, `r/analytics`, `r/dataengineering`), Hacker News
   (Algolia API), Stack Overflow (`pandas`, `data-cleaning`,
   `data-visualization` tags), and optionally Google Trends.
2. **Scores and de-duplicates** the topics, drops anything already covered on
   the site, and selects the top N candidates.
3. **Fetches the current top-3 SERP** for each candidate (via DuckDuckGo HTML)
   and writes an "information-gain brief" telling the generator what is
   missing.
4. **Generates a draft page** (glossary or how-to guide) using the existing
   OpenAI integration, following a strict GEO template — direct-answer block
   in 40-60 words, ≥1 cited statistic per major section, FAQ block, JSON-LD,
   1,200-2,000 words. Pages that fail validation are **dropped, not softened**.
5. **Refreshes stale pages** whose `updated:` marker is older than 90 days
   (configurable).
6. **Writes drafts to `marketing-site/_review/drafts/`** as JSON files, with
   matching rows in the `seo_agent_drafts` PostgreSQL table.
7. **Runs a GEO visibility check** against ~15 fixed prompts and records
   whether DataVision Pro is mentioned (with or without a citation).
8. **Emails a weekly summary** to the admin via the existing Resend
   integration and writes a full row to `seo_agent_runs` for cost / output
   audit.

## Approving drafts

1. Open the Streamlit admin panel → **SEO/GEO Agent** tab → **Review queue**.
2. For each draft, expand it to preview the JSON payload and the information-
   gain note.
3. Click **Approve** to inject the entry into the matching content file
   (`marketing-site/src/content/glossary.ts`, `guides.ts`, or `compare.ts`)
   and trigger the next sitemap regeneration on rebuild.
4. Click **Reject** to drop the draft. The JSON is moved to
   `marketing-site/_review/rejected/` for audit; nothing is published.

After approval, run the marketing-site build to regenerate static HTML:

```bash
cd marketing-site && npm run build
```

(Or set `SEO_AGENT_BUILD_CMD` and the agent will run it for you on approval.)

## Configuration

All knobs live in `seo_agent/agent_config.json`, editable from the admin
panel. Defaults:

| Knob | Default | Notes |
| --- | --- | --- |
| `schedule_cron` | `0 8 * * 1` | Mondays 08:00 UTC |
| `max_new_pages_per_week` | `5` | Hard cap |
| `max_refresh_pages_per_week` | `3` | Hard cap |
| `openai_model` | `gpt-4o` | Override with `SEO_AGENT_MODEL` |
| `weekly_budget_usd` | `7.0` | Soft cap; agent stops cleanly when hit |
| `auto_publish` | `false` | Keep `false` until you trust the output |
| `sources_enabled.reddit` | `true` |  |
| `sources_enabled.hackernews` | `true` |  |
| `sources_enabled.stackoverflow` | `true` |  |
| `sources_enabled.google_trends` | `false` | Requires `pip install pytrends` |
| `geo_prompts` | 15 prompts | Edit in admin panel |
| `refresh_after_days` | `90` |  |
| `report_email_to` | admin email |  |

## Scheduling

Configure a Replit **Scheduled Deployment** with:

- **Command:** `python scripts/run_seo_agent.py`
- **Schedule:** `0 8 * * 1` (or whatever you set in `schedule_cron`)

Manual runs:

```bash
# Print the resolved config
python scripts/run_seo_agent.py --print-config

# Full cycle, no drafts persisted, no email
python scripts/run_seo_agent.py --dry-run

# Real run (also accessible from the admin panel "Run now" button)
python scripts/run_seo_agent.py
```

## Pausing the agent

- Set `weekly_budget_usd` to `0` in the admin panel — the run will start, log
  `"budget cap hit"`, and exit cleanly with no drafts and no email cost.
- Or simply pause the Replit Scheduled Deployment.

## Cost guardrails

- The agent estimates spend live using gpt-4o pricing
  ($2.50/M input, $10/M output). When the running total crosses
  `weekly_budget_usd`, the remaining steps are skipped and the cap event is
  reported in the weekly email.
- Every run is recorded in the `seo_agent_runs` PostgreSQL table with token
  counts and dollar estimate, so you can audit a quarter at a time.

## Information-gain rule (do not relax this)

> Every generated page must contain at least one fact, statistic, or insight
> not present in the current top-3 results for its target query. If the
> generator cannot produce that, the page is **dropped — not softened, not
> published**. This is the line that separates real pSEO from the "scaled
> content abuse" Google penalises.

The generator returns the literal string `DROP_NO_INFORMATION_GAIN` when it
cannot meet the rule, and the runner records the drop with no further
attempt.

## Files at a glance

```
seo_agent/
├── __init__.py
├── config.py        # AgentConfig + agent_config.json
├── db.py            # AgentRun / AgentDraft / GeoCheckResult tables
├── sources.py       # Reddit, HN, Stack Overflow, (opt) Google Trends
├── selector.py      # de-dupe, score, filter against existing slugs
├── serp.py          # DuckDuckGo top-3 + information-gap brief
├── generator.py     # GEO-template page generation + validation
├── refresh.py       # find stale pages, refresh stats
├── review.py        # file-based review queue + content-file injection
├── geo_check.py     # brand-mention check across the prompt set
├── report.py        # weekly Resend email
└── runner.py        # orchestrator with cost cap

scripts/run_seo_agent.py   # CLI entry, used by the cron job
marketing-site/_review/
├── drafts/          # pending JSON drafts
├── approved/        # audit log of published drafts
└── rejected/        # audit log of rejected drafts
```
