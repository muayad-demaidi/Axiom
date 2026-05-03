# AXIOM - Intelligent Data Analytics Platform

## Overview
AXIOM is an intelligent data analytics system designed to simplify complex data analysis. It offers automated data cleaning, statistical analysis, interactive visualizations, AI-powered predictive analytics, and professional report generation. The platform includes an AI chat assistant for conversational interactions and aims to provide an accessible and powerful data analysis tool, enabling users to gain quick, professional insights without deep technical expertise. A sophisticated SEO/GEO automation agent and a dedicated marketing site drive organic discovery.

## User Preferences
- Language: Arabic (Levantine dialect) for communication
- No payment integration - all tiers freely accessible
- Professional, sophisticated design aesthetic
- Column types displayed in English

## System Architecture
The application uses a unified architecture with a **Next.js 14 (App Router + React + TS + Tailwind)** frontend and a **FastAPI** backend. **Pandas** and **NumPy** are used for data manipulation, **Recharts** for interactive visualizations, and **Scikit-learn** for machine learning models. **SQLAlchemy** with **PostgreSQL** manages data. **OpenAI GPT** powers AI analysis and conversational features. User authentication uses **JWT** and **bcrypt**.

### UI/UX Decisions
The design theme, "Data Noir," features a dark aesthetic with deep navy and AXIOM-blue accents. It uses Inter, JetBrains Mono, and SF Pro fonts. Key UI elements include a theme toggle, a custom `DataStreamBackground.tsx` component for the landing page, glassmorphism cards, and a subtle matrix rain background animation. The layout is desktop-first, with a maximum content width of 1320px. The workspace follows a chat-first pattern with a global left sidebar displaying new chat, recent chats, projects, files, and data connectors. Project workspaces have a slim inner rail for project-specific chats and datasets.

### Technical Implementations
- **Data Processing**: Includes toggleable data cleaning substeps, descriptive statistics, correlations, and distribution analysis.
- **Visualizations**: Supports various chart types like bar, scatter, box, pie, line charts, and heatmaps.
- **Predictive Analytics**: Implements linear models, trend analysis, categorical data analysis, ML prediction models (RandomForest/LinearRegression), and K-Means clustering. A guided predictive flow (Arabic-first / RTL) uses Prophet for time-series and sklearn for regression, generating Arabic clarifying questions and narratives.
- **User Management**: Features email/password authentication, registration, user profiles, and project management.
- **AI-Powered Chat**: A project-aware AI assistant using OpenAI GPT, supporting multi-conversation sessions. It incorporates a CRISP-DM playbook and specific methodologies per data type. It also includes a "Guided → Expert handoff" mechanism based on query complexity.
- **Conversational EDA workspace**: On dataset upload, the chat displays a dataset preview, automatic profile, insights ribbon, and suggestion chips. It uses NDJSON streaming with OpenAI tool-calling for `profile_dataset`, `make_chart`, `predict_column`, and `cluster_dataset`, persisting results as `chat_artifacts`. A "Final Report" side tab renders artifacts, an LLM-synthesized executive summary, and a PDF mini-preview.
- **Power BI–style aggregation engine**: A central engine (`backend/aggregation.py`) for measure aggregation across the product. It infers field metadata, handles user overrides, and provides functionality for data modeling, pivot tables, auto-generated dashboards with page-level slicers, cell explanations, and CSV export. The pivot page supports date-grain selectors, Top/Bottom-N, subtotals, cross-filtering, and export.
- **Canonical numeric parser**: One deterministic parser (`context/type_inference.py` — `parse_numeric_value`, `parse_numeric_series`, `to_numeric_canonical`) handles every BI surface (preview, group-by, charts, KPIs, chat, insights, transforms). Mixed-locale strings ("1,583", "1.234,56", "865,518"), parentheses negatives, currency symbols, and percent signs all parse deterministically; junk tokens (NaN/ERROR/blank) are excluded with a status code rather than silently coerced. SAP/ERP amount columns (DMBTR, WRBTR, etc.) classify as SUM measures even when stored as object dtype. Aggregation results carry a `calc_trace` block with parser diagnostics; a validation gate refuses implausible totals (>50× implied-per-row inflation over median magnitude, or zero rows parsed) with the message "Possible numeric parsing issue detected in <col>. Aggregation blocked until values are normalized." A new `GET /api/bi/{id}/reconciliation` endpoint returns raw vs parsed sample, totals, excluded rows, and duplicates. Per-column `parse_mode` overrides (auto / decimal_point / decimal_comma / thousands_comma / thousands_dot / mixed_smart) are accepted on the field-meta PATCH endpoint and persisted alongside other field overrides.
  - **Parser invariants** (do not break these):
    - In `auto`/`mixed_smart` mode the *rightmost* separator wins; a single `,` followed by exactly 3 digits is thousands ("1,583" → 1583), 1–2 digits is decimal ("1,5" → 1.5). The dot-only branch mirrors the same rule: "1.583" → 1583, "123.45" → 123.45, leading-zero head ("0.583") stays decimal.
    - Override modes (`decimal_point`/`decimal_comma`/`thousands_comma`/`thousands_dot`) bypass the heuristic — they always interpret `.` and `,` per the user's choice.
    - Every BI consumer must call the canonical parser; no `pd.to_numeric` in aggregation/pivot/KPI/chart/chat/insights paths. The single remaining `pd.to_numeric` call (`backend/bi.py` reconciliation `raw_sum`) is intentional and diagnostic-only — it shows what naive pre-parser code would have summed so the reconciliation view can display the diff.
  - **Totals drift on the `acdoca_dirty_1200_rows` fixture**: the original task spec quoted Excel totals of ~31M / 29M / 35M for SUM(DMBTR) by GJAHR. Those are mathematically impossible (1200 rows × $107–$9,977 caps the grand total at ~12M). The deterministic ground truth from canonical parsing is 2021=1,558,611.23, 2022=1,259,791.70, 2023=1,422,885.56 (grand total 4,241,288.49). `tests/test_numeric_parser_dmbtr.py` pins those values; the API-level parity test `test_bi_pivot_dmbtr_parity_kpi_pivot_canonical` re-asserts them at the HTTP boundary.
