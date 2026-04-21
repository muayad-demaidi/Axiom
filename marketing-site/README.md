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

## Adding a new glossary / compare / guide page

Edit the matching file under `src/content/`:

- `src/content/glossary.ts`
- `src/content/compare.ts`
- `src/content/guides.ts`

Add a new entry to the array. The corresponding `[slug].astro` page renders it automatically and the sitemap picks it up on the next build.

## Crawlability check

```bash
# After running `npm run preview` (or against the live site)
curl -s http://localhost:8000/glossary/data-cleaning | grep "What is data cleaning?"
curl -s http://localhost:8000/ | grep "DataVision Pro"
```

Both should print matching lines. If they don't, the page is not server-rendered and you've broken the contract.
