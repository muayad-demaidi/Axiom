# AXIOM - Intelligent Data Analytics Platform

## Overview
AXIOM is a comprehensive, intelligent data analytics system, currently migrating from Streamlit to a unified Next.js and FastAPI application. Its core purpose is to simplify complex data analysis, offering capabilities such as automated data cleaning, statistical analysis, interactive visualizations, predictive analytics powered by AI, and professional report generation. The platform includes an AI chat assistant for conversational interactions and operates on a 60-day free trial model with email notifications and a support contact form. A sophisticated SEO/GEO automation agent and a dedicated marketing site drive organic discovery. The business vision is to provide an accessible yet powerful data analysis tool, enabling users to gain quick, professional insights without requiring deep technical expertise. The project aims for market potential by offering a robust solution for data-driven decision-making across various industries.

## User Preferences
- Language: Arabic (Levantine dialect) for communication
- No payment integration - all tiers freely accessible
- Professional, sophisticated design aesthetic
- Column types displayed in English

## System Architecture
The application is undergoing migration to a unified architecture consisting of a **Next.js 14 (App Router + React + TS + Tailwind)** frontend and a **FastAPI** backend. The system leverages **Pandas** and **NumPy** for data manipulation, **Recharts** for interactive visualizations (Plotly is retired), and **Scikit-learn** for machine learning models. **SQLAlchemy** with **PostgreSQL** manages user, project, dataset, chat session, and support message data. **OpenAI GPT** powers AI-driven analysis, recommendations, and conversational features. User authentication utilizes **JWT** and **bcrypt**.

### UI/UX Decisions
The design theme, "Data Noir," features a dark aesthetic with deep navy and AXIOM-blue accents (`#60A5FA` / `#3b82f6` / `#2563eb`). The UI uses Inter for body text, JetBrains Mono for code, and SF Pro as a fallback. A theme toggle persists user preference, and a custom `DataStreamBackground.tsx` component provides an animated Matrix-style background on the landing page. Glassmorphism cards and a subtle matrix rain background animation contribute to a professional user experience. The layout is desktop-first, with a maximum content width of 1320px. After login, the workspace follows a Julius.ai-style chat-first pattern: `/app` is a centered "What do you want to analyze today?" landing with a single rounded chat input (Attach data + Connectors + circular send), and a global left sidebar (`ProductSidebar.tsx`) shows **+ New chat**, recent **Chats** across all projects, recent **Projects**, and a **Workspace** group with Files and Data Connectors. Submitting from the landing calls `POST /api/chats/quick` to find-or-create a "Quick Chats" project + new session and redirects to `/app/project/{pid}?session={sid}&q={text}`, where `ChatPanel`'s `initialPrompt` auto-sends once. The projects index moved to `/app/projects`; project workspaces keep a slim inner rail for that project's own chats and datasets.

### Technical Implementations
- **Data Processing**: Features include an ordered list of toggleable data cleaning substeps (e.g., duplicate removal, missing value handling), descriptive statistics, correlations, and distribution analysis.
- **Visualizations**: Supports various chart types, including bar, scatter, box, pie, line charts, heatmaps, with custom SVG for box plots and CSS grid for heatmaps.
- **Predictive Analytics**: Implements linear models, trend analysis, categorical data analysis, ML prediction models (RandomForest/LinearRegression), and K-Means risk clustering.
- **User Management**: Includes email/password authentication, registration, detailed user profiles, and a 60-day free trial. Project management is central to the user workflow.
- **AI-Powered Chat**: A project-aware AI assistant leveraging OpenAI GPT, supporting multi-conversation sessions and a Julius.ai-style landing chat. The system prompt embeds a CRISP-DM playbook (Understand → Identify → Plan → Result → Caveats), common-data-challenge guidance, and per-data-type methodology (sales/RFM, surveys/sentiment, e-commerce/funnel, telemetry/anomaly, sports/regression). Sessions are persisted under a per-project `chat_sessions` table; new chats auto-title from the first user message; ownership is enforced on every endpoint (verified cross-user 404s). New endpoints `GET /api/chats/recent` (cross-project recency) and `POST /api/chats/quick` (auto-create Quick Chats project + session) power the landing flow.
- **Data Connectors**: A `/app/connectors` catalog presents data sources supported through Replit (PostgreSQL, MySQL, MongoDB, Snowflake, BigQuery, Databricks, Google Sheets, Airtable, Notion, Stripe, HubSpot, Salesforce, Linear, GitHub, Slack, Google Analytics, CSV upload, REST), grouped by category, each opening a modal that explains how to wire it up.
- **Report Generation**: PDF reports are generated server-side using ReportLab, incorporating cover pages, data tables, statistical summaries, distribution histograms (Matplotlib), and AI-generated insights.
- **SEO/GEO Automation**: A Python agent generates GEO-optimized pages, refreshes content, and performs brand-mention checks using trending topics from external sources.
- **Deployment**: Configured for `autoscale` on Replit, building the Next.js frontend and running FastAPI with uvicorn.

## External Dependencies
- **PostgreSQL**: Relational database.
- **OpenAI GPT**: AI models for various intelligent features.
- **Resend**: Transactional email service.
- **Google Fonts**: For Inter, DM Sans, and JetBrains Mono typefaces.
- **Recharts**: Frontend charting library.
- **Pandas & NumPy**: Data manipulation.
- **Scikit-learn**: Machine learning.
- **SQLAlchemy**: ORM for database interaction.
- **bcrypt**: Password hashing.
- **ReportLab**: PDF generation.