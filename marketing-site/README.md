# DataVision Pro — Marketing Site

A static, fully crawlable marketing site for DataVision Pro, built with [Astro](https://astro.build/). It lives **alongside** the Streamlit app (which stays as the product) and is what search engines and AI engines (ChatGPT, Perplexity, Google AI Overviews) actually see.

## Why a separate site

Streamlit renders content via WebSocket / JS after page load, so search engines see an empty shell. This site is server-rendered HTML with full content, JSON-LD, and Open Graph tags in the response — `curl` can see every word.

## Stack

- **Astro 4** — zero JS by default, ideal for SEO/GEO content.
- **Custom `/sitemap.xml`** endpoint at `src/pages/sitemap.xml.ts` — auto-includes all glossary, compare, and guide entries.
- Plain CSS, no Tailwind, no UI framework — keeps Lighthouse fast.

## Run locally

```bash
cd marketing-site
npm install   # only the first time
npm run dev   # http://0.0.0.0:8000
```

Or via Replit workflow: the **Marketing site** workflow runs `astro dev` on port 8000.

## Build for production

```bash
npm run build       # outputs ./dist
npm run preview     # serve dist on :8000
```

## Deploy

The build output (`marketing-site/dist`) is fully static and can be hosted on:

- Replit Static Deployment (recommended — separate from the Streamlit autoscale deployment)
- Cloudflare Pages, Netlify, Vercel, GitHub Pages — any static host

Set the env var `APP_URL` at build time to point the "Launch App" / "Sign In" buttons at the live Streamlit URL (defaults to `https://app.datavisionpro.app`):

```bash
APP_URL=https://your-streamlit-domain.replit.app npm run build
```

## Pages shipped

**Core**

- `/` — Home
- `/features`
- `/pricing`
- `/about`
- `/contact`

**Glossary** (`/glossary/`) — 8 in-depth term pages

- data-cleaning, outlier-detection, k-means-clustering, data-drift, etl-vs-elt,
  descriptive-statistics, predictive-analytics, missing-value-imputation

**Compare** (`/compare/`) — 3 head-to-head pages

- vs Tableau, vs Power BI, vs Excel

**Guides** (`/guides/`) — 3 how-to pages

- Clean a messy CSV in 60 seconds
- Detect outliers in sales data
- Build a 3-month sales forecast (no code)

## Content rules

These are non-negotiable and apply to every new page:

1. **Information gain.** Each page must contain at least one piece of insight or data not present in the current top-3 Google results for the target query.
2. **No fabrication.** No invented testimonials, ROI percentages, customer names, or competitor metrics. Where a number is needed and unavailable, leave a clearly-marked `[INSERT: …]` placeholder.
3. **Source every stat.** All cited statistics link to a primary source (research paper, government / .edu publication, or the vendor's own published materials).
4. **GEO structure.** First 40–60 words = direct answer. Then stats with citations, then how-it-works, then FAQ, then related links.
5. **No thin pages.** ~25 high-quality pages beats 200 thin ones.

## Editing content (no code required)

All marketing content lives as plain Markdown files with YAML frontmatter under `src/content/`. Non-developers can add or edit pages without touching any TypeScript or Astro code — just drop a new `.md` file in the right folder, fill in the frontmatter, and the site picks it up on the next build.

### Folder layout

```
src/content/
├── config.ts                # Schema (validates frontmatter on build — do not edit unless adding a field)
├── glossary/<slug>.md       # One file per glossary term  → /glossary/<slug>
├── compare/<slug>.md        # One file per competitor     → /compare/<slug>
└── guides/<slug>.md         # One file per how-to guide   → /guides/<slug>
```

The filename (minus `.md`) becomes the URL slug. The build will fail loudly if any required field is missing or has the wrong type, so typos can't ship silently.

### Adding a new glossary term

Create `src/content/glossary/my-new-term.md`:

```markdown
---
term: "My New Term"
question: "What is my new term?"
shortDef: "One-sentence definition that appears on cards."
description: "Meta description for search engines (~155 chars)."
answer: "40–60 word direct answer that opens the page."
stats:
  - value: "42%"
    label: "Why this number matters."
    source:
      label: "Source name"
      url: "https://example.com/source"
faq:
  - q: "First question?"
    a: "Direct answer."
related:
  - "data-cleaning"
  - "outlier-detection"
updated: "2026-04-21"
---

## How it works

Write the body in **Markdown**. Inline HTML (`<ol>`, `<table>`, etc.) also works.

## Why it matters

Each `## Heading` becomes a section on the page.
```

### Adding a new compare page

Create `src/content/compare/datavision-pro-vs-<competitor>.md`. All content for compare pages lives in the frontmatter (no markdown body needed):

```markdown
---
competitor: "Looker"
title: "DataVision Pro vs Looker"
description: "Honest, side-by-side comparison."
intro: "40–60 word direct answer."
bestFor:
  us: "Who DataVision Pro is best for."
  them: "Who Looker is best for."
rows:
  - feature: "Setup time"
    us: "Minutes"
    them: "Days"
whenToChoose:
  us:
    - "Bullet list of when DataVision Pro wins."
  them:
    - "Bullet list of when Looker wins."
faq:
  - q: "Question?"
    a: "Answer."
updated: "2026-04-21"
---
```

### Adding a new guide

Create `src/content/guides/how-to-do-something.md`. Each `## Heading` in the body becomes one ordered step in the page **and** in the `HowTo` JSON-LD schema for search engines, so the heading order is the step order:

```markdown
---
title: "How to do something useful"
description: "One-line meta description."
intro: "40–60 word direct answer."
estTime: "5 minutes"
difficulty: "Beginner"           # Beginner | Intermediate | Advanced
prerequisites:
  - "What you need before starting."
pitfalls:
  - "Common mistakes to avoid."
faq:
  - q: "Question?"
    a: "Answer."
updated: "2026-04-21"
---

## Step name one

What to do. Markdown plus inline HTML both work.

## Step name two

Next step.
```

### Editing an existing page

Open the `.md` file under `src/content/<collection>/<slug>.md`, edit the frontmatter or the body, and save. The dev server hot-reloads; production picks up the change on the next build.

### Validation

Frontmatter is validated against the Zod schema in `src/content/config.ts` at build time. If you forget a required field or use the wrong type, the build fails with a clear error pointing at the file and field — nothing broken can ship.

## Crawlability check

```bash
# After running `npm run preview` (or against the live site)
curl -s http://localhost:8000/glossary/data-cleaning | grep "What is data cleaning?"
curl -s http://localhost:8000/ | grep "DataVision Pro"
```

Both should print matching lines. If they don't, the page is not server-rendered and you've broken the contract.
