# AXIOM - Intelligent Data Analytics Platform

## Active Migration: Streamlit + Astro → Next.js + FastAPI (Task #131, in progress)
The unified app is being scaffolded under `frontend/` (Next.js 14 App Router + React + TS + Tailwind) and `backend/` (FastAPI). The existing Streamlit app and Astro marketing site **remain in the repo as the parity reference and are not deleted** until each surface is verified at parity.

**Current workflow layout** (see `.replit`):
- `Start application` → Next.js dev server on port 5000 (primary preview, webview).
- `Backend API` → FastAPI/uvicorn on port 8000 (console). Frontend proxies `/api/*` to it via `next.config.mjs` rewrites.
- `Streamlit (legacy)` → `streamlit run app.py` on port 5173 (console, not auto-started). Start it via the workflow tool when verifying parity against the legacy app.
- The previous `Marketing site` (Astro static) workflow has been removed; its content has been migrated to Next.js routes (see below). Source still lives at `marketing-site/` for diff/parity until cutover.

**Migration status**:
- ✅ Marketing surfaces — `/`, `/features`, `/pricing`, `/about`, `/contact`, `/glossary` (12 entries), `/guides` (5 entries), `/compare` (5 entries) all rendering as SSG with `revalidate = 3600` (ISR), generating canonical metadata, Organization / SoftwareApplication / FAQPage / Article / DefinedTerm / BreadcrumbList JSON-LD, and a sitemap matching legacy priorities (1.0/0.9/0.9/0.6/0.5/0.8/0.7/0.8 + per-slug 0.7).
- ✅ Content collections migrated as Markdown under `frontend/content/{glossary,guides,compare}/` parsed with gray-matter + remark + Zod schemas (`frontend/src/lib/content.ts`).
- ✅ SEO infrastructure — `app/sitemap.ts`, `app/robots.ts`, per-page `generateMetadata`, JSON-LD injection helper, breadcrumbs.
- ✅ Product shell skeleton — `/app` workspace, sidebar grouped `DATA · ANALYSIS · INSIGHT`, pages for upload / clean / transform / statistics / visualize / predict / model / chat / report. Streaming chat panel hits `/api/chat/stream` (SSE-style chunked text) and is dataset-aware (pulls active project + dataset from local storage).
- ✅ FastAPI backend wired in `backend/`: `auth_routes.py` (JWT + bcrypt via `models.create_user`/`authenticate_user`), `projects.py` (list/create/update/delete), `datasets.py` (upload + list, persists Parquet bytes via `models.save_dataset_record`), `analysis.py` (clean → `data_cleaner.clean_data`, statistics → `data_analyzer.generate_summary_report`, predict → `predictions.simple_forecast`, model → sklearn KMeans / RandomForest, transform → small Power Query–style step set, visualize → server-aggregated chart points), `chat.py` (real OpenAI streaming reusing `ai_assistant.SYSTEM_PROMPT` + `detect_language`, persists turns via `models.save_chat_message`). All routes verified via curl: register → token → /me → projects round-trip succeeds.
- ✅ JSON-safe responses: every analysis/dataset endpoint return is wrapped through `backend/_json.py::jsonify()` which recursively coerces `numpy.int64`, `numpy.float64`, `numpy.bool_`, `pandas.Timestamp`, NaN/Inf → JSON-safe primitives. This fixed a class of 500s ("'numpy.int64' object is not iterable") that broke `/api/datasets/upload`, `/api/statistics`, etc., once a real dataset hit them.
- ✅ OpenAI API key plumbing: chat streaming reads `AI_INTEGRATIONS_OPENAI_API_KEY` (Replit-managed) with `OPENAI_API_KEY` fallback, and honors `AI_INTEGRATIONS_OPENAI_BASE_URL` when set. `ai_assistant.py` already used the same env vars; previously `backend/chat.py` was reading only `OPENAI_API_KEY` and silently degrading to "chat is offline".
- ✅ Frontend auth surface — `/login`, `/signup` post to `/api/auth/{login,register}`, store JWT in `localStorage` (`axiom_token`), redirect to `/app`. `frontend/src/lib/api.ts` adds the bearer header to every request and exposes `streamPost` for SSE-style chunks. `frontend/src/lib/projectContext.ts` tracks active project/dataset/mode in local storage.
- ✅ Real product pages — `/app` lists projects with mode picker (Guided → `/app/chat`, Expert → `/app/upload`); `/app/upload` posts CSV/Excel and shows live row × col counts; `/app/statistics`, `/app/clean`, `/app/transform`, `/app/predict`, `/app/model` all hit the wired endpoints against the active dataset and render JSON results.
- ✅ **Deployment configured** — `.replit` deployment switched to `autoscale`. Build runs `cd frontend && npm install --include=dev && npm run build`; production run starts uvicorn on 127.0.0.1:8000 in the background and serves Next.js on `$PORT` with `BACKEND_URL=http://127.0.0.1:8000` so `/api/*` rewrites still resolve. The user must click Publish from the main repl after this branch merges.
- ✅ PDF report generation: `POST /api/report/pdf` (in `backend/main.py`) builds a parametric reportlab PDF — cover, columns table, numeric describe, distribution histogram (matplotlib Agg), and AI insights via `ai_assistant.generate_data_insights`. All user-controlled strings (title, notes, dataset name) are passed through `_escape_for_pdf` before reaching `Paragraph` so `<`/`&`/`>` cannot break the markup parser. Frontend `/app/report` posts JSON, downloads the PDF blob.
- ✅ Contact form: `POST /api/support/contact` (`backend/support.py`) persists via `models.save_support_message` and best-effort relays to Resend through `email_service.send_support_notification`. Pydantic `field_validator` strips inputs **before** length checks so whitespace-only payloads return 422 instead of being persisted as empty rows. The Resend HTML/subject now `html.escape`s the user-supplied name/email/message to block markup injection into the support inbox. Frontend `/contact` ships a real form (`frontend/src/components/ContactForm.tsx`) with client-side guard + server-error surfacing.
- ⚠️ Still pending parity follow-ups: Recharts visualizations on `/app/visualize`, broader Power Query transform palette beyond the six ops currently exposed, and full removal of `marketing-site/` + `app.py` once a side-by-side parity QA confirms equivalence.

