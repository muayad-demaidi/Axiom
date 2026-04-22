# DataVision Pro - Intelligent Data Analytics Platform

## Overview
DataVision Pro is a comprehensive, intelligent data analytics system built with Streamlit, designed to offer one-click automated data analysis. It aims to simplify complex data processes, providing valuable insights and predictive capabilities to users. The platform focuses on automatic data cleaning, statistical analysis, interactive visualizations, time period comparisons, and AI-powered predictive analytics. It includes an AI chat assistant, generates professional reports with recommendations, and operates on a 60-day free trial system with email notifications and a support contact form. The project also includes a sophisticated SEO/GEO automation agent and a separate marketing site to drive organic discovery. The business vision is to provide an accessible yet powerful data analysis tool, catering to users who need quick, professional insights without deep technical expertise.

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