- **Data Connectors**: A `/app/connectors` catalog lists supported data sources (e.g., PostgreSQL, MongoDB, Snowflake, Google Sheets, CSV upload, REST).
- **Report Generation**: Server-side PDF reports using ReportLab, incorporating data tables, statistical summaries, distribution histograms (Matplotlib), and AI-generated insights.
- **SEO/GEO Automation**: A Python agent generates GEO-optimized pages and performs content refreshes based on trending topics.
- **Daily Pulse (Task #248)**: An in-process APScheduler `BackgroundScheduler` (`backend/scheduler.py`, wired via FastAPI `lifespan` in `backend/main.py`) runs once a day (UTC hour from `AXIOM_DAILY_PULSE_HOUR`, default 2) and persists a `daily_pulse_snapshots` row per *active* project (≥1 dataset, `last_opened_at` within 60 days, not archived). Each snapshot bundles `build_profile`, `predictions_engine.run_prediction`, `predictions.detect_anomalies_zscore` (z=3.0), per-metric deltas vs the previous snapshot, and a small recommendations list. Unique `(project_id, snapshot_date)` keeps reruns idempotent. `GET /api/projects/{project_id}/daily-pulse` returns `{generated_at, top_changes, anomalies, predictions, recommendations}` and falls back to a synchronous build when no snapshot exists yet. **Single-worker assumption**: the scheduler is in-process; with multiple uvicorn workers the unique constraint dedupes writes but the redundant work is wasted — switch to an external scheduler before scaling out.

## External Dependencies
- **PostgreSQL**: Relational database.
- **OpenAI GPT**: AI models.
- **Resend**: Transactional email service.
- **Google Fonts**: Typefaces.
- **Recharts**: Frontend charting library.
- **Pandas & NumPy**: Data manipulation.
- **Scikit-learn**: Machine learning.
- **SQLAlchemy**: ORM for database interaction.
- **bcrypt**: Password hashing.
- **ReportLab**: PDF generation.

## Testing
- The full backend test suite lives under `tests/` and is driven by `pytest`. New AXIOM-wide coverage modules (added in Task #219) are:
  - `tests/conftest.py` — shared fixtures (auth/register, project, dataset upload, chat session, sample CSVs, OpenAI stub) plus an `_db_isolation` autouse session fixture that records every test-created user ID and purges them (cascade) at session teardown.
  - `tests/test_units_semantic_model.py`, `test_units_predictions.py`, `test_units_data_modules.py` — pure-unit coverage for `backend/semantic_model.py`, `backend/predictions.py`, and the `data_*` modules.
  - `tests/test_api_endpoints.py` — request/response coverage for every FastAPI router, including all data-model variants (PATCH tables, POST relationships, PUT description, PATCH questions) and every chat tool dispatcher kind (`profile_dataset`, `make_chart`, `predict_column`, `cluster_dataset`, `query_model`, `list_model`, `explain_model`).
  - `tests/test_error_handling.py` — 400/401/404/422/500 JSON envelope guarantees. The 500-envelope test strictly requires both `error` and `detail` keys per the documented contract.
  - `tests/test_e2e_journey.py` — strict 10-step end-to-end journey (register → predict → chat → report) that asserts cross-table query produced rows, no refusals, artifacts persisted, and the report PDF is non-trivial in size.
  - `tests/test_frontend_components.py` — emits `MANUAL_REVIEW_REQUIRED` because no React test runner (Jest/Vitest/Playwright) is wired up in `frontend/package.json`.
- **Frontend Vitest suite** (`frontend/src/tests/`, jsdom env): 34 / 34 green across 8 component test files (last run 2026-05-02). MSW mocks `/api/auth/me` (GET + PATCH) plus `/api/users/me` aliases for the locale selector. `setup.ts` mocks `next-intl`, `next/navigation` (incl. `useParams` returning `{locale: "en"}`), `next/image`, `next/dynamic`, and shims `Element.prototype.scrollIntoView` + `window.matchMedia` for jsdom. Translation assertions resolve through `frontend/src/tests/utils/i18n.ts` (`t(locale, "settings.title")`) so tests fail loudly on missing keys rather than the silent `path` fallback that lives in `setup.ts`. **Do not** install a `globalThis.fetch` stub in `setup.ts` — MSW's interceptor wraps the runtime fetch when `server.listen()` runs and a stub silently bypasses every handler.

## Bug Fixes (2026-05-03)
- `backend/chat.py::_run_cross_predict` — was calling `cp._candidate_relationships` with the obsolete signature (no `target_id`, dict instead of `_FrameLoader`), throwing `TypeError: missing required positional argument 'loader'`. Fixed by switching to `cp._FrameLoader(records)` and passing `target_record.id` + `loader` to both `_candidate_relationships` and `_build_merged`. Regression covered by `tests/test_chat_cross_predict.py` (7 cases).
- `models.delete_project` — was missing cascade deletes for `UploadNotification`, `DailyPulseSnapshot`, and `Recommendation` (all NOT NULL FK → `projects.id`). Project deletion now wipes those three tables before the project row. Regression covered by `tests/test_delete_cascade.py`.

## Audits
- `docs/audits/world-class-audit.md` (Task #270) — 8-section initial pass with backlog (B-1 .. B-8). Items shipped this session: `frontend/public/manifest.webmanifest`, locale-layout `viewport` block (incl. `themeColor` light/dark), Settings language test, MSW handlers, i18n test helper, post-i18n Locust baseline (`tests/performance/baselines/post-i18n.md`), and ChatPanel greeting + follow-up chips extracted to `messages/{en,ar}.json` under the `chat` namespace (consumed via `useTranslations("chat")`).
- Run the whole suite with the consolidated runner: `python scripts/run_full_suite.py tests/`. It uses `pytest-json-report` to print totals, failures with file:line, a structured "Broken endpoints / components" list, and any `MANUAL_REVIEW_REQUIRED` markers.