**Visual system** (replaces "Data Noir" for the unified app):
- Light: surface `#FFFFFF`, alt `#F9FAFB`, accent `#2563eb`.
- Dark (Midnight Blue): surface `#050B1F` (deep navy), alt `#0A1432`, border `#1A2750`, text `#E6ECFF`, accent `#60A5FA`. Defined under `.dark { ... }` in `frontend/src/app/globals.css`.
- Theme toggle lives in the header (`frontend/src/components/ThemeToggle.tsx`) — sun/moon button that flips `.dark` on `<html>` and persists to `localStorage('axiom-theme')`. A tiny inline boot script in `app/layout.tsx` reads localStorage + `prefers-color-scheme` and applies the class **before** hydration to avoid FOUC. `<html suppressHydrationWarning>` covers the legitimate server/client class delta.
- Animated landing background: `frontend/src/components/DataStreamBackground.tsx` is a `<canvas>` that renders Matrix-style falling monospace glyphs in brand blue (`--stream-strong` / `--stream-soft` CSS vars). Soft radial vignette over the canvas keeps the headline crisp. Hidden under `prefers-reduced-motion`.
- Type: Inter (body/UI), JetBrains Mono (code/eyebrow + data stream), SF Pro fallback. Loaded via Google Fonts in `app/layout.tsx`.
- Charts use Recharts (Plotly retired). Box plot is a custom SVG, heatmap is a CSS grid (Recharts has no built-in for either).

## Overview
AXIOM (formerly DataVision Pro) is a comprehensive, intelligent data analytics system. The legacy interface is built with Streamlit and is being migrated to a unified Next.js + FastAPI app. It aims to simplify complex data processes, providing valuable insights and predictive capabilities to users. The platform focuses on automatic data cleaning, statistical analysis, interactive visualizations, time period comparisons, and AI-powered predictive analytics. It includes an AI chat assistant, generates professional reports with recommendations, and operates on a 60-day free trial system with email notifications and a support contact form. The project also includes a sophisticated SEO/GEO automation agent and a separate marketing site to drive organic discovery. The business vision is to provide an accessible yet powerful data analysis tool, catering to users who need quick, professional insights without deep technical expertise.

