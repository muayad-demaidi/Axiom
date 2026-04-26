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
- **Data Connectors**: A `/app/connectors` catalog lists supported data sources (e.g., PostgreSQL, MongoDB, Snowflake, Google Sheets, CSV upload, REST).
- **Report Generation**: Server-side PDF reports using ReportLab, incorporating data tables, statistical summaries, distribution histograms (Matplotlib), and AI-generated insights.
- **SEO/GEO Automation**: A Python agent generates GEO-optimized pages and performs content refreshes based on trending topics.

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
- Run the whole suite with the consolidated runner: `python scripts/run_full_suite.py tests/`. It uses `pytest-json-report` to print totals, failures with file:line, a structured "Broken endpoints / components" list, and any `MANUAL_REVIEW_REQUIRED` markers.