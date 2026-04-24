# AXIOM (DataVision Pro) — Complete Setup & Restore Guide

This archive contains everything required to rebuild the AXIOM project from
scratch on any machine (local, server, or a fresh Replit). Follow the steps
below in order.

> **Project name**: Currently branded as "DataVision Pro" in code. Rebrand to
> "AXIOM" is in progress. Either name refers to the same project.

---

## 1. Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Python | **3.11+** | Main app, AI helpers, SEO agent |
| Node.js | **20+** | Marketing site (Astro) |
| PostgreSQL | **14+** (16 recommended) | Users, projects, datasets, conversations |
| `pip`, `npm` | latest | Package managers |
| (Optional) `git` | latest | Restore commit history |

System libraries (Linux/macOS — install via your package manager):
`cairo`, `freetype`, `libxcrypt`, `libyaml`, `pkg-config`, `qhull`, `tcl`, `tk`
(needed by matplotlib, reportlab, and PDF generation).

On Replit: these are already in `.replit` under `[nix].packages` — no action needed.

---

## 2. Restore the Code

### 2a. From this ZIP
```bash
unzip axiom_project_complete.zip -d axiom
cd axiom
```

### 2b. (Optional) Restore git history
The `.git/` folder is included. To make it your working repo:
```bash
git status        # should show a clean tree
git log --oneline # see full commit history
```

---

## 3. Install Dependencies

### 3a. Python
```bash
python3.11 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
```

> If you use `pyproject.toml` directly: `pip install -e .` instead.

### 3b. Marketing site (Astro)
```bash
cd marketing-site
npm ci
cd ..
```

---

## 4. Set Up the Database

### 4a. Create a fresh database
```bash
createdb axiom                         # local Postgres
# or use a hosted provider (Neon, Supabase, Render, Replit)
```

### 4b. Apply the schema
```bash
psql "$DATABASE_URL" -f database_schema.sql
```

Alternatively, the app will auto-create missing tables on first start via
SQLAlchemy `init_db()` in `models.py`.

### 4c. (Optional) Restore data
This export does **NOT** include user data. To migrate data from the old
database, run `pg_dump` on the source and `pg_restore` on the target.

---

## 5. Configure Environment Variables

Copy the template:
```bash
cp .env.example .env
```

Edit `.env` and fill in **at minimum**:
- `DATABASE_URL` — your PostgreSQL connection string
- `AI_INTEGRATIONS_OPENAI_API_KEY` — your OpenAI key
- `RESEND_API_KEY` — your Resend email key

Optional vars (only if you run the SEO agent) are documented in `.env.example`.

> On Replit, set these via **Secrets** in the side panel — do not commit `.env`.

---

## 6. Run the App

### 6a. Streamlit data app (port 5000)
```bash
streamlit run app.py --server.port 5000
```
Open `http://localhost:5000`.

### 6b. Marketing site (port 8000)
```bash
cd marketing-site
ASTRO_TELEMETRY_DISABLED=1 npm run build
npx serve dist -l tcp://0.0.0.0:8000 --no-clipboard
```
Open `http://localhost:8000`.

### 6c. (Optional) SEO agent
```bash
python -m seo_agent.main
```

### 6d. Run both apps in parallel (Replit-style)
On Replit, the two workflows in `.replit` start automatically. Locally,
open two terminals — one for each command above.

---

## 7. First-Run Checks

1. Visit `http://localhost:5000` → you should see the AXIOM landing page.
2. Click **Sign Up**, create an account → you get a 60-day Tier-3 trial.
3. Go to **Projects** → create a project → upload a small CSV.
4. Open the dashboard → you should see all 9 sections in the sidebar.
5. Visit `http://localhost:8000` → marketing site renders 30 static pages.

---

## 8. Project Architecture (quick map)

| File / Folder | Purpose |
|---|---|
| `app.py` | Streamlit UI (~13,700 lines) — all 9 dashboard sections, projects page, login, admin |
| `models.py` | SQLAlchemy models — Users, Projects, Datasets, Sheets, Conversations, etc. |
| `ai_assistant.py` | OpenAI helpers — chat, insights, comparison, prediction, cleaning report |
| `data_cleaner.py` | Pandas-based cleaning pipeline (deduplication, missing values, outliers, etc.) |
| `data_analyzer.py`, `predictions.py`, `data_modelling.py` | Statistics + ML helpers |
| `proactive_questions.py` | Detects data issues and suggests fixes |
| `knowledge_base.py` | Per-project knowledge base + learned notes |
| `email_service.py` | Resend transactional emails |
| `seo_agent/` | Scheduled SEO/GEO automation agent |
| `marketing-site/` | Astro static marketing site (30 pages) |
| `static/` | Streamlit-served static assets (logos, images) |
| `tests/` | Test suite |
| `.streamlit/config.toml` | Streamlit server config |
| `.replit` | Replit workflow + Nix package manifest |
| `replit.md` | Project memory / agent instructions |
| `CLAUDE.md` | Detailed Arabic project guide |

---

## 9. Common Issues & Fixes

**"ImportError: cannot import name X from models"**  
You're on an older app.py against a newer models.py (or vice versa).  
Run `git status` to make sure everything is in sync.

**Database connection refused**  
Confirm `DATABASE_URL` is set and Postgres is running:  
```bash
psql "$DATABASE_URL" -c "SELECT 1;"
```

**"No module named 'streamlit'"**  
You forgot to `source .venv/bin/activate` before `pip install`.

**Marketing site build fails on `serve`**  
Use `npx --yes serve dist -l tcp://0.0.0.0:8000 --no-clipboard` so npx
auto-confirms install.

**Matplotlib / reportlab / cairo errors**  
You're missing system libraries — see Prerequisites section.

---

## 10. Deployment

This project deploys as a **Replit Autoscale Deployment**:
- Build: `cd marketing-site && npm install && npm run build`
- Public dir: `marketing-site/dist`
- Runtime: Streamlit on port 5000 (auto-routed to port 80)

To deploy elsewhere (Render, Fly, Railway):
1. Provide all env vars from `.env.example`
2. Provision a PostgreSQL instance and apply `database_schema.sql`
3. Run both processes (Streamlit + Astro preview) — typically as two services
4. Reverse-proxy the marketing site at `/` and Streamlit at a subdomain

---

## 11. What's NOT in This Archive

- `node_modules/` — restored by `npm ci`
- `.pythonlibs/` / `.venv/` — restored by `pip install -r requirements.txt`
- `.env` (your real secrets) — fill in `.env.example` instead
- User data / database rows — only the schema is included
- `__pycache__/` and `.cache/` — auto-generated at runtime

---

## 12. Need Help?

- All Arabic project guidance: `CLAUDE.md`
- Project memory & decisions: `replit.md`
- SEO agent docs: `marketing-site/SEO_AGENT.md`

---

_Generated automatically as part of the project export._