### Brand
- **Current name**: AXIOM (rebranded from DataVision Pro)
- **Logo**: Blue hexagonal network/dome design at `static/logo.png` (1408×768) and `marketing-site/public/logo.png`. Old DataVision Pro logos preserved as `logo_datavision_backup.png` in both locations.
- **Domain**: still `datavisionpro.app` (not renamed) — internal links and SEO slugs (`/compare/datavision-pro-vs-*`) intentionally preserved to avoid breaking external SEO equity. Only user-visible UI strings, page titles, alt text, copyright, email templates, AI system prompt, and marketing-site content were renamed to AXIOM.
- **Accent palette**: shifted from teal (#2dd4bf / #14b8a6 / #0d9488) to the AXIOM-blue family (#60a5fa / #3b82f6 / #2563eb / #1d4ed8) so the surrounding UI matches the actual logo color. The CSS custom properties keep their legacy `--teal*` names for compatibility but resolve to blue values at runtime — when adding new accents, prefer `var(--teal)`/`var(--teal-mid)`/`var(--teal-dark)` over hardcoded hexes so future palette changes stay one-edit jobs. The deep-navy background and "Data Noir" mood are unchanged.

## User Preferences
- Language: Arabic (Levantine dialect) for communication
- No payment integration - all tiers freely accessible
- Professional, sophisticated design aesthetic
- Column types displayed in English

## System Architecture
The application is primarily built with **Streamlit** for its interactive web interface. Data processing and analysis leverage **Pandas** and **NumPy**. Visualizations are created using **Plotly**, with supplementary charts from **Seaborn** and **Matplotlib**. Predictive models are built with **Scikit-learn**.

The system uses **SQLAlchemy** for ORM and **PostgreSQL** as its relational database to manage users, subscriptions, datasets, and support messages. **OpenAI GPT** powers the AI for analysis, recommendations, and conversational interactions. User authentication is handled with **bcrypt** for secure password hashing.

### UI/UX Decisions
The design theme is "Data Noir," characterized by a dark precision aesthetic with deep navy and teal accents. It utilizes "Syne" for headings and "DM Sans" for body text, with "JetBrains Mono" for monospaced elements. The layout is desktop-first, with a maximum content width of 1320px. Visual elements include glassmorphism cards and a subtle matrix rain background animation. The user dashboard features a sidebar navigation, and the overall design emphasizes a professional and sophisticated user experience. Projects are managed through a dedicated page with a workspace strip, live search, and per-project monogram tiles. Inside an open project, the dashboard chrome is intentionally minimal — a tight breadcrumb topbar (`← Projects` ghost pill / project name / active sheet name) replaces the previous greeting hero, and the sidebar groups its nine sections into three mono-labeled clusters (DATA · ANALYSIS · INSIGHT) with 2-digit index prefixes and a subtle teal left-rail on the active row.

### Technical Implementations
- **Data Cleaning**: Features an ordered list of toggleable and customizable substeps (e.g., remove duplicates, handle missing values, outlier detection). A proactive question bar helps identify and suggest fixes for common data issues.
- **Statistical Analysis**: Provides descriptive statistics, correlations, and distribution analysis.
- **Visualizations**: Supports various chart types including bar, scatter, box, pie, line charts, and heatmaps.
- **Time Tracking**: Enables saving and comparing data across different time periods.
- **Predictions**: Implements linear models and trend analysis.
- **ML & Clustering Analytics**: An advanced section offering categorical data analysis, ML prediction models (RandomForest/LinearRegression), K-Means risk clustering, and enhanced outlier detection.
- **User System**: Includes email/password authentication, registration with detailed user profiles, and a 60-day free trial providing full Tier 3 access. Users can manage projects and datasets, with a project-centric workflow post-login.
- **Admin Panel**: Provides tools for user management, dataset analytics, conversation history, and platform usage metrics.
- **SEO/GEO Automation Agent**: A scheduled Python agent (`seo_agent/`) that pulls trending topics, drafts GEO-optimized pages using OpenAI, refreshes old content, and performs brand-mention checks. Drafts require human approval via an admin panel. It includes cost guardrails and an information-gain rule to ensure quality. A build queue system handles the deployment of approved marketing site content.
- **Marketing Site**: A separate Astro-based static site (`marketing-site/`) for SEO/GEO purposes, designed for organic discovery.

## External Dependencies
- **Streamlit**: Main web framework.
- **Pandas & NumPy**: Data manipulation and numerical operations.
- **Plotly, Seaborn & Matplotlib**: Interactive and static data visualization libraries.
- **Scikit-learn**: Machine learning library for predictive models.
- **SQLAlchemy**: Python SQL toolkit and Object Relational Mapper.
- **PostgreSQL**: Relational database management system.
- **OpenAI GPT**: AI models for natural language processing, analysis, and content generation.
- **bcrypt**: Password hashing library.
- **Resend**: Transactional email service for welcome emails and support notifications.
- **Reddit, Hacker News, Stack Overflow, Google Trends**: Sources for trending topics for the SEO agent.
- **Plausible API and Google Search Console**: Used by the SEO agent for organic traffic feedback.