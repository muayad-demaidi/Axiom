import streamlit as st
import pandas as pd
import numpy as np
import hashlib
from datetime import datetime
import io
import base64
import csv as _csv

from context.type_inference import (
    infer_schema, apply_schema, schema_to_dataframe, cast_column, ColumnType
)
from context.step_history import (
    StepHistory, Step,
    serialize_source_df, deserialize_source_df,
    rebuild_history_from_recipes,
)


def _column_config_from_schema(schema_iter, df=None):
    """Build a Streamlit column_config dict that pretty-prints inferred types.

    Currency/decimal columns get thousand separators and 2dp; date columns get
    a DD-MMM-YYYY display; percentages render as percent. The mapping is driven
    off whatever schema is captured at the active step, so manual overrides
    automatically flow through to the preview formatting.
    """
    cfg = {}
    if not schema_iter:
        return cfg
    cols_in_df = set(df.columns) if df is not None else None
    for s in schema_iter:
        if isinstance(s, dict):
            col = s.get("column")
            t = (s.get("inferred_type") or "").lower()
        else:
            col = getattr(s, "column", None)
            t = (getattr(s, "inferred_type", "") or "").lower()
        if not col:
            continue
        if cols_in_df is not None and col not in cols_in_df:
            continue
        try:
            if t == "integer":
                cfg[col] = st.column_config.NumberColumn(format="localized")
            elif t == "decimal":
                cfg[col] = st.column_config.NumberColumn(format="localized")
            elif t == "currency":
                cfg[col] = st.column_config.NumberColumn(format="accounting")
            elif t == "percentage":
                cfg[col] = st.column_config.NumberColumn(format="percent")
            elif t == "date":
                cfg[col] = st.column_config.DateColumn(format="DD-MMM-YYYY")
            elif t == "datetime":
                cfg[col] = st.column_config.DatetimeColumn(format="DD-MMM-YYYY HH:mm")
        except Exception:
            # Older Streamlit versions may not support every preset; skip silently.
            pass
    return cfg

from models import (
    init_db, get_db, save_dataset_record, find_similar_datasets, 
    get_datasets_by_name, save_chat_message, get_chat_history,
    create_user, authenticate_user, get_user_by_id, get_all_users,
    get_all_datasets, get_admin_stats, increment_analysis_count, User,
    update_user_subscription, save_support_message, check_trial_active,
    issue_session_token, get_user_by_session_token, clear_session_token,
    update_dataset_steps, get_dataset_record, set_user_last_dataset,
    get_user_datasets,
)
from data_cleaner import (
    clean_data, detect_column_types, get_data_quality_score,
    CLEANING_SUBSTEPS, SUBSTEP_FUNCS,
)
from data_analyzer import (
    get_basic_stats, get_numeric_stats, get_categorical_stats, 
    get_correlation_matrix, find_strong_correlations, detect_outliers, 
    generate_summary_report
)
from visualizations import (
    create_histogram, create_bar_chart, create_box_plot, 
    create_scatter_plot, create_correlation_heatmap, create_line_chart,
    create_pie_chart, create_missing_values_chart,
    create_distribution_overview, create_comparison_chart, create_trend_chart,
    create_categorical_distribution, create_categorical_bar_chart,
    create_cluster_scatter, create_feature_importance_chart, create_outlier_visualization
)
from predictions import (
    compare_datasets, simple_forecast, analyze_trend, 
    predict_column, calculate_growth_metrics, build_ml_prediction_model,
    create_risk_clusters, analyze_categorical_insights
)
from ai_assistant import (
    generate_data_insights, chat_about_data, 
    generate_comparison_insights, generate_prediction_insights
)
import math
from email_service import send_welcome_email, send_support_notification

def get_logo_base64():
    """Load logo as base64 for HTML embedding"""
    try:
        with open("static/logo.png", "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return ""

def sanitize_for_json(obj):
    """Recursively replace NaN and Inf values with None for JSON serialization"""
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    return obj

st.set_page_config(
    page_title="DataVision Pro - Intelligent Data Analytics",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="collapsed"
)

NEON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --teal:         #2dd4bf;
    --teal-mid:     #14b8a6;
    --teal-dark:    #0d9488;
    --indigo:       #818cf8;
    --bg:           #07101f;
    --surface:      #0c1829;
    --surface-2:    #111f35;
    --text-primary: #f0f4f8;
    --text-secondary: #94a3b8;
    --text-muted:   #475569;
    --border:       rgba(45,212,191,0.14);
    --border-hover: rgba(45,212,191,0.38);
    --shadow-teal:  0 0 32px rgba(13,148,136,0.18);
    /* legacy aliases kept for dashboard compatibility */
    --matrix-teal: #0d9488;
    --matrix-teal-dark: #0f766e;
    --matrix-teal-light: #14b8a6;
    --emerald-muted: #059669;
    --soft-silver: #94a3b8;
    --deep-slate: #0f172a;
    --obsidian: #020617;
    --glass-bg: rgba(15, 23, 42, 0.7);
    --glass-border: rgba(20, 184, 166, 0.15);
}

* { font-family: 'DM Sans', sans-serif; }

/* ── Desktop-first layout override ───────────────────────────────────────── */
.block-container,
[data-testid="stMainBlockContainer"] {
    max-width: 1320px !important;
    padding: 1rem 3rem 3rem 3rem !important;
    margin: 0 auto !important;
}
@media (max-width: 1100px) {
    .block-container, [data-testid="stMainBlockContainer"] {
        padding: 1rem 1.5rem 3rem 1.5rem !important;
    }
}

.stApp {
    background: radial-gradient(ellipse 120% 80% at 50% -20%, #0d2240 0%, #07101f 55%, #020b18 100%);
}

.matrix-bg {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
    background: transparent;
}

.matrix-column {
    position: absolute;
    top: -100%;
    font-family: 'JetBrains Mono', monospace;
    font-size: 14px;
    line-height: 1.2;
    color: rgba(13, 148, 136, 0.25);
    text-shadow: 0 0 8px rgba(13, 148, 136, 0.3);
    animation: matrix-fall linear infinite;
    white-space: pre;
    writing-mode: vertical-rl;
    text-orientation: upright;
}

.matrix-column span {
    display: block;
    opacity: 0.4;
}

.matrix-column span:first-child {
    color: rgba(20, 184, 166, 0.5);
    text-shadow: 0 0 12px rgba(20, 184, 166, 0.4);
    opacity: 0.6;
}

@keyframes matrix-fall {
    0% {
        transform: translateY(-100%);
        opacity: 0;
    }
    5% {
        opacity: 1;
    }
    95% {
        opacity: 1;
    }
    100% {
        transform: translateY(250vh);
        opacity: 0;
    }
}

.glow-text {
    font-size: 2.75rem;
    font-weight: 800;
    text-align: center;
    font-family: 'Syne', sans-serif;
    background: linear-gradient(135deg, #2dd4bf, #14b8a6, #94a3b8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem;
    letter-spacing: -0.04em;
}

.sub-title {
    font-size: 1.1rem;
    text-align: center;
    color: #94a3b8;
    margin-bottom: 2.5rem;
    font-weight: 400;
}

.neon-card {
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(20, 184, 166, 0.15);
    border-radius: 20px;
    padding: 1.75rem;
    margin: 1rem 0;
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.neon-card:hover {
    border-color: rgba(20, 184, 166, 0.35);
    box-shadow: 0 16px 48px rgba(0, 0, 0, 0.5);
    transform: translateY(-4px);
}

.metric-card {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(20, 184, 166, 0.12);
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
    box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    transition: all 0.3s ease;
}

.metric-card:hover {
    border-color: rgba(20, 184, 166, 0.3);
    transform: translateY(-2px);
}

.metric-value {
    font-size: 2.5rem;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.metric-label {
    font-size: 0.875rem;
    color: #94a3b8;
    margin-top: 0.5rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

.pricing-card {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(20, 184, 166, 0.15);
    border-radius: 24px;
    padding: 2.5rem;
    text-align: center;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}

.pricing-card.premium {
    border-color: rgba(20, 184, 166, 0.4);
    box-shadow: 0 0 40px rgba(13, 148, 136, 0.15);
}

.pricing-card.premium::before {
    content: 'MOST POPULAR';
    position: absolute;
    top: 20px;
    right: -40px;
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    color: #ffffff;
    padding: 8px 50px;
    font-size: 0.7rem;
    font-weight: 700;
    transform: rotate(45deg);
    letter-spacing: 0.1em;
}

.pricing-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #e2e8f0;
    margin-bottom: 0.5rem;
}

.pricing-price {
    font-size: 3rem;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.pricing-period {
    color: #94a3b8;
    font-size: 0.875rem;
    font-weight: 500;
}

.feature-list {
    text-align: left;
    margin: 2rem 0;
}

.feature-item {
    padding: 0.75rem 0;
    color: #94a3b8;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    font-size: 0.95rem;
}

.feature-item.included {
    color: #14b8a6;
}

.neon-button {
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    color: #ffffff;
    border: none;
    padding: 14px 36px;
    border-radius: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 20px rgba(13, 148, 136, 0.25);
}

.neon-button:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 28px rgba(13, 148, 136, 0.35);
}

.auth-container {
    max-width: 420px;
    margin: 2rem auto;
    background: rgba(15, 23, 42, 0.85);
    border: 1px solid rgba(20, 184, 166, 0.2);
    border-radius: 24px;
    padding: 2.5rem;
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    box-shadow: 0 24px 64px rgba(0, 0, 0, 0.5);
}

.sidebar-header {
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 1.4rem;
    font-weight: 700;
    text-align: center;
    margin-bottom: 1.5rem;
    letter-spacing: -0.01em;
}

.user-badge {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(20, 184, 166, 0.15);
    border-radius: 16px;
    padding: 1.25rem;
    text-align: center;
    margin-bottom: 1.5rem;
    backdrop-filter: blur(12px);
}

.badge-free {
    background: rgba(100, 116, 139, 0.3);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.75rem;
    color: #94a3b8;
    font-weight: 600;
    letter-spacing: 0.05em;
}

.badge-premium {
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 0.75rem;
    color: #ffffff;
    font-weight: 600;
    letter-spacing: 0.05em;
}

.admin-stat-card {
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(20, 184, 166, 0.12);
    border-radius: 20px;
    padding: 2rem;
    text-align: center;
    backdrop-filter: blur(12px);
    transition: all 0.3s ease;
}

.admin-stat-card:hover {
    border-color: rgba(20, 184, 166, 0.3);
}

.admin-stat-icon {
    font-size: 3rem;
    margin-bottom: 0.75rem;
}

.admin-stat-value {
    font-size: 2.5rem;
    font-weight: 700;
    color: #14b8a6;
    font-family: 'JetBrains Mono', monospace;
}

.admin-stat-label {
    color: #94a3b8;
    font-size: 0.875rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 0.5rem;
}

.insight-box {
    background: rgba(13, 148, 136, 0.08);
    border-left: 4px solid #14b8a6;
    padding: 1.25rem;
    margin: 1rem 0;
    border-radius: 0 12px 12px 0;
}

.warning-box {
    background: linear-gradient(145deg, rgba(239, 68, 68, 0.08), rgba(239, 68, 68, 0.04));
    border-left: 4px solid #ef4444;
    padding: 1.25rem;
    margin: 1rem 0;
    border-radius: 0 12px 12px 0;
}

.success-box {
    background: linear-gradient(145deg, rgba(16, 185, 129, 0.08), rgba(16, 185, 129, 0.04));
    border-left: 4px solid #10b981;
    padding: 1.25rem;
    margin: 1rem 0;
    border-radius: 0 12px 12px 0;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #020617 0%, #0f172a 100%);
    border-right: 1px solid rgba(20, 184, 166, 0.1);
}

[data-testid="stSidebar"] [data-testid="stMarkdown"] {
    color: #e2e8f0;
}

.stButton > button {
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    color: #ffffff;
    border: none;
    border-radius: 12px;
    padding: 0.625rem 2rem;
    font-weight: 600;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    box-shadow: 0 4px 16px rgba(13, 148, 136, 0.2);
    letter-spacing: 0.02em;
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 24px rgba(13, 148, 136, 0.3);
}

.stTextInput > div > div > input,
.stSelectbox > div > div > div,
.stTextArea > div > div > textarea {
    background-color: rgba(15, 23, 42, 0.8) !important;
    border: 1px solid rgba(20, 184, 166, 0.15) !important;
    border-radius: 12px !important;
    color: #e2e8f0 !important;
    font-size: 0.95rem !important;
}

.stTextInput > div > div > input:focus,
.stSelectbox > div > div > div:focus,
.stTextArea > div > div > textarea:focus {
    border-color: rgba(20, 184, 166, 0.4) !important;
    box-shadow: 0 0 12px rgba(13, 148, 136, 0.15) !important;
}

.stTabs [data-baseweb="tab-list"] {
    background: rgba(15, 23, 42, 0.7);
    border-radius: 16px;
    padding: 6px;
    backdrop-filter: blur(12px);
    gap: 4px;
    flex-wrap: wrap;
    justify-content: flex-start;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #94a3b8;
    border-radius: 12px;
    padding: 12px 24px;
    font-weight: 500;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #94a3b8;
    border-radius: 12px;
    padding: 12px 24px;
    font-weight: 500;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    color: #ffffff;
}

.stDataFrame {
    background: rgba(15, 23, 42, 0.8);
    border-radius: 12px;
}

.stMetric {
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(20, 184, 166, 0.1);
    border-radius: 16px;
    padding: 1.25rem;
    backdrop-filter: blur(12px);
}

.stMetric label {
    color: #94a3b8 !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    font-size: 0.75rem !important;
    letter-spacing: 0.05em !important;
}

.stMetric [data-testid="stMetricValue"] {
    color: #14b8a6 !important;
    font-weight: 700 !important;
    font-family: 'JetBrains Mono', monospace !important;
}

.stExpander {
    background: rgba(15, 23, 42, 0.7);
    border: 1px solid rgba(20, 184, 166, 0.1);
    border-radius: 16px;
    backdrop-filter: blur(12px);
}

h1, h2, h3, h4, h5, h6 {
    color: #e2e8f0 !important;
    font-weight: 700 !important;
}

p, span, div {
    color: #cbd5e1;
}

.stFileUploader {
    background: rgba(15, 23, 42, 0.7);
    border: 2px dashed rgba(20, 184, 166, 0.3);
    border-radius: 16px;
    padding: 1.25rem;
    transition: all 0.3s ease;
    backdrop-filter: blur(12px);
}

.stFileUploader:hover {
    border-color: rgba(20, 184, 166, 0.6);
    box-shadow: 0 0 20px rgba(13, 148, 136, 0.1);
}

.hero-badge {
    display: inline-block;
    background: rgba(13, 148, 136, 0.1);
    border: 1px solid rgba(20, 184, 166, 0.25);
    border-radius: 30px;
    padding: 8px 20px;
    font-size: 0.875rem;
    color: #14b8a6;
    font-weight: 600;
    margin-bottom: 1rem;
}

.logo-link {
    display: block;
    margin-bottom: 1rem;
    transition: transform 0.2s ease, opacity 0.2s ease;
}

.logo-link:hover {
    transform: scale(1.02);
    opacity: 0.85;
}

.sidebar-logo {
    width: 100%;
    border-radius: 12px;
    cursor: pointer;
}

/* ═══════════════════════════════════════════════════════════════
   LANDING PAGE — DESIGN SYSTEM
   Aesthetic: "Data Noir" — dark precision, editorial, desktop-first
   Fonts: Syne (headings) + DM Sans (body) + JetBrains Mono (data)
   ═══════════════════════════════════════════════════════════════ */

/* ── Entrance animations ─────────────────────────────────────── */
@keyframes fadeSlideUp {
    from { opacity: 0; transform: translateY(20px); }
    to   { opacity: 1; transform: translateY(0); }
}
.lp-hero     { animation: fadeSlideUp 0.28s ease-out both; animation-delay: 0.04s; }
.lp-trust    { animation: fadeSlideUp 0.28s ease-out both; animation-delay: 0.12s; }
.lp-features { animation: fadeSlideUp 0.28s ease-out both; animation-delay: 0.20s; }
.lp-hiw      { animation: fadeSlideUp 0.28s ease-out both; animation-delay: 0.28s; }
.lp-tiers    { animation: fadeSlideUp 0.28s ease-out both; animation-delay: 0.36s; }
@media (prefers-reduced-motion: reduce) {
    .lp-hero,.lp-trust,.lp-features,.lp-hiw,.lp-tiers { animation: none !important; }
}

/* ── Section shared container ────────────────────────────────── */
.lp-section-inner { max-width: 1200px; margin: 0 auto; padding: 0; }
.lp-section-block { padding: 4rem 0 3rem 0; }
.lp-section-header { text-align: center; margin-bottom: 2.5rem; }
.lp-section-header h2 {
    font-family: 'Syne', sans-serif !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.03em !important;
    margin-bottom: 0.5rem !important;
    line-height: 1.1 !important;
}
.lp-section-header p {
    font-size: 1rem;
    color: var(--text-secondary);
    line-height: 1.65;
    max-width: 560px;
    margin: 0 auto;
}
/* Subtle teal rule under section headings */
.lp-section-header h2::after {
    content: '';
    display: block;
    width: 36px;
    height: 3px;
    background: linear-gradient(90deg, var(--teal-mid), transparent);
    border-radius: 2px;
    margin: 0.6rem auto 0 auto;
}

/* ── Trust bar ───────────────────────────────────────────────── */
.lp-trust-bar {
    display: flex;
    justify-content: center;
    gap: 1.25rem;
    flex-wrap: wrap;
    padding: 1.25rem 0 0.5rem 0;
}
.lp-trust-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    background: rgba(45, 212, 191, 0.06);
    border: 1px solid rgba(45, 212, 191, 0.18);
    border-radius: 100px;
    padding: 0.5rem 1.4rem;
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--teal);
    letter-spacing: 0.01em;
    font-family: 'JetBrains Mono', monospace;
}
.lp-trust-pill::before {
    content: '';
    display: inline-block;
    width: 6px; height: 6px;
    background: var(--teal);
    border-radius: 50%;
    box-shadow: 0 0 6px var(--teal);
    flex-shrink: 0;
}

/* ── Feature cards ───────────────────────────────────────────── */
.lp-feature-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1.25rem;
    margin: 0 0 0.5rem 0;
}
@media (max-width: 960px)  { .lp-feature-grid { grid-template-columns: repeat(2,1fr); } }
@media (max-width: 560px)  { .lp-feature-grid { grid-template-columns: 1fr; } }
.lp-feat-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 2rem 1.5rem 1.75rem 1.5rem;
    text-align: left;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    transition: border-color 0.22s ease-out, transform 0.22s ease-out, box-shadow 0.22s ease-out;
    cursor: default;
    position: relative;
    overflow: hidden;
}
.lp-feat-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--teal-mid), var(--indigo));
    opacity: 0;
    transition: opacity 0.22s ease-out;
}
.lp-feat-card:hover { border-color: var(--border-hover); transform: translateY(-6px); box-shadow: 0 20px 48px rgba(0,0,0,0.45); }
.lp-feat-card:hover::before { opacity: 1; }

/* nth-child stagger on enter hover (30-50ms per skill) */
.lp-feature-grid .lp-feat-card:nth-child(2) { transition-delay: 35ms; }
.lp-feature-grid .lp-feat-card:nth-child(3) { transition-delay: 70ms; }
.lp-feature-grid .lp-feat-card:nth-child(4) { transition-delay: 105ms; }

.lp-feat-icon {
    width: 44px; height: 44px;
    margin: 0 0 1.25rem 0;
    background: rgba(45, 212, 191, 0.10);
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    font-size: 1.2rem; line-height: 1;
}
.lp-feat-icon { color: var(--teal-mid); }
/* CSS-only icons — SVG stripped by Markdown parser */
.lp-icon-1::after { content: '\2726'; font-size: 1.2rem; color: var(--teal); }
.lp-icon-2::after { content: '\25A0\25A0\25A0'; font-size: 0.6rem; letter-spacing: 3px; color: var(--teal); }
.lp-icon-3::after { content: '\25C6'; font-size: 1.2rem; color: var(--teal); }
.lp-icon-4::after { content: '\25B2'; font-size: 1rem; color: var(--teal); }

.lp-feat-title { font-size: 1.05rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.5rem; letter-spacing: -0.01em; }
.lp-feat-desc  { font-size: 0.875rem; color: var(--text-muted); line-height: 1.6; }

/* ── How It Works ────────────────────────────────────────────── */
.lp-hiw-section { text-align: center; padding: 0 0 1rem 0; }
.lp-hiw-section h2 {
    font-family: 'Syne', sans-serif !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.03em !important;
    margin-bottom: 0.5rem !important;
    line-height: 1.1 !important;
}
.lp-hiw-section h2::after {
    content: '';
    display: block;
    width: 36px; height: 3px;
    background: linear-gradient(90deg, var(--teal-mid), transparent);
    border-radius: 2px;
    margin: 0.6rem auto 2rem auto;
}
.lp-steps-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.5rem;
    margin-top: 0.5rem;
}
@media (max-width: 720px) { .lp-steps-grid { grid-template-columns: 1fr; } }
.lp-step-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 2.25rem 2rem;
    backdrop-filter: blur(16px);
    text-align: left;
    transition: border-color 0.22s ease-out, transform 0.22s ease-out;
    position: relative;
}
.lp-step-card:hover { border-color: var(--border-hover); transform: translateY(-4px); }
.lp-step-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.5rem; font-weight: 700;
    color: rgba(45, 212, 191, 0.18);
    line-height: 1;
    margin-bottom: 1rem;
    letter-spacing: -0.04em;
}
.lp-step-title { font-size: 1.05rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.5rem; letter-spacing: -0.01em; }
.lp-step-desc  { font-size: 0.875rem; color: var(--text-muted); line-height: 1.65; }

/* ── Tiers teaser ────────────────────────────────────────────── */
.lp-tiers-section { text-align: center; padding: 0 0 1rem 0; }
.lp-tiers-section h2 {
    font-family: 'Syne', sans-serif !important;
    font-size: 2rem !important;
    font-weight: 800 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.03em !important;
    margin-bottom: 0.5rem !important;
    line-height: 1.1 !important;
}
.lp-tiers-section h2::after {
    content: '';
    display: block;
    width: 36px; height: 3px;
    background: linear-gradient(90deg, var(--teal-mid), transparent);
    border-radius: 2px;
    margin: 0.6rem auto 0 auto;
}
.lp-tiers-sub { font-size: 1rem; color: var(--text-secondary); margin-bottom: 2rem; line-height: 1.6; }
.lp-tiers-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.25rem;
    margin-bottom: 1.75rem;
    align-items: start;
}
@media (max-width: 720px) { .lp-tiers-grid { grid-template-columns: 1fr; } }
.lp-tier-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 2rem 1.75rem;
    text-align: left;
    backdrop-filter: blur(16px);
    transition: border-color 0.22s ease-out, transform 0.22s ease-out, box-shadow 0.22s ease-out;
}
.lp-tier-card:hover { border-color: var(--border-hover); transform: translateY(-4px); }
.lp-tier-card.featured {
    border-color: rgba(45, 212, 191, 0.35);
    box-shadow: 0 0 48px rgba(13, 148, 136, 0.14), inset 0 0 32px rgba(13,148,136,0.04);
    transform: translateY(-6px);
}
.lp-tier-card.featured:hover { transform: translateY(-10px); }
.lp-tier-badge {
    display: inline-block;
    background: linear-gradient(135deg, var(--teal-mid), var(--teal-dark));
    color: #fff;
    font-size: 0.65rem; font-weight: 700;
    letter-spacing: 0.1em; padding: 4px 12px;
    border-radius: 100px; margin-bottom: 1rem;
    text-transform: uppercase; font-family: 'JetBrains Mono', monospace;
}
.lp-tier-name    { font-size: 1.3rem; font-weight: 800; color: var(--text-primary); margin-bottom: 0.3rem; letter-spacing: -0.02em; font-family: 'Syne', sans-serif; }
.lp-tier-tagline { font-size: 0.875rem; color: var(--text-muted); margin-bottom: 1.5rem; line-height: 1.5; }
.lp-tier-divider { height: 1px; background: var(--border); margin-bottom: 1.25rem; }
.lp-tier-features { list-style: none; padding: 0; margin: 0; }
.lp-tier-features li {
    font-size: 0.875rem; color: var(--text-secondary);
    padding: 0.4rem 0;
    display: flex; align-items: flex-start; gap: 0.6rem;
    border-bottom: 1px solid rgba(255,255,255,0.04);
}
.lp-tier-features li:last-child { border-bottom: none; }
.lp-check { color: var(--teal); font-weight: 700; font-size: 0.9rem; flex-shrink: 0; line-height: 1.4; }

/* ── Support form ────────────────────────────────────────────── */
.lp-support-section { margin: 1rem 0 0.5rem 0; }
.lp-support-header { text-align: center; margin-bottom: 1.75rem; }
.lp-support-header h2 { font-family: 'Syne', sans-serif !important; font-size: 1.75rem !important; font-weight: 800 !important; color: var(--text-primary) !important; margin-bottom: 0.4rem !important; letter-spacing: -0.02em !important; }
.lp-support-header p { font-size: 0.95rem; color: var(--text-secondary); }
.lp-support-card { background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 2rem; backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px); }

/* ── CTA button variants (desktop scale) ─────────────────────── */
.lp-btn-primary > div > button,
.lp-btn-secondary > div > button,
.lp-btn-outline > div > button {
    touch-action: manipulation !important;
    min-height: 52px !important;
    font-family: 'DM Sans', sans-serif !important;
}
.lp-btn-primary > div > button {
    background: linear-gradient(135deg, var(--teal-mid), var(--teal-dark)) !important;
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    padding: 0.9rem 2.5rem !important;
    border-radius: 14px !important;
    box-shadow: 0 6px 28px rgba(13,148,136,0.35) !important;
    cursor: pointer !important;
    letter-spacing: 0.01em !important;
}
.lp-btn-primary > div > button:hover { box-shadow: 0 10px 36px rgba(13,148,136,0.50) !important; transform: translateY(-2px) !important; }
.lp-btn-primary > div > button:active { transform: translateY(0) scale(0.98) !important; box-shadow: 0 4px 14px rgba(13,148,136,0.28) !important; }

.lp-btn-secondary > div > button {
    background: rgba(12, 24, 41, 0.9) !important;
    border: 1px solid rgba(45,212,191,0.28) !important;
    color: var(--teal) !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
    box-shadow: none !important;
    cursor: pointer !important;
}
.lp-btn-secondary > div > button:hover { background: rgba(45,212,191,0.10) !important; border-color: rgba(45,212,191,0.50) !important; transform: translateY(-1px) !important; }
.lp-btn-secondary > div > button:active { transform: scale(0.97) !important; background: rgba(45,212,191,0.18) !important; }

.lp-btn-outline > div > button {
    background: transparent !important;
    border: 1px solid rgba(45,212,191,0.22) !important;
    color: var(--text-secondary) !important;
    font-size: 0.9rem !important;
    font-weight: 500 !important;
    box-shadow: none !important;
    cursor: pointer !important;
}
.lp-btn-outline > div > button:hover { border-color: rgba(45,212,191,0.48) !important; color: var(--teal) !important; }
.lp-btn-outline > div > button:active { background: rgba(45,212,191,0.08) !important; transform: scale(0.98) !important; }

/* ── Streamlit header hide (custom nav replaces it) ─────────── */
[data-testid="stHeader"] { display: none !important; }

/* ── Top spacer for fixed nav (injected per-page) ────────────── */
.lp-nav-spacer { height: 88px; }

/* ── Navbar ──────────────────────────────────────────────────── */
.lp-nav {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 9999;
    height: 78px;
    background: rgba(7,16,31,0.93);
    backdrop-filter: blur(24px);
    -webkit-backdrop-filter: blur(24px);
    border-bottom: 1px solid rgba(45,212,191,0.10);
}
.lp-nav-inner {
    max-width: 1320px; height: 100%;
    margin: 0 auto; padding: 0 3rem;
    display: flex; align-items: center; justify-content: space-between;
}
.lp-nav-logo { display: flex; align-items: center; text-decoration: none; }
.lp-nav-logo img { height: 60px; width: auto; }
.lp-features, .lp-hiw, .lp-tiers, .lp-support-section { scroll-margin-top: 90px; }
html { scroll-behavior: smooth; }
.lp-nav-links { display: flex; align-items: center; gap: 2.25rem; }
.lp-nav-link { font-size: 0.875rem; font-weight: 500; color: var(--text-secondary) !important; text-decoration: none !important; letter-spacing: 0.01em; transition: color 0.15s; cursor: pointer; }
.lp-nav-link:hover { color: var(--teal); }
.lp-nav-actions { display: flex; align-items: center; }
.lp-nav-signin-link {
    font-size: 0.875rem; font-weight: 500; cursor: pointer;
    color: var(--teal); border: 1px solid rgba(45,212,191,0.28);
    border-radius: 10px; padding: 0.4rem 1.25rem;
    transition: background 0.15s, border-color 0.15s;
    letter-spacing: 0.01em; white-space: nowrap;
}
.lp-nav-signin-link:hover { background: rgba(45,212,191,0.08); border-color: rgba(45,212,191,0.55); }
.lp-nav-signin-link, .lp-nav-signin-link:visited { text-decoration: none !important; color: var(--teal) !important; }

/* ── CTA tagline below hero button ───────────────────────────── */
.lp-cta-tag { font-size: 0.79rem; color: var(--text-muted); text-align: center; font-family: 'JetBrains Mono', monospace; letter-spacing: 0.02em; margin-top: 0.6rem; }
.lp-cta-tag b { color: var(--teal); font-weight: 500; }

/* ── Professional support section ────────────────────────────── */
.lp-support-pro-wrap { background: var(--surface); border: 1px solid var(--border); border-radius: 24px; overflow: hidden; }
.lp-support-left {
    padding: 2.75rem 2.5rem;
    background: linear-gradient(160deg, var(--surface-2) 0%, var(--surface) 100%);
    border-right: 1px solid var(--border); min-height: 380px;
}
.lp-support-left h3 {
    font-family: 'Syne', sans-serif !important;
    font-size: 1.65rem !important; font-weight: 800 !important;
    color: var(--text-primary) !important;
    letter-spacing: -0.02em !important; margin-bottom: 0.5rem !important; line-height: 1.15 !important;
}
.lp-support-tagline { font-size: 0.9rem; color: var(--text-secondary); line-height: 1.65; margin-bottom: 2.25rem; max-width: 320px; }
.lp-support-contact-item { display: flex; align-items: flex-start; gap: 0.9rem; margin-bottom: 1.4rem; }
.lp-support-icon {
    width: 38px; height: 38px; border-radius: 10px;
    background: rgba(45,212,191,0.08); border: 1px solid rgba(45,212,191,0.14);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0; font-size: 0.95rem; line-height: 1;
}
.lp-support-icon-email::after { content: '\2709'; color: var(--teal); }
.lp-support-icon-clock::after { content: '\23F1'; color: var(--teal); }
.lp-support-icon-check::after { content: '\2713'; color: var(--teal); font-weight: 900; font-size: 1.05rem; }
.lp-support-contact-label { font-size: 0.72rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: 0.2rem; }
.lp-support-contact-value { font-size: 0.9rem; color: var(--text-primary); font-weight: 500; }
.lp-support-right { padding: 2.75rem 2.5rem; }
.lp-support-right h4 { font-family: 'Syne', sans-serif !important; font-size: 1.2rem !important; font-weight: 700 !important; color: var(--text-primary) !important; margin-bottom: 1.35rem !important; letter-spacing: -0.01em !important; }

/* ── Support form inputs — match sign-in page style ───────── */
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextInput"] label,
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextInput"] label p,
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextArea"] label,
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextArea"] label p {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem !important; font-weight: 500 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    color: var(--text-secondary) !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextInput"] input,
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextArea"] textarea {
    background: #ffffff !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    padding: 0.9rem 1rem !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important;
    color: #07101f !important;
    -webkit-text-fill-color: #07101f !important;
    transition: border-color 0.18s, box-shadow 0.18s !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextInput"] > div > div,
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextArea"] > div > div {
    background: #ffffff !important;
    border-radius: 10px !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextInput"] input:focus,
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextArea"] textarea:focus {
    border-color: rgba(45,212,191,0.65) !important;
    box-shadow: 0 0 0 3px rgba(45,212,191,0.18) !important;
    outline: none !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextInput"] input::placeholder,
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stTextArea"] textarea::placeholder {
    color: rgba(7,16,31,0.38) !important; opacity: 1 !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stForm"] {
    background: transparent !important;
    border: none !important;
    padding: 0 !important;
    box-shadow: none !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stFormSubmitButton"] button {
    background: linear-gradient(135deg, #2dd4bf 0%, #14b8a6 100%) !important;
    color: #07101f !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.85rem 1rem !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important; font-weight: 700 !important;
    box-shadow: 0 8px 24px rgba(45,212,191,0.28) !important;
    transition: transform 0.15s, box-shadow 0.15s, filter 0.15s !important;
    margin-top: 0.6rem !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stFormSubmitButton"] button:hover {
    transform: translateY(-1px) !important;
    box-shadow: 0 12px 32px rgba(45,212,191,0.4) !important;
    filter: brightness(1.05) !important;
}
[data-testid="stColumn"]:has(.lp-support-right) [data-testid="stFormSubmitButton"] button p {
    color: #07101f !important; font-weight: 700 !important; font-size: 0.95rem !important;
}

/* ── Footer ──────────────────────────────────────────────────── */
.lp-footer { border-top: 1px solid rgba(255,255,255,0.06); padding: 3.5rem 0 2rem 0; margin-top: 4rem; }
.lp-footer-inner { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 4rem; margin-bottom: 3rem; }
.lp-footer-brand-desc { font-size: 0.875rem; color: var(--text-muted); line-height: 1.7; margin-top: 0.85rem; max-width: 280px; }
.lp-footer-col-title { font-size: 0.72rem; font-weight: 600; color: var(--text-secondary); letter-spacing: 0.08em; text-transform: uppercase; font-family: 'JetBrains Mono', monospace; margin-bottom: 1.25rem; }
.lp-footer-links-list { list-style: none; padding: 0; margin: 0; }
.lp-footer-links-list li { margin-bottom: 0.75rem; }
.lp-footer-links-list a { font-size: 0.875rem; color: var(--text-muted); text-decoration: none; transition: color 0.15s; }
.lp-footer-links-list a:hover { color: var(--teal); }
.lp-footer-bottom { border-top: 1px solid rgba(255,255,255,0.05); padding-top: 1.75rem; display: flex; align-items: center; justify-content: space-between; max-width: 1200px; margin: 0 auto; }
.lp-footer-copy { font-size: 0.78rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
.lp-footer-status { display: inline-flex; align-items: center; gap: 0.5rem; font-size: 0.78rem; color: var(--text-muted); font-family: 'JetBrains Mono', monospace; }
.lp-footer-status::before { content: ''; display: inline-block; width: 6px; height: 6px; background: var(--teal); border-radius: 50%; box-shadow: 0 0 6px var(--teal); }

/* ════════════════════════════════════════════════════════════════════ */
/* DASHBOARD — Data Noir post-login chrome (top nav + side menu)        */
/* ════════════════════════════════════════════════════════════════════ */
.dn-topnav {
    position: sticky; top: 0; z-index: 50;
    background: rgba(7,16,31,0.78); backdrop-filter: blur(14px) saturate(160%);
    -webkit-backdrop-filter: blur(14px) saturate(160%);
    border-bottom: 1px solid rgba(45,212,191,0.10);
    margin: -1rem -1rem 1.25rem -1rem; padding: 0.85rem 2rem;
}
.dn-topnav-inner { display: flex; align-items: center; justify-content: space-between; max-width: 1320px; margin: 0 auto; }
.dn-topnav-brand { display: flex; align-items: center; gap: 0.85rem; text-decoration: none; }
.dn-topnav-brand img { height: 36px; width: auto; }
.dn-topnav-brand-text { font-family: 'Syne', sans-serif; font-size: 1.1rem; font-weight: 700; color: #e2e8f0; letter-spacing: -0.01em; }
.dn-topnav-eyebrow {
    display: inline-flex; align-items: center; gap: 0.45rem;
    font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; letter-spacing: 0.18em;
    text-transform: uppercase; color: var(--teal);
    padding: 0.32rem 0.72rem; border: 1px solid rgba(45,212,191,0.22); border-radius: 100px;
    background: rgba(45,212,191,0.05);
}
.dn-topnav-eyebrow::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 6px var(--teal); }
.dn-topnav-user { display: flex; align-items: center; gap: 0.7rem; }
.dn-topnav-avatar {
    width: 36px; height: 36px; border-radius: 50%;
    background: linear-gradient(135deg, var(--teal-mid), var(--teal-dark));
    display: inline-flex; align-items: center; justify-content: center;
    font-family: 'Syne', sans-serif; font-weight: 700; font-size: 0.95rem; color: #07101f;
    border: 1px solid rgba(45,212,191,0.35);
}
.dn-topnav-meta { display: flex; flex-direction: column; line-height: 1.15; }
.dn-topnav-name { font-family: 'DM Sans', sans-serif; font-size: 0.88rem; font-weight: 600; color: #e2e8f0; }
.dn-topnav-tier { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--teal); margin-top: 1px; }

/* Side menu (rendered inside left Streamlit column) */
.dn-side {
    background: linear-gradient(180deg, rgba(12,24,41,0.85) 0%, rgba(7,16,31,0.85) 100%);
    border: 1px solid rgba(45,212,191,0.12);
    border-radius: 18px; padding: 1.4rem 1.1rem;
    backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
    position: sticky; top: 6.5rem;
}
.dn-side-section-label {
    font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; letter-spacing: 0.22em;
    text-transform: uppercase; color: rgba(148,163,184,0.55);
    padding: 0.3rem 0.5rem 0.55rem 0.5rem; display: flex; align-items: center; gap: 0.6rem;
}
.dn-side-section-label::after { content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, rgba(45,212,191,0.18), transparent); }
.dn-side-divider { height: 1px; background: rgba(255,255,255,0.04); margin: 1rem 0.3rem; }

/* Style buttons inside .dn-side-nav-wrap as nav items */
[data-testid="stColumn"]:has(.dn-side-marker) [data-testid="stButton"] > button,
[data-testid="stColumn"]:has(.dn-side-marker) [data-testid="stForm"] [data-testid="stFormSubmitButton"] > button {
    background: transparent !important; border: 1px solid transparent !important;
    color: #cbd5e1 !important; font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important; font-size: 0.92rem !important;
    text-align: left !important; justify-content: flex-start !important;
    padding: 0.65rem 0.85rem !important; height: auto !important; min-height: 0 !important;
    border-radius: 10px !important; box-shadow: none !important;
    letter-spacing: 0.01em !important; line-height: 1.3 !important;
    transition: all 0.18s ease !important; margin-bottom: 0.25rem !important;
}
[data-testid="stColumn"]:has(.dn-side-marker) [data-testid="stButton"] > button:hover {
    background: rgba(45,212,191,0.08) !important; color: var(--teal) !important;
    border-color: rgba(45,212,191,0.18) !important;
    transform: translateX(2px);
}
[data-testid="stColumn"]:has(.dn-side-marker) [data-testid="stButton"] > button p {
    color: inherit !important; font-weight: inherit !important; font-size: inherit !important;
    margin: 0 !important;
}
.dn-side-active-marker { display:none; }

/* Welcome / hero greeting in main col */
.dn-greeting {
    margin: 0 0 1.5rem 0; padding: 1.6rem 1.8rem;
    background: linear-gradient(120deg, rgba(45,212,191,0.06) 0%, rgba(13,148,136,0.02) 60%, transparent 100%);
    border: 1px solid rgba(45,212,191,0.13); border-radius: 16px;
    position: relative; overflow: hidden;
}
.dn-greeting::before {
    content: ''; position: absolute; top: -50%; right: -10%;
    width: 280px; height: 280px;
    background: radial-gradient(circle, rgba(45,212,191,0.10) 0%, transparent 70%);
    pointer-events: none;
}
.dn-greeting-eyebrow {
    font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; letter-spacing: 0.22em;
    text-transform: uppercase; color: var(--teal); margin-bottom: 0.55rem;
}
.dn-greeting h1 {
    font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.95rem;
    letter-spacing: -0.025em; color: #f1f5f9; margin: 0 0 0.35rem 0; line-height: 1.15;
    background: linear-gradient(135deg, #f1f5f9 0%, #2dd4bf 90%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}
.dn-greeting-sub { font-family: 'DM Sans', sans-serif; font-size: 0.96rem; color: #94a3b8; margin: 0; line-height: 1.55; }

/* Slim inline contact drawer */
.dn-contact-slim {
    margin: 1.5rem 0; padding: 1.5rem 1.75rem;
    background: rgba(12,24,41,0.6); border: 1px solid rgba(45,212,191,0.16);
    border-radius: 14px; backdrop-filter: blur(8px);
}
.dn-contact-slim-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 1rem; }
.dn-contact-slim-head h3 { font-family: 'Syne', sans-serif; font-weight: 700; font-size: 1.15rem; color: #e2e8f0; margin: 0; letter-spacing: -0.01em; }
.dn-contact-slim-head .dn-contact-meta { font-family: 'JetBrains Mono', monospace; font-size: 0.7rem; color: rgba(148,163,184,0.7); letter-spacing: 0.1em; text-transform: uppercase; }

/* Flat top bar — no logo, just wordmark + eyebrow */
.dn-topbar {
    display: flex; align-items: center; gap: 1.25rem;
    padding: 0.45rem 0.25rem;
}
.dn-topbar-brand {
    font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.35rem;
    color: #f1f5f9; letter-spacing: -0.025em;
}
.dn-topbar-eyebrow {
    display: inline-flex; align-items: center; gap: 0.5rem;
    font-family: 'JetBrains Mono', monospace; font-size: 0.62rem; letter-spacing: 0.2em;
    text-transform: uppercase; color: var(--teal);
    padding: 0.32rem 0.75rem; border: 1px solid rgba(45,212,191,0.22); border-radius: 100px;
    background: rgba(45,212,191,0.05);
}
.dn-topbar-eyebrow::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: var(--teal); box-shadow: 0 0 6px var(--teal); }

/* Popover trigger button — styled as avatar pill */
[data-testid="stColumn"]:has(.dn-pop-trigger-marker) [data-testid="stPopover"] > div > button {
    background: linear-gradient(135deg, rgba(45,212,191,0.12), rgba(13,148,136,0.06)) !important;
    border: 1px solid rgba(45,212,191,0.22) !important;
    color: #e2e8f0 !important;
    font-family: 'DM Sans', sans-serif !important; font-weight: 600 !important;
    font-size: 0.88rem !important; letter-spacing: 0.01em !important;
    padding: 0.55rem 1rem !important; height: auto !important;
    border-radius: 100px !important; box-shadow: none !important;
    transition: all 0.18s ease !important;
}
[data-testid="stColumn"]:has(.dn-pop-trigger-marker) [data-testid="stPopover"] > div > button:hover {
    border-color: rgba(45,212,191,0.45) !important;
    background: linear-gradient(135deg, rgba(45,212,191,0.2), rgba(13,148,136,0.1)) !important;
    box-shadow: 0 0 0 3px rgba(45,212,191,0.10) !important;
}
[data-testid="stColumn"]:has(.dn-pop-trigger-marker) [data-testid="stPopover"] > div > button p {
    color: inherit !important; font-size: inherit !important; font-weight: inherit !important; margin: 0 !important;
}

/* Popover dropdown content (rendered at body level) */
[data-baseweb="popover"] [data-testid="stPopoverBody"] {
    background: linear-gradient(180deg, #0c1829 0%, #07101f 100%) !important;
    border: 1px solid rgba(45,212,191,0.22) !important;
    border-radius: 14px !important;
    box-shadow: 0 18px 48px rgba(0,0,0,0.5), 0 0 0 1px rgba(45,212,191,0.05) !important;
    padding: 1rem 0.85rem !important;
    min-width: 240px !important;
}
.dn-pop-head { display: flex; align-items: center; gap: 0.85rem; padding: 0.25rem 0.4rem 0.6rem 0.4rem; }
.dn-pop-avatar {
    width: 42px; height: 42px; border-radius: 50%;
    background: linear-gradient(135deg, var(--teal-mid), var(--teal-dark));
    display: inline-flex; align-items: center; justify-content: center;
    font-family: 'Syne', sans-serif; font-weight: 800; font-size: 1.1rem; color: #07101f;
    border: 1px solid rgba(45,212,191,0.4);
    flex-shrink: 0;
}
.dn-pop-name { font-family: 'DM Sans', sans-serif; font-size: 0.95rem; font-weight: 600; color: #f1f5f9; line-height: 1.2; }
.dn-pop-tier { font-family: 'JetBrains Mono', monospace; font-size: 0.66rem; letter-spacing: 0.16em; text-transform: uppercase; color: var(--teal); margin-top: 3px; }
.dn-pop-divider { height: 1px; background: linear-gradient(90deg, transparent, rgba(45,212,191,0.25), transparent); margin: 0.4rem 0 0.6rem 0; }

/* Popover menu buttons (Admin / Contact / Sign Out) */
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stButton"] > button {
    background: transparent !important; border: 1px solid transparent !important;
    color: #cbd5e1 !important; font-family: 'DM Sans', sans-serif !important;
    font-weight: 500 !important; font-size: 0.92rem !important;
    text-align: left !important; justify-content: flex-start !important;
    padding: 0.6rem 0.85rem !important; height: auto !important; min-height: 0 !important;
    border-radius: 9px !important; box-shadow: none !important;
    transition: all 0.16s ease !important; margin-bottom: 0.2rem !important;
}
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stButton"] > button:hover {
    background: rgba(45,212,191,0.10) !important; color: var(--teal) !important;
    border-color: rgba(45,212,191,0.22) !important;
}
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stButton"] > button p {
    color: inherit !important; font-weight: inherit !important; font-size: inherit !important; margin: 0 !important;
}

</style>

"""

st.markdown(NEON_CSS, unsafe_allow_html=True)

TIER1_LIMITS = {
    'max_rows': 10000,
    'max_analyses_per_day': 5,
    'max_file_size_mb': 50,
    'ai_chat_enabled': False,
    'predictions_enabled': False,
    'export_enabled': False,
    'ml_enabled': True
}

TIER2_LIMITS = {
    'max_rows': 500000,
    'max_analyses_per_day': 50,
    'max_file_size_mb': 200,
    'ai_chat_enabled': False,
    'predictions_enabled': True,
    'export_enabled': False,
    'ml_enabled': True
}

TIER3_LIMITS = {
    'max_rows': 1000000,
    'max_analyses_per_day': 999999,
    'max_file_size_mb': 200,
    'ai_chat_enabled': True,
    'predictions_enabled': True,
    'export_enabled': True,
    'ml_enabled': True
}

init_db()

SESSION_QP_NAME = "sid"

if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'home'

if 'session_hydrated' not in st.session_state:
    st.session_state.session_hydrated = False

try:
    if st.query_params.get('signin') == '1':
        st.session_state.page = 'login'
        st.query_params.clear()
    elif st.query_params.get('register') == '1':
        st.session_state.page = 'register'
        st.query_params.clear()
except Exception:
    pass
if 'df' not in st.session_state:
    st.session_state.df = None
if 'df_cleaned' not in st.session_state:
    st.session_state.df_cleaned = None
if 'cleaning_report' not in st.session_state:
    st.session_state.cleaning_report = None
if 'analysis_results' not in st.session_state:
    st.session_state.analysis_results = None
if 'ai_insights' not in st.session_state:
    st.session_state.ai_insights = None
if 'chat_messages' not in st.session_state:
    st.session_state.chat_messages = []
if 'current_dataset_id' not in st.session_state:
    st.session_state.current_dataset_id = None
if 'step_histories' not in st.session_state:
    st.session_state.step_histories = {}
if 'inferred_schema' not in st.session_state:
    st.session_state.inferred_schema = {}
if 'type_overrides' not in st.session_state:
    st.session_state.type_overrides = {}
if 'cleaning_substep_states' not in st.session_state:
    st.session_state.cleaning_substep_states = {}


def _ds_key():
    return st.session_state.get('current_dataset_id') or '__local__'


def _get_step_history(create=False):
    key = _ds_key()
    sh = st.session_state.step_histories.get(key)
    if sh is None and create:
        sh = StepHistory()
        st.session_state.step_histories[key] = sh
    return sh


def _apply_cleaning_substeps(history: StepHistory, base_df,
                             enabled_map: dict) -> tuple:
    """Append one Step per cleaning substep onto `history`, then return
    (final_df, aggregated_report). Disabled substeps still appear as
    pass-through entries so the user can flip them back on later."""
    report = {
        'original_rows': len(base_df),
        'original_columns': len(base_df.columns),
        'changes': [],
        'substeps': [],
    }
    current = base_df
    for key, label in CLEANING_SUBSTEPS:
        on = bool(enabled_map.get(key, True))
        if on:
            current, summary, details = SUBSTEP_FUNCS[key](current)
            report['changes'].extend(details.get('changes', []))
        else:
            summary, details = "Disabled — pass through", {}
        history.add(label, summary, current,
                    meta={'substep_key': key, 'enabled': on,
                          'details': details})
        report['substeps'].append({
            'key': key, 'label': label, 'enabled': on,
            'summary': summary, 'details': details,
        })
    report['final_rows'] = len(current)
    report['final_columns'] = len(current.columns)
    report['rows_removed'] = report['original_rows'] - report['final_rows']
    return current, report


def _rebuild_cleaning_substeps(sh: StepHistory, enabled_map: dict):
    """Rebuild the contiguous cleaning block at the tail of `sh`.

    Drops every step from the first cleaning substep onward (this also
    discards any later manual edits, mirroring `drop_later` semantics
    elsewhere), then re-applies all substeps with the new enabled map.
    Returns (final_df, report) or (None, None) if no cleaning block found.
    """
    first_idx = None
    for i, s in enumerate(sh.steps):
        if s.meta.get('substep_key'):
            first_idx = i
            break
    if first_idx is None or first_idx == 0:
        return None, None
    base_df = sh.steps[first_idx - 1].df
    sh.steps = sh.steps[:first_idx]
    sh.active_index = len(sh.steps) - 1
    final_df, report = _apply_cleaning_substeps(sh, base_df, enabled_map)
    sh.active_index = len(sh.steps) - 1
    return final_df, report


def _persist_step_history():
    """Save the current dataset's step recipes + active pointer to the DB.

    Called after any user-driven mutation (manual override, navigation,
    drop/redo) so the history survives sign-out and refresh.
    """
    ds_id = st.session_state.get('current_dataset_id')
    if not ds_id or not isinstance(ds_id, int):
        return
    sh = st.session_state.step_histories.get(ds_id)
    if sh is None:
        return
    db = get_db()
    try:
        update_dataset_steps(db, ds_id, sh.to_recipes(), sh.active_index)
        uid = (st.session_state.user or {}).get('id')
        if uid:
            set_user_last_dataset(db, uid, ds_id)
    except Exception:
        pass
    finally:
        db.close()


def _hydrate_dataset_from_db(dataset_id):
    """Rebuild session_state for a previously persisted dataset.

    Returns True on success. Used both for auto-resume on session restore
    and for the user-facing 'Reopen' action.
    """
    if not dataset_id:
        return False
    uid = (st.session_state.user or {}).get('id')
    db = get_db()
    try:
        rec = get_dataset_record(db, dataset_id, user_id=uid)
        if not rec or not rec.source_parquet or not rec.step_recipes:
            return False
        try:
            source_df = deserialize_source_df(rec.source_parquet)
        except Exception:
            return False
        history = rebuild_history_from_recipes(
            source_df, rec.step_recipes, rec.active_step_index
        )
        st.session_state.current_dataset_id = rec.id
        st.session_state.step_histories[rec.id] = history

        # Restore the dataframes the rest of the dashboard reads from.
        # Prefer a manual override step over the auto Changed Type so the
        # restored baseline matches the user's most recent typing decision.
        typed_step = history.find_last("Changed Type (manual)") or history.find_last("Changed Type")
        st.session_state.df = (typed_step.df if typed_step else source_df)

        # The cleaned dataframe lives at the last cleaning substep (or the
        # legacy single "Cleaning" step on older records). Walk the steps in
        # order so the most-recent cleaning tail wins.
        clean_step = None
        substep_states = {}
        substep_reports = []
        for s in history.steps:
            sm = s.meta or {}
            sk = sm.get('substep_key')
            if sk:
                clean_step = s
                substep_states[sk] = bool(sm.get('enabled', True))
                substep_reports.append({
                    'key': sk,
                    'label': s.name,
                    'enabled': bool(sm.get('enabled', True)),
                    'summary': s.summary,
                    'details': sm.get('details') or {},
                })
        legacy_clean = history.find_last("Cleaning")
        if clean_step is None and legacy_clean is not None:
            clean_step = legacy_clean
        st.session_state.df_cleaned = (clean_step.df if clean_step else st.session_state.df)

        # Cleaning report — rebuild from the substep tail, fall back to the
        # legacy single-step report stored in meta on older records.
        if substep_reports:
            base_rows = (typed_step.df if typed_step else source_df)
            final_rows = clean_step.df if clean_step is not None else base_rows
            st.session_state.cleaning_report = {
                'original_rows': len(base_rows),
                'original_columns': len(base_rows.columns),
                'final_rows': len(final_rows),
                'final_columns': len(final_rows.columns),
                'rows_removed': len(base_rows) - len(final_rows),
                'changes': [c for r in substep_reports
                            for c in (r['details'].get('changes') or [])],
                'substeps': substep_reports,
            }
        elif legacy_clean is not None:
            st.session_state.cleaning_report = (legacy_clean.meta or {}).get('report')

        if substep_states and 'cleaning_substep_states' in st.session_state:
            st.session_state.cleaning_substep_states[rec.id] = substep_states

        # Schema metadata used by the UI panels.
        change_step = history.find_last("Changed Type (manual)") or history.find_last("Changed Type")
        if change_step and (change_step.meta or {}).get('schema'):
            st.session_state.inferred_schema[rec.id] = change_step.meta.get('schema')
        # Re-derive overrides from any manual steps so the UI mirrors them.
        overrides = {}
        for s in history.steps:
            if s.name == "Changed Type (manual)":
                overrides.update((s.meta or {}).get('override') or {})
        st.session_state.type_overrides[rec.id] = overrides

        st.session_state.analysis_results = generate_summary_report(st.session_state.df_cleaned)

        if uid:
            set_user_last_dataset(db, uid, rec.id)
        return True
    finally:
        db.close()


def _active_df():
    """Return the dataframe at the currently active pipeline step.
    Falls back to df_cleaned -> df when no step history exists."""
    sh = _get_step_history()
    if sh and not sh.is_empty():
        cur = sh.current_df()
        if cur is not None:
            return cur
    if st.session_state.get('df_cleaned') is not None:
        return st.session_state.df_cleaned
    return st.session_state.get('df')


def _active_step_signature():
    """Stable cache-key fragment for the currently active step."""
    sh = _get_step_history()
    if sh and not sh.is_empty():
        return f"{_ds_key()}::{sh.active_index}::{sh.current().name}"
    return f"{_ds_key()}::raw"


# ── Cached wrappers (keyed by dataset id, df hashing skipped via _ prefix) ──
@st.cache_data(ttl=3600, show_spinner=False)
def _c_quality_score(_df, dataset_id):
    return get_data_quality_score(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_column_types(_df, dataset_id):
    return detect_column_types(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_missing_pct(_df, dataset_id):
    return float((_df.isnull().sum().sum() / _df.size) * 100)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_numeric_stats(_df, dataset_id):
    return get_numeric_stats(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_categorical_stats(_df, dataset_id):
    return get_categorical_stats(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_strong_correlations(_df, dataset_id):
    return find_strong_correlations(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_outliers(_df, dataset_id):
    return detect_outliers(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_distribution_overview(_df, dataset_id):
    return create_distribution_overview(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_correlation_heatmap(_df, dataset_id):
    return create_correlation_heatmap(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_missing_values_chart(_df, dataset_id):
    return create_missing_values_chart(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_categorical_insights(_df, dataset_id):
    return analyze_categorical_insights(_df)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_categorical_pie(_df, dataset_id, column):
    return create_categorical_distribution(_df, column)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_categorical_bar(_df, dataset_id, column):
    return create_categorical_bar_chart(_df, column)

@st.cache_data(ttl=3600, show_spinner=False)
def _c_outlier_viz(_df, dataset_id, column, info_tuple):
    info = dict(info_tuple)
    return create_outlier_visualization(_df, column, info)

def _section_head(title, subtitle=None, eyebrow="Section"):
    sub_html = f'<div class="dn-section-sub">{subtitle}</div>' if subtitle else ''
    st.markdown(
        f'<div class="dn-section-head">'
        f'<div class="dn-section-eyebrow">{eyebrow}</div>'
        f'<h2 class="dn-section-title">{title}</h2>{sub_html}'
        f'</div>',
        unsafe_allow_html=True,
    )

if 'similar_datasets' not in st.session_state:
    st.session_state.similar_datasets = []
if 'comparison_data' not in st.session_state:
    st.session_state.comparison_data = None


def user_to_dict(user):
    """Convert SQLAlchemy User object to dictionary to avoid DetachedInstanceError"""
    if user is None:
        return None
    return {
        'id': user.id,
        'email': user.email,
        'username': user.username,
        'full_name': user.full_name,
        'subscription_type': user.subscription_type,
        'is_admin': user.is_admin,
        'analysis_count': user.analysis_count,
        'created_at': user.created_at,
        'last_login': user.last_login,
        'phone': user.phone,
        'country': user.country,
        'gender': user.gender,
        'specialty': user.specialty,
        'specialty_other': user.specialty_other,
        'trial_start': user.trial_start,
        'trial_end': user.trial_end
    }


# ── Hydrate session from URL query-param token (preserved by browser on refresh) ──
if not st.session_state.session_hydrated and st.session_state.user is None:
    _saved_token = st.query_params.get(SESSION_QP_NAME)
    if _saved_token:
        _db = get_db()
        try:
            _db_user = get_user_by_session_token(_db, _saved_token)
            if _db_user:
                st.session_state.user = user_to_dict(_db_user)
                if st.session_state.page in ('home', 'login', 'register'):
                    st.session_state.page = 'dashboard'
                # Auto-resume the dataset the user was last working on so the
                # Applied Steps panel and dashboard render exactly where they
                # left off — even after a sign-out or browser refresh.
                _last_ds = getattr(_db_user, 'last_dataset_id', None)
                if _last_ds and st.session_state.df is None:
                    try:
                        _hydrate_dataset_from_db(_last_ds)
                    except Exception:
                        pass
            else:
                # Stale or unknown token — strip it so we don't keep retrying.
                try:
                    del st.query_params[SESSION_QP_NAME]
                except Exception:
                    pass
        finally:
            _db.close()
    st.session_state.session_hydrated = True


def get_user_limits():
    if st.session_state.user:
        user_id = st.session_state.user.get('id')
        db = get_db()
        try:
            user_obj = get_user_by_id(db, user_id)
            if user_obj and not check_trial_active(user_obj):
                return {
                    'max_rows': 0,
                    'max_analyses_per_day': 0,
                    'max_file_size_mb': 0,
                    'ai_chat_enabled': False,
                    'predictions_enabled': False,
                    'export_enabled': False,
                    'ml_enabled': False
                }
        finally:
            db.close()
        sub_type = st.session_state.user.get('subscription_type', 'tier1')
        if sub_type == 'tier3':
            return TIER3_LIMITS
        elif sub_type == 'tier2':
            return TIER2_LIMITS
        return TIER1_LIMITS
    return None


def update_user_tier(new_tier):
    """Update the current user's tier"""
    if st.session_state.user:
        user_id = st.session_state.user.get('id')
        if user_id:
            db = get_db()
            try:
                update_user_subscription(db, user_id, new_tier)
                st.session_state.user['subscription_type'] = new_tier
            finally:
                db.close()


def calculate_data_hash(df):
    columns_str = '_'.join(sorted(df.columns.tolist()))
    return hashlib.md5(columns_str.encode()).hexdigest()


_CSV_ENCODINGS = [
    'utf-8', 'utf-8-sig', 'cp1256', 'windows-1256',
    'iso-8859-6', 'utf-16', 'latin-1', 'cp1252',
]
_CSV_DELIMITERS = [',', ';', '\t', '|']
_DELIM_LABELS = {',': 'Comma (,)', ';': 'Semicolon (;)',
                 '\t': 'Tab (\\t)', '|': 'Pipe (|)'}


def _decode_bytes(file_bytes):
    """Try a list of encodings and return (text, encoding) or (None, None)."""
    for enc in _CSV_ENCODINGS:
        try:
            text = file_bytes.decode(enc)
            if '\ufffd' in text[:4096]:
                continue
            return text, enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    try:
        return file_bytes.decode('utf-8', errors='replace'), 'utf-8'
    except Exception:
        return None, None


def sniff_csv_options(file_bytes):
    """Inspect raw CSV bytes and guess encoding, delimiter, and whether the
    first row is a header. Returns a dict with confidence flags."""
    text, encoding = _decode_bytes(file_bytes)
    if not text:
        return {'encoding': 'utf-8', 'delimiter': ',', 'delimiter_confident': False,
                'has_header': True, 'header_confident': False, 'preview': '', 'error': 'decode_failed'}
    sample = text[:8192]
    delimiter = ','
    delim_confident = False
    try:
        dialect = _csv.Sniffer().sniff(sample, delimiters=''.join(_CSV_DELIMITERS))
        if dialect.delimiter in _CSV_DELIMITERS:
            delimiter = dialect.delimiter
            delim_confident = True
    except Exception:
        # Fallback: count occurrences in the first non-empty line
        first_line = next((ln for ln in sample.splitlines() if ln.strip()), '')
        counts = {d: first_line.count(d) for d in _CSV_DELIMITERS}
        delimiter = max(counts, key=counts.get) if any(counts.values()) else ','
        delim_confident = max(counts.values()) >= 2 if counts else False
    has_header = True
    header_confident = False
    try:
        has_header = _csv.Sniffer().has_header(sample)
        header_confident = True
    except Exception:
        # Heuristic: if first row has no numeric tokens, assume header
        first_line = next((ln for ln in sample.splitlines() if ln.strip()), '')
        toks = [t.strip() for t in first_line.split(delimiter)]
        numeric_toks = sum(1 for t in toks if t.replace('.', '', 1).replace(',', '').lstrip('-+').isdigit())
        has_header = numeric_toks <= max(0, len(toks) // 4)
        header_confident = False
    return {
        'encoding': encoding,
        'delimiter': delimiter,
        'delimiter_confident': delim_confident,
        'has_header': has_header,
        'header_confident': header_confident,
        'preview': '\n'.join(sample.splitlines()[:5]),
    }


def load_file(uploaded_file, delimiter=None, has_header=None, return_meta=False):
    """Load CSV or Excel file. For CSVs, optionally accept explicit delimiter
    and has_header overrides. Returns the DataFrame, or (df, meta) if
    return_meta is True. meta includes the parser settings actually used."""
    meta = {'kind': None, 'encoding': None, 'delimiter': None, 'has_header': None,
            'sheet_name': None}
    try:
        name = uploaded_file.name.lower()
        if name.endswith('.csv'):
            file_bytes = uploaded_file.read()
            sniff = sniff_csv_options(file_bytes)
            chosen_delim = delimiter if delimiter else sniff['delimiter']
            chosen_header = has_header if has_header is not None else sniff['has_header']
            chosen_encoding = sniff['encoding'] or 'utf-8'
            df = None
            last_error = None
            encodings_to_try = [chosen_encoding] + [e for e in _CSV_ENCODINGS if e != chosen_encoding]
            for enc in encodings_to_try:
                try:
                    df = pd.read_csv(
                        io.BytesIO(file_bytes), encoding=enc,
                        sep=chosen_delim, header=0 if chosen_header else None,
                        engine='python',
                    )
                    if df.empty or len(df.columns) == 0:
                        continue
                    col_text = ''.join(str(c) for c in df.columns)
                    if '\ufffd' in col_text or '?' * 5 in col_text:
                        continue
                    chosen_encoding = enc
                    break
                except Exception as e:
                    last_error = e
                    df = None
                    continue
            if df is None or df.empty:
                st.error("Could not read file with any supported encoding. "
                         "The file may be corrupted or use an unsupported format.")
                return (None, meta) if return_meta else None
            if not chosen_header:
                df.columns = [f"Column_{i+1}" for i in range(len(df.columns))]
            meta.update(kind='csv', encoding=chosen_encoding,
                        delimiter=chosen_delim, has_header=bool(chosen_header))
            return (df, meta) if return_meta else df

        elif name.endswith(('.xlsx', '.xls')):
            header_arg = 0 if (has_header is None or has_header) else None
            df = pd.read_excel(uploaded_file, header=header_arg)
            if has_header is False:
                df.columns = [f"Column_{i+1}" for i in range(len(df.columns))]
            meta.update(kind='excel', has_header=(header_arg == 0))
            return (df, meta) if return_meta else df
        else:
            st.error("Unsupported file type. Please upload a CSV or Excel file.")
            return (None, meta) if return_meta else None

    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return (None, meta) if return_meta else None


def _render_auth_chrome(logo_b64, action_label="Home", action_href="/"):
    """Render the shared navbar + atmospheric background + auth CSS for auth pages."""
    st.markdown(f'''
<div class="lp-nav"><div class="lp-nav-inner">
<a class="lp-nav-logo" href="/" target="_self"><img src="data:image/png;base64,{logo_b64}" alt="DataVision Pro"></a>
<div class="lp-nav-links">
<a class="lp-nav-link" href="/" target="_self">Home</a>
<a class="lp-nav-link" href="/#features" target="_self">Features</a>
<a class="lp-nav-link" href="/#pricing" target="_self">Pricing</a>
<a class="lp-nav-link" href="/#contact" target="_self">Contact</a>
</div>
<div class="lp-nav-actions">
<a class="lp-nav-signin-link" href="{action_href}" target="_self">{action_label}</a>
</div>
</div></div>
<div class="lp-nav-spacer"></div>
''', unsafe_allow_html=True)

    st.markdown(f'''
<style>
/* ── Auth page background atmosphere ──────────────────────── */
[data-testid="stAppViewContainer"] > .main {{ position: relative; }}
.auth-bg-grid {{
    position: fixed; inset: 0; z-index: 0; pointer-events: none; opacity: 0.55;
    background-image:
        linear-gradient(rgba(45,212,191,0.05) 1px, transparent 1px),
        linear-gradient(90deg, rgba(45,212,191,0.05) 1px, transparent 1px);
    background-size: 56px 56px;
    mask-image: radial-gradient(ellipse 55% 45% at 50% 35%, black 25%, transparent 75%);
    -webkit-mask-image: radial-gradient(ellipse 55% 45% at 50% 35%, black 25%, transparent 75%);
}}
.auth-bg-glow {{
    position: fixed; top: -8%; left: 50%; transform: translateX(-50%);
    width: 720px; height: 520px; z-index: 0; pointer-events: none;
    background: radial-gradient(circle, rgba(45,212,191,0.13) 0%, transparent 60%);
    filter: blur(50px);
}}
.auth-corner-mono {{
    position: fixed; font-family: 'JetBrains Mono', monospace;
    font-size: 0.68rem; color: rgba(148,163,184,0.18); letter-spacing: 0.18em;
    z-index: 1; pointer-events: none;
}}
.auth-corner-tl {{ top: 1.4rem; left: 1.5rem; }}
.auth-corner-br {{ bottom: 1.4rem; right: 1.5rem; }}

/* ── Desktop layout container ─────────────────────────────── */
.block-container {{ padding-top: 1.5rem !important; padding-bottom: 0 !important; max-width: 1320px !important; position: relative; z-index: 5; }}

/* ── Two-column hero/form layout ──────────────────────────── */
.auth-twocol {{ display: grid; grid-template-columns: 1.05fr 1fr; gap: 4rem; align-items: center; min-height: 70vh; padding: 1rem 0 4rem 0; }}
@media (max-width: 900px) {{ .auth-twocol {{ grid-template-columns: 1fr; gap: 2rem; }} }}

/* ── LEFT brand pane ──────────────────────────────────────── */
.auth-brand-pane {{ padding-right: 1rem; }}
.auth-brand-eyebrow {{
    display: inline-flex; align-items: center; gap: 0.6rem;
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--teal); margin-bottom: 1.4rem;
    padding: 0.4rem 0.85rem; border: 1px solid rgba(45,212,191,0.2);
    border-radius: 100px; background: rgba(45,212,191,0.04);
}}
.auth-brand-eyebrow::before {{
    content: ''; display: inline-block; width: 6px; height: 6px;
    border-radius: 50%; background: var(--teal); box-shadow: 0 0 8px var(--teal);
}}
.auth-brand-headline {{
    font-family: 'Syne', sans-serif; font-size: 3.25rem; font-weight: 800;
    letter-spacing: -0.035em; line-height: 1.05; margin: 0 0 1.25rem 0;
    background: linear-gradient(135deg, #ffffff 0%, #2dd4bf 75%, #94a3b8 130%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}}
.auth-brand-sub {{
    font-size: 1.05rem; color: var(--text-secondary); line-height: 1.65;
    max-width: 460px; margin: 0 0 2.25rem 0;
}}
.auth-brand-features {{ display: flex; flex-direction: column; gap: 1rem; max-width: 440px; }}
.auth-brand-feat {{ display: flex; align-items: flex-start; gap: 0.95rem; }}
.auth-brand-feat-icon {{
    width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0;
    background: rgba(45,212,191,0.08); border: 1px solid rgba(45,212,191,0.2);
    display: flex; align-items: center; justify-content: center;
    color: var(--teal); font-weight: 700; font-family: 'JetBrains Mono', monospace; font-size: 0.85rem;
}}
.auth-brand-feat-body strong {{ font-family: 'Syne', sans-serif; font-weight: 700; color: var(--text-primary); font-size: 0.98rem; display: block; margin-bottom: 0.15rem; }}
.auth-brand-feat-body span {{ font-size: 0.85rem; color: var(--text-muted); line-height: 1.5; }}

/* ── Eyebrow above form ───────────────────────────────────── */
.auth-eyebrow {{
    text-align: center; font-family: 'JetBrains Mono', monospace;
    font-size: 0.7rem; letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--teal); margin: 0 0 0.85rem 0; opacity: 0.85;
}}
.auth-eyebrow span::before, .auth-eyebrow span::after {{
    content: ''; display: inline-block; width: 22px; height: 1px;
    background: rgba(45,212,191,0.4); vertical-align: middle; margin: 0 0.7rem;
}}
.auth-headline {{
    text-align: center; margin-bottom: 1.85rem;
}}
.auth-headline h1 {{
    font-family: 'Syne', sans-serif;
    font-size: 2.25rem; font-weight: 800;
    letter-spacing: -0.025em; line-height: 1.05;
    background: linear-gradient(135deg, #ffffff 0%, #2dd4bf 115%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin: 0 0 0.55rem 0;
}}
.auth-headline p {{
    font-size: 0.92rem; color: var(--text-secondary);
    margin: 0; line-height: 1.55;
}}

/* ── Card via stForm styling ──────────────────────────────── */
[data-testid="stForm"] {{
    background: linear-gradient(160deg, rgba(17,31,53,0.88) 0%, rgba(12,24,41,0.92) 100%) !important;
    border: 1px solid rgba(45,212,191,0.14) !important;
    border-radius: 20px !important;
    padding: 2.25rem 2rem 2rem 2rem !important;
    backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
    box-shadow: 0 30px 80px rgba(0,0,0,0.4), 0 1px 0 rgba(45,212,191,0.08) inset !important;
    position: relative; overflow: hidden;
}}
[data-testid="stForm"]::before {{
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(45,212,191,0.55), transparent);
}}

/* ── Form input refinement ────────────────────────────────── */
[data-testid="stForm"] [data-testid="stTextInput"] label p,
[data-testid="stForm"] [data-testid="stTextInput"] label {{
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem !important; font-weight: 500 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    color: var(--text-secondary) !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] input {{
    background: #ffffff !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    padding: 0.9rem 1rem !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important;
    color: #07101f !important;
    transition: border-color 0.18s, box-shadow 0.18s !important;
    -webkit-text-fill-color: #07101f !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] input:focus {{
    border-color: rgba(45,212,191,0.65) !important;
    box-shadow: 0 0 0 3px rgba(45,212,191,0.18) !important;
    outline: none !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] input::placeholder {{
    color: rgba(7,16,31,0.38) !important;
    opacity: 1 !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] [data-testid="stTextInputContainer"],
[data-testid="stForm"] [data-testid="stTextInput"] > div > div {{
    background: #ffffff !important;
    border-radius: 10px !important;
}}
/* Password reveal button styling */
[data-testid="stForm"] [data-testid="stTextInput"] button {{
    background: #ffffff !important;
    color: #64748b !important;
    border-left: 1px solid rgba(0,0,0,0.06) !important;
}}
[data-testid="stForm"] [data-testid="stTextInput"] button:hover {{
    color: #07101f !important;
    background: #f1f5f9 !important;
}}

/* ── Primary submit button ────────────────────────────────── */
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button {{
    background: linear-gradient(135deg, #2dd4bf 0%, #14b8a6 100%) !important;
    color: #07101f !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 0.85rem 1rem !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important; font-weight: 700 !important;
    letter-spacing: 0.01em !important;
    box-shadow: 0 8px 24px rgba(45,212,191,0.28) !important;
    transition: transform 0.15s, box-shadow 0.15s, filter 0.15s !important;
    margin-top: 0.6rem !important;
}}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover {{
    transform: translateY(-1px) !important;
    box-shadow: 0 12px 32px rgba(45,212,191,0.4) !important;
    filter: brightness(1.05) !important;
}}
[data-testid="stForm"] [data-testid="stFormSubmitButton"] button p {{
    font-weight: 700 !important; color: #07101f !important; font-size: 0.95rem !important;
}}

/* ── Forgot password row inside form ──────────────────────── */
.auth-aux-row {{
    display: flex; justify-content: flex-end;
    margin: -0.5rem 0 0.4rem 0;
}}
.auth-aux-link {{
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    color: var(--text-muted) !important; text-decoration: none !important;
    letter-spacing: 0.05em;
}}
.auth-aux-link:hover {{ color: var(--teal) !important; }}

/* ── Divider + secondary action OUTSIDE form ──────────────── */
.auth-divider {{
    display: flex; align-items: center; gap: 0.85rem;
    margin: 1.75rem auto 1.1rem auto;
    font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
    color: var(--text-muted); letter-spacing: 0.22em;
}}
.auth-divider::before, .auth-divider::after {{
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.08), transparent);
}}
.auth-foot-text {{
    text-align: center; font-size: 0.88rem; color: var(--text-secondary);
    margin: 0 0 0.85rem 0;
}}

/* ── Secondary "Create Account" button (outside form) ────── */
.stButton > button[kind="secondary"], .stButton > button {{
    background: transparent !important;
    color: var(--text-primary) !important;
    border: 1px solid rgba(45,212,191,0.28) !important;
    border-radius: 10px !important;
    padding: 0.78rem 1rem !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important; font-weight: 500 !important;
    transition: background 0.15s, border-color 0.15s, color 0.15s !important;
    box-shadow: none !important;
}}
.stButton > button:hover {{
    background: rgba(45,212,191,0.07) !important;
    border-color: rgba(45,212,191,0.55) !important;
    color: var(--teal) !important;
}}
.stButton > button p {{ color: inherit !important; font-weight: 500 !important; }}

/* ── Trust strip ──────────────────────────────────────────── */
.auth-trust {{
    text-align: center; margin: 2rem 0 1rem 0;
    font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
    color: var(--text-muted); letter-spacing: 0.14em;
}}
.auth-trust span {{ display: inline-block; margin: 0 0.4rem; }}
.auth-trust .dot {{ color: var(--teal); opacity: 0.55; }}

/* Hide error/warning default Streamlit chrome inside form */
[data-testid="stForm"] [data-testid="stAlert"] {{
    background: rgba(239,68,68,0.08) !important;
    border: 1px solid rgba(239,68,68,0.25) !important;
    border-radius: 8px !important;
}}
</style>
<div class="auth-bg-grid"></div>
<div class="auth-bg-glow"></div>
''', unsafe_allow_html=True)


def show_login_page():
    if st.session_state.user:
        st.session_state.page = 'dashboard'
        st.rerun()
        return

    logo_b64 = get_logo_base64()
    _render_auth_chrome(logo_b64, action_label="Home", action_href="/")

    # ── 2-COLUMN DESKTOP LAYOUT ─────────────────────────────────────────────
    col_left, col_right = st.columns([1.05, 1], gap="large")

    with col_left:
        st.markdown('''
<div class="auth-brand-pane">
<div class="auth-brand-eyebrow">Welcome Back</div>
<h1 class="auth-brand-headline">Sign in. See your data come alive.</h1>
<p class="auth-brand-sub">Pick up exactly where you left off &mdash; your datasets, AI conversations, and saved analyses are one click away.</p>
<div class="auth-brand-features">
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">01</div>
<div class="auth-brand-feat-body"><strong>Persistent Workspaces</strong><span>Every dataset, chart, and chat thread is saved to your account.</span></div>
</div>
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">02</div>
<div class="auth-brand-feat-body"><strong>Bank-Grade Security</strong><span>Bcrypt-hashed credentials. End-to-end encrypted sessions.</span></div>
</div>
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">03</div>
<div class="auth-brand-feat-body"><strong>Instant Access</strong><span>Your full Tier 3 trial unlocks the moment you sign in.</span></div>
</div>
</div>
</div>
''', unsafe_allow_html=True)

    with col_right:
        st.markdown('''
<div class="auth-eyebrow"><span>Secure Sign In</span></div>
<div class="auth-headline">
<h1>Sign In to Your Account</h1>
<p>Enter your credentials to continue.</p>
</div>
''', unsafe_allow_html=True)

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email Address", placeholder="you@company.com", key="login_email")
            password = st.text_input("Password", type="password", placeholder="Enter your password", key="login_password")
            st.markdown('<div class="auth-aux-row"><a class="auth-aux-link" href="mailto:muayad.demaidi.work@gmail.com?subject=Password%20Reset%20Request">Forgot password?</a></div>', unsafe_allow_html=True)
            submit = st.form_submit_button("Sign In \u2192", use_container_width=True)

            if submit:
                if email and password:
                    db = get_db()
                    try:
                        user = authenticate_user(db, email, password)
                        if user:
                            _tok = issue_session_token(db, user, days=30)
                            st.session_state.user = user_to_dict(user)
                            st.session_state.page = 'dashboard'
                            st.query_params[SESSION_QP_NAME] = _tok
                        else:
                            st.error("Invalid email or password")
                    finally:
                        db.close()
                else:
                    st.warning("Please enter both email and password")

        if st.session_state.user and st.session_state.page == 'dashboard':
            st.rerun()

        st.markdown('<div class="auth-divider">NEW HERE</div>', unsafe_allow_html=True)
        st.markdown('<p class="auth-foot-text">Don&#39;t have an account yet? Start your 60-day free trial.</p>', unsafe_allow_html=True)

        if st.button("Create Account \u2192", use_container_width=True, key="login_to_register"):
            st.session_state.page = 'register'
            st.rerun()

        st.markdown('''
<div class="auth-trust">
<span>ENCRYPTED</span><span class="dot">\u00b7</span><span>BCRYPT HASHING</span><span class="dot">\u00b7</span><span>GDPR-ALIGNED</span>
</div>
''', unsafe_allow_html=True)

    # ── FOOTER (same as landing) ────────────────────────────────────────────
    st.markdown(f'''
<div class="lp-footer">
<div class="lp-footer-inner">
<div>
<img src="data:image/png;base64,{logo_b64}" style="height:60px;width:auto;border-radius:6px;" alt="DataVision Pro">
<p class="lp-footer-brand-desc">An intelligent data analytics platform that turns raw datasets into clear, actionable insights &mdash; in seconds, no code required.</p>
</div>
<div>
<div class="lp-footer-col-title">Platform</div>
<ul class="lp-footer-links-list">
<li><a href="/" target="_self">Home</a></li>
<li><a href="/#features" target="_self">Features</a></li>
<li><a href="/#pricing" target="_self">Pricing &amp; Plans</a></li>
<li><a href="/#how" target="_self">How It Works</a></li>
</ul>
</div>
<div>
<div class="lp-footer-col-title">Support</div>
<ul class="lp-footer-links-list">
<li><a href="/#contact" target="_self">Contact Us</a></li>
<li><a href="mailto:muayad.demaidi.work@gmail.com">Account Help</a></li>
<li><a href="mailto:muayad.demaidi.work@gmail.com">Report an Issue</a></li>
<li><a href="/" target="_self">60-Day Free Trial</a></li>
</ul>
</div>
</div>
<div class="lp-footer-bottom">
<span class="lp-footer-copy">&copy; 2026 DataVision Pro. All rights reserved.</span>
<span class="lp-footer-status">All systems operational</span>
</div>
</div>
''', unsafe_allow_html=True)


def show_register_page():
    if st.session_state.user:
        st.session_state.page = 'dashboard'
        st.rerun()
        return

    logo_b64 = get_logo_base64()
    _render_auth_chrome(logo_b64, action_label="Sign In", action_href="?signin=1")

    # ── REGISTER-SPECIFIC STYLES (white selectboxes + tighter form) ─────────
    st.markdown('''
<style>
[data-testid="stForm"] [data-testid="stSelectbox"] label,
[data-testid="stForm"] [data-testid="stSelectbox"] label p {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem !important; font-weight: 500 !important;
    letter-spacing: 0.1em !important; text-transform: uppercase !important;
    color: var(--text-secondary) !important;
}
/* ── Selectbox: white outer pill matching text inputs ───── */
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1px solid rgba(255,255,255,0.12) !important;
    border-radius: 10px !important;
    min-height: 49.5px !important;
    height: 49.5px !important;
    padding: 0 0.5rem 0 1rem !important;
    box-shadow: none !important;
    cursor: pointer !important;
    transition: border-color 0.18s, box-shadow 0.18s !important;
}
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:hover {
    border-color: rgba(45,212,191,0.4) !important;
}
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within {
    border-color: rgba(45,212,191,0.65) !important;
    box-shadow: 0 0 0 3px rgba(45,212,191,0.18) !important;
}
/* Strip every inner descendant — bg, borders, shadows, decorations */
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div *,
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div *::before,
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div *::after {
    background: transparent !important;
    background-color: transparent !important;
    border: 0 !important;
    border-bottom: 0 !important;
    border-top: 0 !important;
    border-left: 0 !important;
    border-right: 0 !important;
    box-shadow: none !important;
    outline: none !important;
    text-decoration: none !important;
    border-image: none !important;
    cursor: pointer !important;
}
/* Force solid dark text on the chosen value AND placeholder */
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div *,
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] [data-baseweb="select-input-container"],
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] input {
    color: #07101f !important;
    -webkit-text-fill-color: #07101f !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important;
    line-height: 1.4 !important;
    caret-color: transparent !important;
    -webkit-caret-color: transparent !important;
}
/* The hidden search input baseweb adds — neutralize its visual + text caret */
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] input {
    padding: 0 !important;
    margin: 0 !important;
}
/* Container divs reset to zero padding so text aligns with text inputs */
[data-testid="stForm"] [data-testid="stSelectbox"] [data-baseweb="select"] > div > div {
    padding: 0 !important;
}
/* Chevron icon */
[data-testid="stForm"] [data-testid="stSelectbox"] svg {
    fill: #64748b !important; color: #64748b !important; cursor: pointer !important;
}

/* ── Selectbox dropdown menu (popover, rendered at body level) ── */
[data-baseweb="popover"] [data-baseweb="menu"],
[data-baseweb="popover"] ul[role="listbox"] {
    background: #ffffff !important;
    border: 1px solid rgba(45,212,191,0.25) !important;
    border-radius: 10px !important;
    box-shadow: 0 14px 40px rgba(0,0,0,0.35) !important;
    padding: 4px !important;
}
[data-baseweb="popover"] [role="option"],
[data-baseweb="popover"] li[role="option"] {
    background: transparent !important;
    color: #07101f !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.92rem !important;
    padding: 0.55rem 0.75rem !important;
    border-radius: 6px !important;
}
[data-baseweb="popover"] [role="option"] *,
[data-baseweb="popover"] li[role="option"] * {
    color: #07101f !important;
    -webkit-text-fill-color: #07101f !important;
    background: transparent !important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] li[role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"],
[data-baseweb="popover"] li[role="option"][aria-selected="true"] {
    background: rgba(45,212,191,0.12) !important;
    color: #0f766e !important;
}
[data-baseweb="popover"] [role="option"]:hover *,
[data-baseweb="popover"] li[role="option"]:hover * {
    color: #0f766e !important;
    -webkit-text-fill-color: #0f766e !important;
}

.auth-form-section {
    font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
    letter-spacing: 0.18em; text-transform: uppercase;
    color: var(--teal); margin: 1.1rem 0 0.85rem 0;
    display: flex; align-items: center; gap: 0.85rem;
}
.auth-form-section::after {
    content: ''; flex: 1; height: 1px;
    background: linear-gradient(90deg, rgba(45,212,191,0.25), transparent);
}
.auth-form-section:first-of-type { margin-top: 0; }

/* Tighter form for register (more fields) */
[data-testid="stForm"] [data-testid="stTextInput"] { margin-bottom: 0.35rem !important; }
[data-testid="stForm"] [data-testid="stSelectbox"] { margin-bottom: 0.35rem !important; }
</style>
''', unsafe_allow_html=True)

    # ── 2-COLUMN LAYOUT ─────────────────────────────────────────────────────
    col_left, col_right = st.columns([0.95, 1.15], gap="large")

    with col_left:
        st.markdown('''
<div class="auth-brand-pane">
  <div class="auth-brand-eyebrow">START FREE · 60-DAY TRIAL</div>
  <h1 class="auth-brand-headline">Create your account.<br>Start in 60&nbsp;seconds.</h1>
  <p class="auth-brand-sub">No credit card. No commitment. Just data analytics that thinks alongside you — built for analysts, founders, and operators who want answers, not dashboards.</p>
  <div class="auth-brand-features">
    <div class="auth-brand-feat">
      <div class="auth-brand-feat-icon">01</div>
      <div class="auth-brand-feat-body">
        <strong>60-Day Free Trial</strong>
        <span>Full Tier 3 access from day one — every feature unlocked.</span>
      </div>
    </div>
    <div class="auth-brand-feat">
      <div class="auth-brand-feat-icon">02</div>
      <div class="auth-brand-feat-body">
        <strong>Up to 1M Rows per File</strong>
        <span>Upload CSV or Excel up to 200&nbsp;MB. Auto-cleaned on arrival.</span>
      </div>
    </div>
    <div class="auth-brand-feat">
      <div class="auth-brand-feat-icon">03</div>
      <div class="auth-brand-feat-body">
        <strong>AI Chat &amp; ML Insights</strong>
        <span>GPT-driven analysis, predictions, clustering — included.</span>
      </div>
    </div>
  </div>
</div>
''', unsafe_allow_html=True)

    with col_right:
        st.markdown('''
<div class="auth-eyebrow"><span>CREATE ACCOUNT</span></div>
<div class="auth-headline">
  <h1>Start your 60-day trial</h1>
  <p>It takes less than a minute. We'll never share your details.</p>
</div>
''', unsafe_allow_html=True)

        COUNTRIES = [
            "Select Country", "Afghanistan", "Albania", "Algeria", "Argentina", "Australia", "Austria",
            "Bahrain", "Bangladesh", "Belgium", "Brazil", "Canada", "Chile", "China", "Colombia",
            "Croatia", "Czech Republic", "Denmark", "Egypt", "Estonia", "Ethiopia", "Finland",
            "France", "Germany", "Ghana", "Greece", "Hungary", "Iceland", "India", "Indonesia",
            "Iran", "Iraq", "Ireland", "Israel", "Italy", "Jamaica", "Japan", "Jordan", "Kazakhstan",
            "Kenya", "Kuwait", "Latvia", "Lebanon", "Libya", "Lithuania", "Luxembourg", "Malaysia",
            "Mexico", "Morocco", "Netherlands", "New Zealand", "Nigeria", "Norway", "Oman",
            "Pakistan", "Palestine", "Panama", "Peru", "Philippines", "Poland", "Portugal", "Qatar",
            "Romania", "Russia", "Saudi Arabia", "Serbia", "Singapore", "Slovakia", "Slovenia",
            "South Africa", "South Korea", "Spain", "Sri Lanka", "Sudan", "Sweden", "Switzerland",
            "Syria", "Taiwan", "Thailand", "Tunisia", "Turkey", "UAE", "Uganda", "Ukraine",
            "United Kingdom", "United States", "Uruguay", "Venezuela", "Vietnam", "Yemen", "Other"
        ]

        SPECIALTIES = [
            "Select Specialty",
            "Data Science & Analytics", "Business & Management", "Marketing & Advertising",
            "Engineering & Technical", "Finance & Accounting", "Healthcare & Medicine",
            "Education & Academia", "IT & Software Development", "Research & Scientific",
            "Government & Public Sector", "Legal & Compliance", "Media & Communications",
            "Human Resources", "Supply Chain & Logistics", "Real Estate",
            "Retail & E-Commerce", "Consulting", "Non-Profit & NGO", "Student", "Other"
        ]

        with st.form("register_form"):
            st.markdown('<div class="auth-form-section">PERSONAL · 01</div>', unsafe_allow_html=True)
            full_name = st.text_input("Full Name", placeholder="Enter your full name")

            r1c1, r1c2 = st.columns(2)
            with r1c1:
                email = st.text_input("Email Address", placeholder="you@company.com")
            with r1c2:
                phone = st.text_input("Phone Number", placeholder="+1 234 567 8900")

            r2c1, r2c2 = st.columns(2)
            with r2c1:
                username = st.text_input("Username", placeholder="Choose a username")
            with r2c2:
                gender = st.selectbox("Gender", ["Select Gender", "Male", "Female"])

            st.markdown('<div class="auth-form-section">PROFILE · 02</div>', unsafe_allow_html=True)
            r3c1, r3c2 = st.columns(2)
            with r3c1:
                country = st.selectbox("Country", COUNTRIES)
            with r3c2:
                specialty = st.selectbox("Specialty", SPECIALTIES)

            specialty_other_val = ""
            if specialty == "Other":
                specialty_other_val = st.text_input("Please Specify", placeholder="Enter your specialty")

            st.markdown('<div class="auth-form-section">SECURITY · 03</div>', unsafe_allow_html=True)
            p1, p2 = st.columns(2)
            with p1:
                password = st.text_input("Password", type="password", placeholder="Min 6 characters")
            with p2:
                confirm_password = st.text_input("Confirm Password", type="password", placeholder="Re-enter password")

            submit = st.form_submit_button("Create Account & Start 60-Day Trial  →", use_container_width=True)

            if submit:
                if not all([full_name, username, email, password, confirm_password, phone]):
                    st.warning("Please fill in all required fields")
                elif country == "Select Country":
                    st.warning("Please select your country")
                elif gender == "Select Gender":
                    st.warning("Please select your gender")
                elif specialty == "Select Specialty":
                    st.warning("Please select your specialty")
                elif specialty == "Other" and not specialty_other_val:
                    st.warning("Please specify your specialty")
                elif password != confirm_password:
                    st.error("Passwords do not match")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    db = get_db()
                    try:
                        user = create_user(
                            db, email, username, password, full_name,
                            phone=phone, country=country, gender=gender,
                            specialty=specialty,
                            specialty_other=specialty_other_val if specialty == "Other" else None
                        )
                        if user:
                            _tok = issue_session_token(db, user, days=30)
                            st.session_state.user = user_to_dict(user)
                            st.session_state.page = 'dashboard'
                            st.query_params[SESSION_QP_NAME] = _tok
                            try:
                                send_welcome_email(email, full_name, user.trial_end)
                            except Exception as e:
                                print(f"Email sending failed: {e}")
                        else:
                            st.error("Email or username already exists")
                    finally:
                        db.close()

        if st.session_state.user and st.session_state.page == 'dashboard':
            st.success("Account created successfully! Your 60-day free trial has started. Check your email for details.")
            st.rerun()

        st.markdown('<div class="auth-divider"><span>ALREADY A MEMBER</span></div>', unsafe_allow_html=True)
        st.markdown('<p class="auth-foot-text">Sign in to access your saved datasets and analyses.</p>', unsafe_allow_html=True)
        if st.button("Sign In to Existing Account  →", use_container_width=True, key="reg_to_login"):
            st.session_state.page = 'login'
            st.rerun()

        st.markdown('''
<div class="auth-trust">
  <span>● 60-DAY TRIAL</span><span class="dot">·</span>
  <span>NO CREDIT CARD</span><span class="dot">·</span>
  <span>BCRYPT SECURED</span><span class="dot">·</span>
  <span>GDPR READY</span>
</div>
''', unsafe_allow_html=True)

    # ── FOOTER (same as landing) ────────────────────────────────────────────
    st.markdown(f'''
<div class="lp-footer"><div class="lp-footer-inner">
<div class="lp-footer-grid">
<div class="lp-footer-brand">
<a class="lp-footer-logo" href="/" target="_self"><img src="data:image/png;base64,{logo_b64}" alt="DataVision Pro"></a>
<p class="lp-footer-desc">Intelligent data analytics for teams who want answers, not dashboards. AI-powered insights from upload to action.</p>
</div>
<div class="lp-footer-col">
<div class="lp-footer-col-title">PLATFORM</div>
<a class="lp-footer-link" href="/#features" target="_self">Features</a>
<a class="lp-footer-link" href="/#how" target="_self">How It Works</a>
<a class="lp-footer-link" href="/#pricing" target="_self">Pricing</a>
<a class="lp-footer-link" href="?signin=1" target="_self">Sign In</a>
</div>
<div class="lp-footer-col">
<div class="lp-footer-col-title">SUPPORT</div>
<a class="lp-footer-link" href="/#contact" target="_self">Contact Us</a>
<a class="lp-footer-link" href="mailto:muayad.demaidi.work@gmail.com">Email Support</a>
<a class="lp-footer-link" href="/#contact" target="_self">Help Center</a>
</div>
</div>
<div class="lp-footer-bottom">
<div class="lp-footer-copy">© 2026 DataVision Pro · All systems operational</div>
<div class="lp-footer-pulse"><span class="lp-pulse-dot"></span>STATUS · LIVE</div>
</div>
</div></div>
''', unsafe_allow_html=True)


def show_pricing_page():
    st.markdown('<h2 class="glow-text" style="font-size: 2.5rem;">Available Tiers</h2>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Explore our feature tiers for data analytics</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="pricing-card">
            <div class="pricing-title">Tier 1</div>
            <div class="pricing-price" style="font-size: 1.5rem;">Basic</div>
            <div class="pricing-period">Essential Features</div>
            <div class="feature-list">
                <div class="feature-item included">✓ Upload up to 50MB files</div>
                <div class="feature-item included">✓ Analyze up to 10,000 rows</div>
                <div class="feature-item included">✓ Basic visualizations</div>
                <div class="feature-item included">✓ Auto data cleaning</div>
                <div class="feature-item included">✓ Statistical overview</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="pricing-card premium">
            <div class="pricing-title">Tier 2</div>
            <div class="pricing-price" style="font-size: 1.5rem;">Advanced</div>
            <div class="pricing-period">Enhanced Analytics</div>
            <div class="feature-list">
                <div class="feature-item included">✓ Everything in Tier 1</div>
                <div class="feature-item included">✓ Upload up to 200MB files</div>
                <div class="feature-item included">✓ Up to 1M rows</div>
                <div class="feature-item included">✓ Advanced visualizations</div>
                <div class="feature-item included">✓ Predictions & Forecasting</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="pricing-card">
            <div class="pricing-title">Tier 3</div>
            <div class="pricing-price" style="font-size: 1.5rem;">Pro</div>
            <div class="pricing-period">Full Power</div>
            <div class="feature-list">
                <div class="feature-item included">✓ Everything in Tier 2</div>
                <div class="feature-item included">✓ AI Chat Assistant</div>
                <div class="feature-item included">✓ ML & Clustering</div>
                <div class="feature-item included">✓ Export Reports</div>
                <div class="feature-item included">✓ Priority Support</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    if st.session_state.user:
        current_tier = st.session_state.user.get('subscription_type', 'tier1')
        st.markdown(f'<p style="text-align: center; color: #14b8a6; font-weight: 600;">Currently on: {current_tier.upper()}</p>', unsafe_allow_html=True)
        st.markdown('<p style="text-align: center; color: #94a3b8;">Select any tier below - all features are free!</p>', unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            btn_style1 = "primary" if current_tier == 'tier1' else "secondary"
            if st.button("🔹 Select Tier 1", use_container_width=True, type=btn_style1):
                update_user_tier('tier1')
                st.success("Switched to Tier 1!")
                st.rerun()
        with col2:
            btn_style2 = "primary" if current_tier == 'tier2' else "secondary"
            if st.button("📈 Select Tier 2", use_container_width=True, type=btn_style2):
                update_user_tier('tier2')
                st.success("Switched to Tier 2!")
                st.rerun()
        with col3:
            btn_style3 = "primary" if current_tier == 'tier3' else "secondary"
            if st.button("⭐ Select Tier 3", use_container_width=True, type=btn_style3):
                update_user_tier('tier3')
                st.success("Switched to Tier 3!")
                st.rerun()
        
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("← Back to Dashboard", use_container_width=True):
            st.session_state.page = 'dashboard'
            st.rerun()
    else:
        st.markdown('<p style="text-align: center; color: #94a3b8;">All features are currently available for testing. Create an account to select your tier!</p>', unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 Create Account", use_container_width=True, type="primary"):
                st.session_state.page = 'register'
                st.rerun()
        with col2:
            if st.button("← Back to Home", use_container_width=True):
                st.session_state.page = 'home'
                st.rerun()


def show_admin_panel():
    st.markdown('<h2 class="glow-text" style="font-size: 2.5rem;">Admin Dashboard</h2>', unsafe_allow_html=True)
    
    db = get_db()
    try:
        stats = get_admin_stats(db)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">👥</div>
                <div class="admin-stat-value">{stats['total_users']}</div>
                <div class="admin-stat-label">Total Users</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">⭐</div>
                <div class="admin-stat-value">{stats['premium_users']}</div>
                <div class="admin-stat-label">Tier 2+</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">📊</div>
                <div class="admin-stat-value">{stats['total_datasets']}</div>
                <div class="admin-stat-label">Datasets</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">🔬</div>
                <div class="admin-stat-value">{stats['total_analyses']}</div>
                <div class="admin-stat-label">Analyses</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        admin_tabs = st.tabs(["👥 Users", "📊 Datasets", "💬 Conversations"])
        
        with admin_tabs[0]:
            st.subheader("User Management")
            users = get_all_users(db)
            if users:
                users_data = []
                for u in users:
                    users_data.append({
                        'ID': u.id,
                        'Name': u.full_name or u.username,
                        'Email': u.email,
                        'Plan': '⭐ Tier 3' if u.subscription_type == 'tier3' else ('📈 Tier 2' if u.subscription_type == 'tier2' else '🔹 Tier 1'),
                        'Analyses': u.analysis_count or 0,
                        'Joined': u.created_at.strftime('%Y-%m-%d') if u.created_at else '-',
                        'Last Login': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '-'
                    })
                st.dataframe(pd.DataFrame(users_data), use_container_width=True)
            else:
                st.info("No users registered yet")
        
        with admin_tabs[1]:
            st.subheader("Dataset Analytics")
            datasets = get_all_datasets(db)
            if datasets:
                datasets_data = []
                for d in datasets:
                    datasets_data.append({
                        'ID': d.id,
                        'Filename': d.filename,
                        'Dataset Name': d.dataset_name,
                        'Rows': f"{d.row_count:,}",
                        'Columns': d.column_count,
                        'Period': f"{d.period_month}/{d.period_year}" if d.period_month else '-',
                        'Uploaded': d.upload_date.strftime('%Y-%m-%d %H:%M') if d.upload_date else '-'
                    })
                st.dataframe(pd.DataFrame(datasets_data), use_container_width=True)
                
                st.subheader("📈 Statistics Overview")
                if datasets:
                    total_rows = sum(d.row_count for d in datasets)
                    avg_rows = total_rows / len(datasets)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Rows Processed", f"{total_rows:,}")
                    with col2:
                        st.metric("Average Rows/Dataset", f"{avg_rows:,.0f}")
                    with col3:
                        st.metric("Largest Dataset", f"{max(d.row_count for d in datasets):,} rows")
            else:
                st.info("No datasets uploaded yet")
        
        with admin_tabs[2]:
            st.subheader("Conversation History")
            chats = get_chat_history(db, limit=100)
            if chats:
                for chat in chats[:20]:
                    with st.expander(f"💬 {chat.user_message[:50]}..." if len(chat.user_message) > 50 else f"💬 {chat.user_message}"):
                        st.write(f"**Question:** {chat.user_message}")
                        st.write(f"**Answer:** {chat.ai_response}")
                        st.caption(f"Date: {chat.timestamp.strftime('%Y-%m-%d %H:%M') if chat.timestamp else '-'}")
            else:
                st.info("No conversations yet")
    
    finally:
        db.close()
    
    st.markdown("---")
    if st.button("← Back to Dashboard", use_container_width=True):
        st.session_state.page = 'dashboard'
        st.rerun()


def render_clickable_logo(key_suffix=""):
    """Render clickable logo that navigates to home"""
    logo_clicked = st.button("", key=f"logo_btn_{key_suffix}", help="Go to Home")
    st.markdown('''
    <style>
    [data-testid="stButton"]:has(button[kind="secondary"][data-testid="stBaseButton-secondary"]) {
        display: none;
    }
    </style>
    <div class="sidebar-logo-container" onclick="window.location.reload()">
        <img src="app/static/logo.png" class="sidebar-logo" alt="DataVision Pro">
    </div>
    ''', unsafe_allow_html=True)
    return logo_clicked

def show_dashboard():
    limits = get_user_limits()
    logo_b64 = get_logo_base64()
    
    if st.session_state.user:
        user_id = st.session_state.user.get('id')
        db = get_db()
        try:
            user_obj = get_user_by_id(db, user_id)
            if user_obj and not check_trial_active(user_obj):
                st.markdown('''
                <div style="text-align: center; padding: 3rem;">
                    <div style="font-size: 4rem; margin-bottom: 1rem;">⏰</div>
                    <h2 style="color: #e2e8f0;">Your Free Trial Has Ended</h2>
                    <p style="color: #94a3b8; font-size: 1.1rem; max-width: 500px; margin: 1rem auto;">
                        Your 60-day free trial period has expired. To continue using DataVision Pro, 
                        please contact our team for activation.
                    </p>
                    <p style="color: #14b8a6; font-size: 1rem;">
                        Contact us at: muayad.demaidi.work@gmail.com
                    </p>
                </div>
                ''', unsafe_allow_html=True)
                show_support_section()
                return
        finally:
            db.close()
    else:
        st.session_state.page = 'login'
        st.rerun()
        return
    
    user = st.session_state.user
    sub_type = user.get('subscription_type', 'tier1')
    tier_label = {"tier1": "Tier 01 · Starter", "tier2": "Tier 02 · Growth", "tier3": "Tier 03 · Full Access"}.get(sub_type, "Tier 01")
    display_name = user.get('full_name') or user.get('username') or 'Analyst'
    avatar_letter = (display_name[:1] or 'A').upper()
    first_name = display_name.split()[0] if display_name else 'Analyst'

    # ── TOP NAVBAR — flat, wordmark only + account popover on right ─────────
    if 'show_contact_panel' not in st.session_state:
        st.session_state.show_contact_panel = False

    nav_brand_col, _, nav_user_col = st.columns([5, 0.3, 1.6], gap="small")
    with nav_brand_col:
        st.markdown(f'''
<div class="dn-topbar">
  <span class="dn-topbar-brand">DataVision <span style="color:var(--teal);">Pro</span></span>
  <span class="dn-topbar-eyebrow">Workspace · Live</span>
</div>
''', unsafe_allow_html=True)
    with nav_user_col:
        st.markdown('<div class="dn-pop-trigger-marker"></div>', unsafe_allow_html=True)
        with st.popover(f"{avatar_letter}   {first_name}   ▾", use_container_width=True):
            st.markdown(f'''
<div class="dn-pop-head">
  <div class="dn-pop-avatar">{avatar_letter}</div>
  <div>
    <div class="dn-pop-name">{display_name}</div>
    <div class="dn-pop-tier">{tier_label}</div>
  </div>
</div>
<div class="dn-pop-divider"></div>
''', unsafe_allow_html=True)
            st.markdown('<div class="dn-pop-marker"></div>', unsafe_allow_html=True)
            if user.get('is_admin'):
                if st.button("  Admin Panel", use_container_width=True, key="pop_admin"):
                    st.session_state.page = 'admin'
                    st.rerun()
            if st.button("  Contact Support", use_container_width=True, key="pop_contact"):
                st.session_state.show_contact_panel = not st.session_state.show_contact_panel
                st.rerun()
            if st.button("→   Sign Out", use_container_width=True, key="pop_signout"):
                _uid = st.session_state.user.get('id') if st.session_state.user else None
                if _uid:
                    _db = get_db()
                    try:
                        _u = get_user_by_id(_db, _uid)
                        clear_session_token(_db, _u)
                    finally:
                        _db.close()
                try:
                    if SESSION_QP_NAME in st.query_params:
                        del st.query_params[SESSION_QP_NAME]
                except Exception as _e:
                    print(f"Query param clear failed: {_e}")
                st.session_state.user = None
                st.session_state.page = 'home'
                st.session_state.df = None
                st.session_state.df_cleaned = None
                st.session_state.session_hydrated = True
                st.rerun()

    st.markdown('<div style="height:0.75rem;"></div>', unsafe_allow_html=True)
    main_col = st.container()

    with main_col:
        # Greeting hero
        st.markdown(f'''
<div class="dn-greeting">
  <div class="dn-greeting-eyebrow">— Welcome back · {tier_label}</div>
  <h1>Hello, {first_name}.</h1>
  <p class="dn-greeting-sub">Upload a dataset to start analysing — or pick up where you left off. Auto-cleaning, deep statistics, charts, and AI insights are one click away.</p>
</div>
''', unsafe_allow_html=True)

        if st.session_state.show_contact_panel:
            st.markdown('''
<div class="dn-contact-slim">
  <div class="dn-contact-slim-head">
    <h3>Contact Support</h3>
    <span class="dn-contact-meta">Reply within 24h</span>
  </div>
</div>
''', unsafe_allow_html=True)
            with st.form("dn_support_form", clear_on_submit=True):
                col_e, col_n = st.columns(2)
                with col_e:
                    s_email = st.text_input("Email Address", placeholder="your@email.com", key="dn_se")
                with col_n:
                    s_name = st.text_input("Full Name", placeholder="Your full name", value=display_name, key="dn_sn")
                s_msg = st.text_area("Message", placeholder="Describe your question or issue…", height=110, key="dn_sm")
                if st.form_submit_button("Send Message →", use_container_width=True):
                    if not s_email or not s_msg:
                        st.warning("Please provide your email address and message.")
                    else:
                        db = get_db()
                        try:
                            save_support_message(db, s_email, s_name, s_msg)
                            try:
                                send_support_notification(s_email, s_name, s_msg)
                            except Exception as e:
                                print(f"Support email notification failed: {e}")
                            st.success("Message sent — we'll get back to you shortly.")
                        finally:
                            db.close()

        def _csv_options_panel(uploaded_file, key_prefix):
            """Render CSV parser options (delimiter, header) and return overrides.
            For non-CSV files, just returns (None, None)."""
            name = uploaded_file.name.lower()
            if not name.endswith('.csv'):
                return None, None
            cache_key = f"_sniff_cache_{key_prefix}_{uploaded_file.name}_{uploaded_file.size}"
            if cache_key not in st.session_state:
                pos = uploaded_file.tell() if hasattr(uploaded_file, 'tell') else 0
                file_bytes = uploaded_file.read()
                try:
                    uploaded_file.seek(pos)
                except Exception:
                    pass
                st.session_state[cache_key] = sniff_csv_options(file_bytes)
            sniff = st.session_state[cache_key]
            ambiguous = (not sniff['delimiter_confident']) or (not sniff['header_confident'])
            with st.expander("CSV parsing options" + (" — please confirm" if ambiguous else ""),
                             expanded=ambiguous):
                if sniff.get('preview'):
                    st.caption("First 5 rows of the raw file:")
                    st.code(sniff['preview'], language="text")
                opt_col1, opt_col2 = st.columns(2)
                with opt_col1:
                    delim_options = list(_DELIM_LABELS.keys())
                    default_delim = sniff['delimiter'] if sniff['delimiter'] in delim_options else ','
                    chosen_delim = st.selectbox(
                        "Delimiter",
                        options=delim_options,
                        index=delim_options.index(default_delim),
                        format_func=lambda d: _DELIM_LABELS[d] +
                            (" — auto-detected" if d == sniff['delimiter'] and sniff['delimiter_confident'] else ""),
                        key=f"{key_prefix}_delim",
                    )
                with opt_col2:
                    header_choice = st.radio(
                        "Use first row as headers?",
                        options=["Yes", "No"],
                        index=0 if sniff['has_header'] else 1,
                        horizontal=True,
                        key=f"{key_prefix}_hdr",
                        help=("Auto-detected" if sniff['header_confident']
                              else "Could not auto-detect — please confirm"),
                    )
                if ambiguous:
                    st.info("The delimiter or header row could not be auto-detected with confidence. "
                            "Please confirm the values above before running the analysis.")
            return chosen_delim, (header_choice == "Yes")

        def run_analysis(file_obj, ds_name, p_month, p_year, lmts,
                         delimiter=None, has_header=None):
            with st.spinner("Loading and analyzing data..."):
                # Reset upload position so a re-read works
                try:
                    file_obj.seek(0)
                except Exception:
                    pass
                df_raw, parse_meta = load_file(file_obj, delimiter=delimiter,
                                               has_header=has_header, return_meta=True)
                if df_raw is None:
                    return
                if len(df_raw) > lmts['max_rows']:
                    st.error(f"Row count ({len(df_raw):,}) exceeds the limit ({lmts['max_rows']:,})")
                    return

                # Build pipeline: Source -> Promoted Headers -> Changed Type -> Cleaning
                history = StepHistory()
                src_summary = (f"Read {parse_meta.get('kind','file')} — "
                               f"delimiter `{parse_meta.get('delimiter') or 'n/a'}`, "
                               f"encoding `{parse_meta.get('encoding') or 'n/a'}`, "
                               f"{len(df_raw):,} rows × {len(df_raw.columns)} cols")
                history.add("Source", src_summary, df_raw, meta={'parse': parse_meta})

                if parse_meta.get('has_header'):
                    history.add("Promoted Headers",
                                "First row promoted to column names",
                                df_raw, meta={})
                else:
                    history.add("Promoted Headers",
                                "Headers auto-named (Column_1 … Column_N)",
                                df_raw, meta={})

                schema = infer_schema(df_raw)
                df_typed = apply_schema(df_raw, schema)
                changed = [s for s in schema if s.inferred_type not in ("text", "empty")]
                type_summary = (f"{len(changed)} of {len(schema)} columns retyped — "
                                + ", ".join(f"{s.column}→{s.inferred_type}"
                                            for s in changed[:6])
                                + ("…" if len(changed) > 6 else ""))
                history.add("Changed Type", type_summary, df_typed,
                            meta={'schema': [s.to_dict() for s in schema]})

                # Cleaning is broken into individual, toggleable substeps so
                # each appears as its own entry in the Applied Steps panel.
                substep_states = {k: True for k, _ in CLEANING_SUBSTEPS}
                df_cleaned, cleaning_report = _apply_cleaning_substeps(
                    history, df_typed, substep_states
                )

                st.session_state.df = df_typed
                st.session_state.df_cleaned = df_cleaned
                st.session_state.cleaning_report = cleaning_report
                st.session_state.inferred_schema_obj = schema

                analysis_results = generate_summary_report(df_cleaned)
                st.session_state.analysis_results = analysis_results
                data_hash = calculate_data_hash(df_typed)
                columns_info = {col: str(df_typed[col].dtype) for col in df_typed.columns}
                try:
                    source_blob = serialize_source_df(df_raw)
                except Exception:
                    source_blob = None
                db = get_db()
                try:
                    uid = (st.session_state.user or {}).get('id')
                    record = save_dataset_record(
                        db, filename=file_obj.name, dataset_name=ds_name,
                        period_month=p_month, period_year=p_year,
                        row_count=len(df_typed), column_count=len(df_typed.columns),
                        columns_info=columns_info, data_hash=data_hash,
                        summary_stats=sanitize_for_json(analysis_results.get('numeric_summary', {})),
                        user_id=uid,
                        source_parquet=source_blob,
                        parse_meta=parse_meta if isinstance(parse_meta, dict) else None,
                        step_recipes=history.to_recipes(),
                        active_step_index=history.active_index,
                    )
                    st.session_state.current_dataset_id = record.id
                    st.session_state.step_histories[record.id] = history
                    st.session_state.inferred_schema[record.id] = [s.to_dict() for s in schema]
                    st.session_state.type_overrides[record.id] = {}
                    st.session_state.cleaning_substep_states[record.id] = substep_states
                    if uid:
                        set_user_last_dataset(db, uid, record.id)
                    similar = find_similar_datasets(db, columns_info)
                    similar = [s for s in similar if s['record']['id'] != record.id]
                    st.session_state.similar_datasets = similar
                    if st.session_state.user:
                        increment_analysis_count(db, st.session_state.user.get('id'))
                finally:
                    db.close()
                st.success("Analysis completed!")
                st.rerun()
    
        if st.session_state.df is None:
            upload_col1, upload_col2, upload_col3 = st.columns([1, 2, 1])
            with upload_col2:
                st.markdown("""
                <div style="text-align: center; background: rgba(13, 148, 136, 0.08); border: 1px solid rgba(20, 184, 166, 0.2); 
                     border-radius: 16px; padding: 2rem; margin-bottom: 1rem;">
                    <div style="font-size: 2.5rem; margin-bottom: 0.5rem;"></div>
                    <h3 style="color: #14b8a6; margin: 0;">Upload Your Data</h3>
                    <p style="color: #64748b; font-size: 0.9rem; margin-top: 0.5rem;">CSV, Excel (XLS, XLSX)</p>
                </div>
                """, unsafe_allow_html=True)
    
                file_limit_mb = limits['max_file_size_mb']
                uploaded_file = st.file_uploader(
                    "Choose CSV or Excel file",
                    type=['csv', 'xlsx', 'xls'],
                    help=f"Drag and drop file here. Limit {file_limit_mb}MB per file",
                    label_visibility="collapsed"
                )
    
                if uploaded_file:
                    file_size_mb = uploaded_file.size / (1024 * 1024)
                    if file_size_mb > limits['max_file_size_mb']:
                        st.error(f"File size ({file_size_mb:.1f} MB) exceeds the limit ({limits['max_file_size_mb']} MB)")
                    else:
                        st.success(f"Uploaded: {uploaded_file.name}")
                        col1, col2 = st.columns(2)
                        with col1:
                            period_month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1)
                        with col2:
                            period_year = st.selectbox("Year", range(2020, 2030), index=datetime.now().year - 2020)
                        dataset_name = st.text_input("Dataset Name", value=uploaded_file.name.split('.')[0])
                        csv_delim, csv_hdr = _csv_options_panel(uploaded_file, "first")
                        if st.button("Start Analysis", type="primary", use_container_width=True):
                            run_analysis(uploaded_file, dataset_name, period_month, period_year,
                                         limits, delimiter=csv_delim, has_header=csv_hdr)

                # ── Recent datasets ─ reopen a previously analysed file with
                # its full Applied Steps history rebuilt from the database.
                _u = st.session_state.user or {}
                _uid = _u.get('id')
                if _uid:
                    _rdb = get_db()
                    try:
                        _recent = get_user_datasets(_rdb, _uid)
                        _recent = [r for r in _recent if r.source_parquet and r.step_recipes][:5]
                    finally:
                        _rdb.close()
                    if _recent:
                        st.markdown("---")
                        st.markdown("##### Recent datasets")
                        st.caption("Reopen a previously analysed dataset and resume from its last Applied Step.")
                        for _rec in _recent:
                            _meta = f"{_rec.row_count:,} rows × {_rec.column_count} cols · {_rec.upload_date.strftime('%Y-%m-%d')}"
                            _rl, _rr = st.columns([0.72, 0.28])
                            with _rl:
                                st.markdown(f"**{_rec.dataset_name}**  \n<span style='color:#94a3b8;font-size:0.8rem;'>{_meta}</span>",
                                            unsafe_allow_html=True)
                            with _rr:
                                if st.button("Reopen", key=f"reopen_{_rec.id}",
                                             use_container_width=True):
                                    if _hydrate_dataset_from_db(_rec.id):
                                        st.rerun()
                                    else:
                                        st.error("Could not rebuild this dataset's history.")

        if st.session_state.df is not None:
            with st.expander("Upload New Data", expanded=False):
                file_limit_mb = limits['max_file_size_mb']
                new_file = st.file_uploader(
                    "Choose CSV or Excel file", type=['csv', 'xlsx', 'xls'],
                    help=f"Limit {file_limit_mb}MB per file", key="new_upload", label_visibility="collapsed"
                )
                if new_file:
                    file_size_mb = new_file.size / (1024 * 1024)
                    if file_size_mb > limits['max_file_size_mb']:
                        st.error(f"File size exceeds limit ({limits['max_file_size_mb']} MB)")
                    else:
                        st.success(f"Uploaded: {new_file.name}")
                        col1, col2 = st.columns(2)
                        with col1:
                            period_month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1, key="new_month")
                        with col2:
                            period_year = st.selectbox("Year", range(2020, 2030), index=datetime.now().year - 2020, key="new_year")
                        dataset_name = st.text_input("Dataset Name", value=new_file.name.split('.')[0], key="new_name")
                        csv_delim2, csv_hdr2 = _csv_options_panel(new_file, "next")
                        if st.button("Start Analysis", type="primary", use_container_width=True, key="new_analyze"):
                            run_analysis(new_file, dataset_name, period_month, period_year,
                                         limits, delimiter=csv_delim2, has_header=csv_hdr2)
    
            _TAB_LABELS = [
                "Overview",
                "Cleaning",
                "Statistics",
                "Visualizations",
                "Predictions",
                "ML & Clusters",
                "AI Chat",
                "Report",
            ]
            st.markdown('''<style>
.dn-side-nav .stRadio > div { gap: 0.45rem !important; flex-direction: column !important; }
.dn-side-nav .stRadio > div > label {
  display: flex !important; align-items: center !important; gap: 0.7rem !important;
  width: 100% !important; padding: 0.85rem 1rem !important; margin: 0 !important;
  border: 1px solid rgba(45,212,191,0.10) !important; border-radius: 12px !important;
  background: linear-gradient(180deg, rgba(17,31,53,0.55), rgba(12,24,41,0.55)) !important;
  color: #94a3b8 !important; font-family: "DM Sans", sans-serif !important;
  font-size: 0.92rem !important; font-weight: 500 !important; letter-spacing: 0.01em !important;
  cursor: pointer !important; transition: all 0.18s ease !important;
}
.dn-side-nav .stRadio > div > label:hover {
  border-color: rgba(45,212,191,0.30) !important; color: #e2e8f0 !important;
  background: linear-gradient(180deg, rgba(45,212,191,0.08), rgba(12,24,41,0.55)) !important;
  transform: translateX(2px);
}
.dn-side-nav .stRadio > div > label > div:first-child { display: none !important; }
.dn-side-nav .stRadio > div > label[data-checked="true"],
.dn-side-nav .stRadio > div > label:has(input:checked) {
  border-color: rgba(45,212,191,0.55) !important;
  background: linear-gradient(180deg, rgba(45,212,191,0.18), rgba(45,212,191,0.04)) !important;
  color: #2dd4bf !important; font-weight: 600 !important;
  box-shadow: 0 0 0 1px rgba(45,212,191,0.20), 0 8px 24px -10px rgba(45,212,191,0.30);
}
.dn-side-nav .dn-side-title {
  font-family: "Syne", sans-serif; font-weight: 800; font-size: 0.72rem;
  letter-spacing: 0.18em; color: #2dd4bf; text-transform: uppercase;
  padding: 0 0.25rem 0.85rem 0.25rem; opacity: 0.85;
}
.dn-side-card {
  position: sticky; top: 1rem;
  background:
    radial-gradient(120% 80% at 0% 0%, rgba(45,212,191,0.10), transparent 55%),
    linear-gradient(180deg, rgba(12,24,41,0.92), rgba(7,16,31,0.92));
  border: 1px solid rgba(45,212,191,0.18); border-radius: 22px;
  padding: 1.4rem 1.05rem 1.1rem 1.05rem;
  backdrop-filter: blur(18px) saturate(140%);
  box-shadow:
    0 1px 0 rgba(255,255,255,0.04) inset,
    0 24px 60px -28px rgba(0,0,0,0.65),
    0 0 0 1px rgba(45,212,191,0.04);
  position: sticky; top: 1rem;
  overflow: hidden;
}
.dn-side-card::before {
  content: ""; position: absolute; left: 0; top: 18%; bottom: 18%; width: 2px;
  background: linear-gradient(180deg, transparent, rgba(45,212,191,0.55), transparent);
  border-radius: 2px;
}
.dn-side-brand {
  display: flex; align-items: center; gap: 0.55rem;
  padding: 0 0.25rem 0.6rem 0.25rem; margin-bottom: 0.85rem;
  border-bottom: 1px solid rgba(45,212,191,0.10);
}
.dn-side-brand-mark {
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(135deg, rgba(45,212,191,0.85), rgba(20,184,166,0.45));
  display: grid; place-items: center; color: #07101f;
  font-family: "Syne", sans-serif; font-weight: 800; font-size: 0.85rem;
  box-shadow: 0 6px 16px -6px rgba(45,212,191,0.55);
}
.dn-side-brand-text {
  font-family: "Syne", sans-serif; font-weight: 700; font-size: 0.95rem;
  color: #e2e8f0; letter-spacing: 0.01em;
}
.dn-side-foot {
  margin-top: 1rem; padding-top: 0.85rem;
  border-top: 1px solid rgba(45,212,191,0.10);
  font-family: "JetBrains Mono", monospace; font-size: 0.68rem;
  letter-spacing: 0.14em; text-transform: uppercase;
  color: rgba(148,163,184,0.55); text-align: center;
}
.dn-section-head {
  margin: 0.25rem 0 1.1rem 0; padding-bottom: 0.85rem;
  border-bottom: 1px solid rgba(45,212,191,0.10);
}
.dn-section-eyebrow {
  font-family: "JetBrains Mono", monospace; font-size: 0.68rem;
  letter-spacing: 0.22em; text-transform: uppercase;
  color: var(--teal); opacity: 0.85; margin-bottom: 0.4rem;
}
.dn-section-title {
  font-family: "Syne", sans-serif; font-weight: 800; font-size: 1.65rem;
  color: #e2e8f0; line-height: 1.15; margin: 0;
}
.dn-section-sub {
  font-family: "DM Sans", sans-serif; font-size: 0.92rem;
  color: #94a3b8; margin-top: 0.45rem; max-width: 60ch;
}
.dn-meta {
  font-family: "DM Sans", sans-serif; font-size: 0.88rem;
  color: #94a3b8; margin: 0.4rem 0 0.85rem 0;
}
.dn-meta b { color: #e2e8f0; font-weight: 600; }
[data-testid="stMetric"] {
  background: linear-gradient(180deg, rgba(17,31,53,0.55), rgba(12,24,41,0.45));
  border: 1px solid rgba(45,212,191,0.12); border-radius: 14px;
  padding: 1rem 1.1rem; transition: border-color 0.18s ease;
}
[data-testid="stMetric"]:hover { border-color: rgba(45,212,191,0.30); }
[data-testid="stMetricLabel"] {
  font-family: "JetBrains Mono", monospace !important; font-size: 0.66rem !important;
  letter-spacing: 0.18em !important; text-transform: uppercase !important;
  color: rgba(148,163,184,0.85) !important;
}
[data-testid="stMetricValue"] {
  font-family: "Syne", sans-serif !important; font-weight: 700 !important;
  font-size: 1.55rem !important; color: #e2e8f0 !important;
}
</style>''', unsafe_allow_html=True)

            nav_col, content_col = st.columns([1, 4], gap="large")
            with nav_col:
                st.markdown('''
<div class="dn-side-card dn-side-nav">
  <div class="dn-side-brand">
    <div class="dn-side-brand-mark">DV</div>
    <div class="dn-side-brand-text">DataVision</div>
  </div>
  <div class="dn-side-title">Workspace</div>
''', unsafe_allow_html=True)
                active_tab = st.radio(
                    "Section", _TAB_LABELS,
                    label_visibility="collapsed", key="dashboard_section"
                )
                st.markdown('<div class="dn-side-foot">v · Data Noir</div></div>', unsafe_allow_html=True)

            with content_col:
                if active_tab == _TAB_LABELS[0]:
                    _section_head("Data Overview", "A snapshot of the dataset — size, integrity, and field types.", "01 — Overview")

                    sh = _get_step_history()
                    view_df = _active_df()
                    sig = _active_step_signature()

                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Total Rows", f"{len(view_df):,}")
                    with col2:
                        st.metric("Total Columns", len(view_df.columns))
                    with col3:
                        quality = _c_quality_score(view_df, sig)
                        st.metric("Data Quality", f"{quality['overall_score']}%")
                    with col4:
                        missing_pct = _c_missing_pct(view_df, sig)
                        st.metric("Missing Values", f"{missing_pct:.1f}%")

                    # ── Applied Steps panel (Power Query-style) ──
                    if sh and not sh.is_empty():
                        st.subheader("Applied Steps")
                        st.caption("Click any step to view the dataset at that point. "
                                   "Cleaning substeps can be toggled on/off — downstream "
                                   "substeps are recomputed automatically.")
                        steps_col, ctrl_col = st.columns([3, 1])
                        with steps_col:
                            for i, step in enumerate(sh.steps):
                                is_active = (i == sh.active_index)
                                is_future = (i > sh.active_index)
                                substep_key = step.meta.get('substep_key')
                                enabled = step.meta.get('enabled', True)
                                badge = "▶" if is_active else ("◌" if is_future else "✓")
                                color = "#2dd4bf" if is_active else ("#64748b" if is_future else "#94a3b8")
                                weight = "700" if is_active else "500"
                                opacity = "0.55" if is_future else ("0.55" if (substep_key and not enabled) else "1")
                                disabled_tag = (" <span style='color:#f59e0b;font-size:0.7rem;"
                                                "letter-spacing:0.08em;'>· DISABLED</span>"
                                                if substep_key and not enabled else "")
                                if substep_key:
                                    row_l, row_chk, row_btn = st.columns([0.6, 0.2, 0.2])
                                else:
                                    row_l, row_btn = st.columns([0.78, 0.22])
                                    row_chk = None
                                with row_l:
                                    st.markdown(
                                        f"<div style='padding:0.45rem 0.6rem;border-left:3px solid {color};"
                                        f"opacity:{opacity};font-weight:{weight};color:#e2e8f0;'>"
                                        f"<span style='color:{color};font-family:JetBrains Mono,monospace;"
                                        f"font-size:0.78rem;letter-spacing:0.1em;'>{badge} STEP {i+1}</span>"
                                        f"{disabled_tag}<br>"
                                        f"<b>{step.name}</b> · <span style='color:#94a3b8;font-size:0.85rem;'>"
                                        f"{step.summary}</span><br>"
                                        f"<span style='color:#64748b;font-size:0.75rem;'>{step.rows:,} rows × {step.cols} cols</span>"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )
                                if row_chk is not None:
                                    with row_chk:
                                        new_enabled = st.checkbox(
                                            "Enabled", value=enabled,
                                            key=f"substep_toggle_{_ds_key()}_{substep_key}",
                                            help="Toggle this cleaning substep on/off. "
                                                 "Downstream substeps will be recomputed.",
                                        )
                                        if new_enabled != enabled:
                                            states = st.session_state.cleaning_substep_states.setdefault(
                                                _ds_key(),
                                                {k: True for k, _ in CLEANING_SUBSTEPS},
                                            )
                                            states[substep_key] = new_enabled
                                            final_df, new_report = _rebuild_cleaning_substeps(sh, states)
                                            if new_report is not None:
                                                st.session_state.df_cleaned = final_df
                                                st.session_state.cleaning_report = new_report
                                            st.rerun()
                                with row_btn:
                                    if not is_active:
                                        if st.button("Go to", key=f"goto_step_{i}_{sig}",
                                                     use_container_width=True):
                                            sh.go_to(i)
                                            _persist_step_history()
                                            st.rerun()
                        with ctrl_col:
                            st.markdown(f"**Active:** `{sh.current().name}`")
                            if sh.has_later_steps():
                                if st.button("Redo to latest", use_container_width=True,
                                             key=f"redo_latest_{sig}"):
                                    sh.redo_latest()
                                    _persist_step_history()
                                    st.rerun()
                                if st.button("Drop later steps", use_container_width=True,
                                             key=f"drop_later_{sig}"):
                                    sh.drop_later()
                                    _persist_step_history()
                                    st.rerun()

                    # Resolve the schema for the ACTIVE step first so the
                    # preview can render currency/date columns in their
                    # inferred display format.
                    active_step = sh.current() if sh else None
                    schema_dicts = (active_step.meta.get('schema') if active_step else None) or []
                    if schema_dicts:
                        schema_for_format = schema_dicts
                    else:
                        schema_for_format = infer_schema(view_df)

                    st.subheader("Data Preview")
                    st.dataframe(
                        view_df.head(10),
                        use_container_width=True,
                        column_config=_column_config_from_schema(schema_for_format, view_df),
                    )

                    st.subheader("Column Types")
                    # Always derive Column Types from the ACTIVE step. If the
                    # active step carries pre-computed schema metadata (e.g.
                    # "Changed Type" or "Changed Type (manual)"), use it for
                    # confidence + samples; otherwise re-infer live against the
                    # active dataframe so navigating back to Source / Promoted
                    # Headers shows the schema that fits *that* step's data.
                    if schema_dicts:
                        schema_df = pd.DataFrame(schema_dicts)
                        if 'sample_values' in schema_df.columns:
                            schema_df['sample_values'] = schema_df['sample_values'].apply(
                                lambda xs: ", ".join(map(str, (xs or [])[:3])))
                        schema_df = schema_df[['column', 'inferred_type', 'confidence',
                                               'sample_values', 'notes']]
                    else:
                        schema_df = schema_to_dataframe(schema_for_format)
                    st.dataframe(schema_df, use_container_width=True)

                    # ── Type override control ──
                    with st.expander("Override a column's type", expanded=False):
                        st.caption("If a column was typed incorrectly, force a different type. "
                                   "This appends a new step to the history.")
                        ovr_cols = list(view_df.columns)
                        if ovr_cols:
                            ov1, ov2, ov3 = st.columns([2, 2, 1])
                            with ov1:
                                ovr_col = st.selectbox("Column", ovr_cols, key=f"ovr_col_{_ds_key()}")
                            with ov2:
                                ovr_type = st.selectbox(
                                    "New type",
                                    options=["text", "integer", "decimal", "currency",
                                             "percentage", "date", "datetime", "boolean",
                                             "categorical"],
                                    key=f"ovr_type_{_ds_key()}",
                                )
                            with ov3:
                                st.markdown("&nbsp;", unsafe_allow_html=True)
                                if st.button("Apply", use_container_width=True,
                                             key=f"ovr_apply_{_ds_key()}"):
                                    sh2 = _get_step_history(create=True)
                                    # Power Query semantics: editing from a
                                    # non-latest step truncates the redo tail
                                    # before appending the new step, so the
                                    # history stays a coherent linear chain.
                                    if sh2.has_later_steps():
                                        sh2.drop_later()
                                    base_df = view_df.copy()
                                    base_df[ovr_col] = cast_column(base_df[ovr_col], ovr_type)
                                    # Capture a fresh schema snapshot so the
                                    # Column Types table reflects the override
                                    # immediately when this step becomes active.
                                    new_schema = infer_schema(base_df)
                                    sh2.add(
                                        "Changed Type (manual)",
                                        f"Column `{ovr_col}` retyped to `{ovr_type}`",
                                        base_df,
                                        meta={
                                            'override': {ovr_col: ovr_type},
                                            'schema': [s.to_dict() for s in new_schema],
                                        },
                                    )
                                    st.session_state.inferred_schema[_ds_key()] = new_schema
                                    overrides = st.session_state.type_overrides.setdefault(_ds_key(), {})
                                    overrides[ovr_col] = ovr_type
                                    _persist_step_history()
                                    st.success(f"Set {ovr_col} → {ovr_type}")
                                    st.rerun()
            
                elif active_tab == _TAB_LABELS[1]:
                    _section_head("Data Cleaning", "What was changed, why, and how it improved the data.", "02 — Cleaning")

                    view_df = _active_df()
                    sig = _active_step_signature()
                    if st.session_state.cleaning_report:
                        report = st.session_state.cleaning_report

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Original Rows", f"{report['original_rows']:,}")
                        with col2:
                            st.metric("Cleaned Rows", f"{report['final_rows']:,}")
                        with col3:
                            st.metric("Rows Removed", report['rows_removed'])

                        if report['changes']:
                            st.subheader("Changes Applied")
                            for change in report['changes']:
                                st.markdown(f'<div class="success-box">{change}</div>', unsafe_allow_html=True)
                        else:
                            st.success("Data is clean! No modifications needed.")

                        st.subheader("Data Quality Score")
                        quality = _c_quality_score(view_df, sig)
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Completeness", f"{quality['completeness']}%")
                        with col2:
                            st.metric("Uniqueness", f"{quality['uniqueness']}%")
                        with col3:
                            st.metric("Overall Score", f"{quality['overall_score']}%")

                        missing_chart = _c_missing_values_chart(view_df, sig)
                        if missing_chart:
                            st.plotly_chart(missing_chart, use_container_width=True)
            
                elif active_tab == _TAB_LABELS[2]:
                    _section_head("Statistical Analysis", "Descriptive statistics, correlations, and outlier signals.", "03 — Statistics")
                
                    df_analysis = _active_df()

                    _ds_id = _active_step_signature()
                    st.subheader("Descriptive Statistics")
                    numeric_stats = _c_numeric_stats(df_analysis, _ds_id)
                    if not numeric_stats.empty:
                        # numeric_stats is `df.describe().T` plus extra metrics:
                        # source column names live in the index and the columns
                        # are statistics (count/mean/std/min/.../missing/...).
                        # Surface the source column as a visible field and apply
                        # numeric formatting (thousand separators + 2dp) to the
                        # stat columns so values like 1234567.89 read as
                        # 1,234,567.89 instead of the raw float.
                        stats_display = numeric_stats.reset_index().rename(
                            columns={"index": "column"})
                        stats_cfg = {"column": st.column_config.TextColumn("column")}
                        int_like = {"count", "missing"}
                        for c in stats_display.columns:
                            if c == "column":
                                continue
                            try:
                                if c in int_like:
                                    stats_cfg[c] = st.column_config.NumberColumn(format="localized")
                                elif c == "missing_pct":
                                    stats_cfg[c] = st.column_config.NumberColumn(format="%.2f%%")
                                else:
                                    stats_cfg[c] = st.column_config.NumberColumn(format="%.2f")
                            except Exception:
                                pass
                        st.dataframe(
                            stats_display,
                            use_container_width=True,
                            hide_index=True,
                            column_config=stats_cfg,
                        )
                    else:
                        st.info("No numeric columns found")
                
                    st.subheader("Categorical Statistics")
                    cat_stats = _c_categorical_stats(df_analysis, _ds_id)
                    if cat_stats:
                        for col, stats in cat_stats.items():
                            with st.expander(f"{col}"):
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.write(f"**Unique Values:** {stats['unique_count']}")
                                    st.write(f"**Most Common:** {stats['most_common']}")
                                with col2:
                                    st.write(f"**Least Common:** {stats['least_common']}")
                                    st.write(f"**Missing Values:** {stats['missing']}")
                
                    st.subheader("Strong Correlations")
                    correlations = _c_strong_correlations(df_analysis, _ds_id)
                    if correlations:
                        for corr in correlations[:5]:
                            emoji = "" if corr['correlation'] > 0 else ""
                            st.markdown(f"{emoji} **{corr['column1']}** & **{corr['column2']}**: {corr['correlation']:.3f}")
                    else:
                        st.info("No strong correlations found")
                
                    st.subheader("Outlier Detection")
                    outliers = _c_outliers(df_analysis, _ds_id)
                    if outliers:
                        for col, info in outliers.items():
                            st.markdown(f'<div class="warning-box">️ **{col}**: {info["count"]} outliers detected ({info["percentage"]}%)</div>', unsafe_allow_html=True)
                    else:
                        st.success("No outliers detected")
            
                elif active_tab == _TAB_LABELS[3]:
                    _section_head("Visualizations", "Distributions, relationships, and custom charts.", "04 — Visualizations")
                
                    df_viz = _active_df()
                    numeric_cols = df_viz.select_dtypes(include=[np.number]).columns.tolist()
                    categorical_cols = df_viz.select_dtypes(include=['object']).columns.tolist()

                    _ds_id = _active_step_signature()
                    st.subheader("Distribution Overview")
                    dist_overview = _c_distribution_overview(df_viz, _ds_id)
                    if dist_overview:
                        st.plotly_chart(dist_overview, use_container_width=True)
                
                    corr_heatmap = _c_correlation_heatmap(df_viz, _ds_id)
                    if corr_heatmap:
                        st.plotly_chart(corr_heatmap, use_container_width=True)
                
                    st.subheader("Custom Charts")
                    chart_type = st.selectbox(
                        "Chart Type",
                        ["Bar Chart", "Scatter Plot", "Box Plot", "Pie Chart", "Line Chart", "Histogram"]
                    )
                
                    col1, col2 = st.columns(2)
                
                    if chart_type == "Bar Chart" and categorical_cols:
                        with col1:
                            x_col = st.selectbox("Category", categorical_cols, key="bar_x")
                        with col2:
                            y_col = st.selectbox("Value", numeric_cols if numeric_cols else [None], key="bar_y")
                        if x_col:
                            fig = create_bar_chart(df_viz, x_col, y_col)
                            if fig:
                                st.plotly_chart(fig, use_container_width=True)
                
                    elif chart_type == "Scatter Plot" and len(numeric_cols) >= 2:
                        with col1:
                            x_col = st.selectbox("X Axis", numeric_cols, key="scatter_x")
                        with col2:
                            y_col = st.selectbox("Y Axis", numeric_cols, key="scatter_y", index=1 if len(numeric_cols) > 1 else 0)
                        fig = create_scatter_plot(df_viz, x_col, y_col)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                
                    elif chart_type == "Box Plot" and numeric_cols:
                        with col1:
                            y_col = st.selectbox("Numeric Column", numeric_cols, key="box_y")
                        with col2:
                            x_col = st.selectbox("Group By", [None] + categorical_cols, key="box_x")
                        fig = create_box_plot(df_viz, y_col, x_col)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                
                    elif chart_type == "Pie Chart" and categorical_cols:
                        with col1:
                            col_select = st.selectbox("Column", categorical_cols, key="pie_col")
                        fig = create_pie_chart(df_viz, col_select)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                
                    elif chart_type == "Line Chart" and numeric_cols:
                        with col1:
                            x_col = st.selectbox("X Axis", df_viz.columns.tolist(), key="line_x")
                        with col2:
                            y_col = st.selectbox("Y Axis", numeric_cols, key="line_y")
                        fig = create_line_chart(df_viz, x_col, y_col)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
                
                    elif chart_type == "Histogram" and numeric_cols:
                        with col1:
                            col_select = st.selectbox("Column", numeric_cols, key="hist_col")
                        fig = create_histogram(df_viz, col_select)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
            
                elif active_tab == _TAB_LABELS[4]:
                    _section_head("Predictions & Comparisons", "Forecast a target column and compare against historical periods.", "05 — Predictions")
                
                    if not limits['predictions_enabled']:
                        st.markdown("""
                        <div class="neon-card">
                            <h3 style="text-align: center;">Tier 2 Feature</h3>
                            <p style="text-align: center; color: #94a3b8;">
                                Advanced predictions and time-series comparisons are available in Tier 2 and above.
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button("View Tiers", use_container_width=True, key="upgrade_pred"):
                            st.session_state.page = 'pricing'
                            st.rerun()
                    else:
                        df_pred = _active_df()
                        numeric_cols = df_pred.select_dtypes(include=[np.number]).columns.tolist()
                    
                        if st.session_state.similar_datasets:
                            st.subheader("Historical Data Comparison")
                            st.info(f"Found {len(st.session_state.similar_datasets)} similar dataset(s)")
                        
                            for similar in st.session_state.similar_datasets[:3]:
                                record = similar['record']
                                with st.expander(f"{record['dataset_name']} ({record['period_month']}/{record['period_year']})"):
                                    st.write(f"**Similarity:** {similar['similarity']*100:.1f}%")
                                    st.write(f"**Rows:** {record['row_count']:,}")
                                    if record.get('summary_stats'):
                                        st.json(record['summary_stats'])
                    
                        st.subheader("Forecasting")
                        if numeric_cols:
                            col1, col2 = st.columns(2)
                            with col1:
                                target_col = st.selectbox("Target Column", numeric_cols, key="pred_target")
                            with col2:
                                periods = st.slider("Forecast Periods", 1, 12, 6)
                        
                            if st.button("Generate Forecast", use_container_width=True):
                                with st.spinner("Generating predictions..."):
                                    values = df_pred[target_col].dropna().tolist()
                                    forecast_result = simple_forecast(values, periods)
                                    if forecast_result is not None and len(values) > 0:
                                        predictions_list = forecast_result.get('predictions', []) if isinstance(forecast_result, dict) else forecast_result
                                        labels = [f"Point {i+1}" for i in range(len(values))]
                                        trend_chart = create_trend_chart(values, labels, f"Forecast for {target_col}", predictions_list)
                                        if trend_chart:
                                            st.plotly_chart(trend_chart, use_container_width=True)
                                    
                                        if isinstance(forecast_result, dict):
                                            trend_info = forecast_result.get('trend', '')
                                            confidence = forecast_result.get('confidence', '')
                                            if trend_info:
                                                st.markdown(f'<div class="insight-box">**Trend:** {trend_info} | **Confidence:** {confidence}</div>', unsafe_allow_html=True)
                                    
                                        trend_analysis = analyze_trend(df_pred, target_col)
                                        if trend_analysis:
                                            st.markdown(f'<div class="insight-box">**Analysis:** {trend_analysis}</div>', unsafe_allow_html=True)
            
                elif active_tab == _TAB_LABELS[5]:
                    _section_head("ML & Clustering", "Categorical analysis, ML models, clusters, and outliers.", "06 — Machine Learning")
                
                    df_ml = _active_df()
                    numeric_cols_ml = df_ml.select_dtypes(include=[np.number]).columns.tolist()
                    cat_cols_ml = df_ml.select_dtypes(include=['object', 'category']).columns.tolist()
                
                    _ML_SUBTABS = ["Categorical Analysis", "ML Prediction", "Risk Clustering", "Outlier Detection"]
                    ml_active = st.radio(
                        "ML Section", _ML_SUBTABS, horizontal=True,
                        label_visibility="collapsed", key="ml_subsection"
                    )
                    _ds_id_ml = _active_step_signature()
                
                    if ml_active == _ML_SUBTABS[0]:
                        _section_head("Categorical Data Analysis", "Distribution and balance of every non-numeric field. Pick a column to explore.")
                        if cat_cols_ml:
                            cat_insights = _c_categorical_insights(df_ml, _ds_id_ml)
                            sel_col1, sel_col2 = st.columns([3, 2])
                            with sel_col1:
                                cat_pick = st.selectbox("Column", cat_cols_ml, key="cat_pick")
                            with sel_col2:
                                chart_type = st.radio("View as", ["Pie", "Bar"], key="cat_chart_type", horizontal=True)
                            if cat_pick in cat_insights:
                                insight = cat_insights[cat_pick]
                                m1, m2, m3 = st.columns(3)
                                with m1: st.metric("Unique Values", insight['unique_values'])
                                with m2: st.metric("Missing", f"{insight['missing_pct']}%")
                                with m3: st.metric("Balance Ratio", f"{insight['balance_ratio']:.2f}")
                            fig = _c_categorical_pie(df_ml, _ds_id_ml, cat_pick) if chart_type == "Pie" else _c_categorical_bar(df_ml, _ds_id_ml, cat_pick)
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.info("No categorical columns found in the dataset.")
                
                    elif ml_active == _ML_SUBTABS[1]:
                        st.subheader("ML Prediction Model")
                        st.markdown("Build a machine learning model to predict any target variable in your data.")
                    
                        if len(numeric_cols_ml) >= 3:
                            target_col_ml = st.selectbox("Select Target Variable to Predict", numeric_cols_ml, key="ml_target")
                        
                            if st.button("Build Prediction Model", use_container_width=True):
                                with st.spinner("Training ML model..."):
                                    result = build_ml_prediction_model(df_ml, target_col_ml)
                                
                                    if 'error' in result:
                                        st.error(result['error'])
                                    else:
                                        st.success(f"Model trained successfully!")
                                    
                                        col1, col2, col3 = st.columns(3)
                                        with col1:
                                            st.metric("Model Type", result['model_type'].title())
                                        with col2:
                                            if result['model_type'] == 'classification':
                                                st.metric("Accuracy", f"{result['accuracy']}%")
                                            else:
                                                st.metric("R² Score", f"{result['r2_score']}%")
                                        with col3:
                                            st.metric("Training Size", f"{result['train_size']:,}")
                                    
                                        if 'feature_importance' in result:
                                            st.subheader("Feature Importance")
                                            fig = create_feature_importance_chart(result['feature_importance'])
                                            st.plotly_chart(fig, use_container_width=True)
                                    
                                        st.subheader("Model Details")
                                        st.json(result)
                        else:
                            st.warning("Need at least 3 numeric columns for ML prediction.")
                
                    elif ml_active == _ML_SUBTABS[2]:
                        st.subheader("Customer/Data Clustering")
                        st.markdown("Segment your data into risk-based clusters using K-Means algorithm.")
                    
                        if len(numeric_cols_ml) >= 2:
                            n_clusters = st.slider("Number of Clusters", 2, 6, 4, key="n_clusters")
                        
                            if st.button("Create Clusters", use_container_width=True):
                                with st.spinner("Creating clusters..."):
                                    result = create_risk_clusters(df_ml, n_clusters)
                                
                                    if 'error' in result:
                                        st.error(result['error'])
                                    else:
                                        st.success(f"Created {n_clusters} clusters successfully!")
                                    
                                        st.subheader("Cluster Distribution")
                                        for cluster_name, stats in result['cluster_stats'].items():
                                            with st.expander(f"{cluster_name} ({stats['size']:,} records - {stats['percentage']}%)"):
                                                st.write("**Characteristics:**")
                                                for col, char in stats['characteristics'].items():
                                                    st.write(f"- {col}: Mean = {char['mean']}, Std = {char['std']}")
                                    
                                        st.subheader("Cluster Visualization")
                                        if len(numeric_cols_ml) >= 2:
                                            col1, col2 = st.columns(2)
                                            with col1:
                                                x_col = st.selectbox("X Axis", numeric_cols_ml, key="cluster_x")
                                            with col2:
                                                y_col = st.selectbox("Y Axis", [c for c in numeric_cols_ml if c != x_col], key="cluster_y")
                                        
                                            df_cluster_viz = df_ml[numeric_cols_ml].dropna()
                                            if len(df_cluster_viz) == len(result['cluster_labels']):
                                                fig = create_cluster_scatter(df_cluster_viz, x_col, y_col, result['cluster_labels'])
                                                st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning("Need at least 2 numeric columns for clustering.")
                
                    elif ml_active == _ML_SUBTABS[3]:
                        _section_head("Outlier Detection", "Values outside the inter-quartile range. Pick a column to inspect.")
                        outliers = _c_outliers(df_ml, _ds_id_ml)
                        if outliers:
                            st.markdown(f'<div class="dn-meta">Outliers found in <b>{len(outliers)}</b> column(s).</div>', unsafe_allow_html=True)
                            out_cols = list(outliers.keys())
                            out_pick = st.selectbox("Column", out_cols, key="outlier_pick")
                            info = outliers[out_pick]
                            m1, m2, m3 = st.columns(3)
                            with m1: st.metric("Outlier Count", info['count'])
                            with m2: st.metric("Lower Bound", f"{info['lower_bound']:.2f}")
                            with m3: st.metric("Upper Bound", f"{info['upper_bound']:.2f}")
                            if info.get('min_outlier') and info.get('max_outlier'):
                                st.markdown(f'<div class="dn-meta">Range of outliers: <b>{info["min_outlier"]:.2f}</b> → <b>{info["max_outlier"]:.2f}</b></div>', unsafe_allow_html=True)
                            info_tuple = tuple(sorted((k, v) for k, v in info.items() if isinstance(v, (int, float, str, bool))))
                            fig = _c_outlier_viz(df_ml, _ds_id_ml, out_pick, info_tuple)
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.success("No significant outliers detected in the numeric columns.")
            
                elif active_tab == _TAB_LABELS[6]:
                    _section_head("AI Assistant", "Ask questions about your data in natural language.", "07 — AI Chat")
                
                    if not limits['ai_chat_enabled']:
                        st.markdown("""
                        <div class="neon-card">
                            <h3 style="text-align: center;">⭐ Tier 3 Feature</h3>
                            <p style="text-align: center; color: #94a3b8;">
                                AI-powered data conversations are available in Tier 3.
                            </p>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button("View Tiers", use_container_width=True, key="upgrade_chat"):
                            st.session_state.page = 'pricing'
                            st.rerun()
                    else:
                        st.markdown("""
                        <style>
                        .chat-container {
                            display: flex;
                            flex-direction: column;
                            height: 500px;
                            background: rgba(15, 23, 42, 0.5);
                            border: 1px solid rgba(20, 184, 166, 0.2);
                            border-radius: 12px;
                            overflow: hidden;
                        }
                        .chat-messages {
                            flex: 1;
                            overflow-y: auto;
                            padding: 1rem;
                            display: flex;
                            flex-direction: column;
                            gap: 0.75rem;
                        }
                        .chat-bubble {
                            max-width: 80%;
                            padding: 0.75rem 1rem;
                            border-radius: 12px;
                            line-height: 1.5;
                            animation: fadeIn 0.3s ease;
                        }
                        @keyframes fadeIn {
                            from { opacity: 0; transform: translateY(10px); }
                            to { opacity: 1; transform: translateY(0); }
                        }
                        .chat-bubble.user {
                            background: linear-gradient(135deg, rgba(13, 148, 136, 0.3), rgba(5, 150, 105, 0.3));
                            border: 1px solid rgba(20, 184, 166, 0.3);
                            align-self: flex-end;
                            color: #e2e8f0;
                        }
                        .chat-bubble.assistant {
                            background: rgba(30, 41, 59, 0.8);
                            border: 1px solid rgba(148, 163, 184, 0.2);
                            align-self: flex-start;
                            color: #cbd5e1;
                        }
                        .chat-role {
                            font-size: 0.7rem;
                            text-transform: uppercase;
                            letter-spacing: 0.5px;
                            margin-bottom: 0.25rem;
                            opacity: 0.7;
                        }
                        .chat-bubble.user .chat-role { color: #14b8a6; }
                        .chat-bubble.assistant .chat-role { color: #94a3b8; }
                        </style>
                        """, unsafe_allow_html=True)
                    
                        st.markdown('<p style="color: #94a3b8; margin-bottom: 1rem;">Ask any question about your data and get AI-powered insights</p>', unsafe_allow_html=True)
                    
                        chat_container = st.container(height=450)
                    
                        with chat_container:
                            if not st.session_state.chat_messages:
                                st.markdown("""
                                <div style="text-align: center; padding: 3rem; color: #64748b;">
                                    <div style="font-size: 3rem; margin-bottom: 1rem;"></div>
                                    <p>Start a conversation about your data!</p>
                                    <p style="font-size: 0.85rem;">Try asking: "What patterns do you see?" or "Summarize the key insights"</p>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                for msg in st.session_state.chat_messages:
                                    role_icon = "" if msg["role"] == "user" else ""
                                    role_label = "You" if msg["role"] == "user" else "AI Assistant"
                                    bubble_class = msg["role"]
                                    st.markdown(f"""
                                    <div class="chat-bubble {bubble_class}">
                                        <div class="chat-role">{role_icon} {role_label}</div>
                                        <div>{msg["content"]}</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                    
                        prompt = st.chat_input("Type your question here...", key="chat_input_main")
                    
                        if prompt:
                            st.session_state.chat_messages.append({"role": "user", "content": prompt})
                        
                            with st.spinner("Analyzing your data..."):
                                df_chat = _active_df()
                                df_info = {
                                    'row_count': len(df_chat),
                                    'column_count': len(df_chat.columns),
                                    'columns': df_chat.columns.tolist(),
                                    'dtypes': df_chat.dtypes.astype(str).to_dict(),
                                    'numeric_summary': df_chat.describe().to_dict() if not df_chat.select_dtypes(include=[np.number]).empty else {}
                                }
                                response = chat_about_data(prompt, df_info)
                                st.session_state.chat_messages.append({"role": "assistant", "content": response})
                            
                                db = get_db()
                                try:
                                    save_chat_message(db, st.session_state.current_dataset_id, prompt, response)
                                finally:
                                    db.close()
                        
                            st.rerun()
            
                elif active_tab == _TAB_LABELS[7]:
                    _section_head("Comprehensive Report", "Executive summary, AI insights, and downloadable artefacts.", "08 — Report")
                
                    df_report = _active_df()
                
                    st.subheader("Executive Summary")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Rows", f"{len(df_report):,}")
                    with col2:
                        st.metric("Columns", len(df_report.columns))
                    with col3:
                        quality = get_data_quality_score(df_report)
                        st.metric("Quality", f"{quality['overall_score']}%")
                    with col4:
                        st.metric("Numeric Cols", len(df_report.select_dtypes(include=[np.number]).columns))
                
                    if st.session_state.analysis_results:
                        st.subheader("Analysis Results")
                        results = st.session_state.analysis_results
                    
                        if 'numeric_summary' in results and results['numeric_summary']:
                            st.markdown("**Numeric Statistics:**")
                            st.json(results['numeric_summary'])
                
                    if limits['ai_chat_enabled']:
                        st.subheader("AI Insights & Recommendations")
                        if st.button("Generate AI Insights", use_container_width=True):
                            with st.spinner("Analyzing data with AI..."):
                                df_summary = {
                                    'row_count': len(df_report),
                                    'column_count': len(df_report.columns),
                                    'columns': df_report.columns.tolist()
                                }
                                analysis_results = st.session_state.analysis_results if st.session_state.analysis_results else {}
                                insights = generate_data_insights(df_summary, analysis_results)
                                st.session_state.ai_insights = insights
                                st.markdown(f'<div class="insight-box">{insights}</div>', unsafe_allow_html=True)
                    
                        if st.session_state.ai_insights:
                            st.markdown(f'<div class="insight-box">{st.session_state.ai_insights}</div>', unsafe_allow_html=True)
                
                    st.markdown("---")
                    st.subheader("Download Report")
                
                    col_dl1, col_dl2 = st.columns(2)
                
                    with col_dl1:
                        report_content = f"""# DataVision Pro - Analysis Report
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
    
        ## Executive Summary
        - **Total Rows:** {len(df_report):,}
        - **Total Columns:** {len(df_report.columns)}
        - **Data Quality Score:** {quality['overall_score']}%
        - **Numeric Columns:** {len(df_report.select_dtypes(include=[np.number]).columns)}
    
        ## Column Information
        {chr(10).join([f"- **{col}**: {df_report[col].dtype}" for col in df_report.columns])}
    
        ## Statistical Summary
        """
                        if st.session_state.analysis_results and 'numeric_summary' in st.session_state.analysis_results:
                            for col, stats in st.session_state.analysis_results['numeric_summary'].items():
                                report_content += f"\n### {col}\n"
                                for stat, val in stats.items():
                                    report_content += f"- {stat}: {val}\n"
                    
                        if st.session_state.ai_insights:
                            report_content += f"\n## AI Insights & Recommendations\n{st.session_state.ai_insights}\n"
                    
                        st.download_button(
                            label="📄 Download Report (TXT)",
                            data=report_content,
                            file_name=f"datavision_report_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
                            mime="text/plain",
                            use_container_width=True
                        )
                
                    with col_dl2:
                        csv_data = df_report.to_csv(index=False)
                        st.download_button(
                            label="📊 Download Data (CSV)",
                            data=csv_data,
                            file_name=f"cleaned_data_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
        


def show_support_section():
    st.markdown('''
<div style="height:1px;background:linear-gradient(90deg,transparent,rgba(45,212,191,0.20),transparent);margin:2rem 0 2.5rem 0;"></div>
<div class="lp-support-section" id="contact"><div class="lp-section-inner">
<div class="lp-section-header"><h2>Get in Touch</h2><p>Have a question about your data, your plan, or how the platform works? Our team responds within 24 hours.</p></div>
<div class="lp-support-pro-wrap">
''', unsafe_allow_html=True)

    sup_left, sup_right = st.columns([1, 1.35])

    with sup_left:
        st.markdown('''
<div class="lp-support-left">
<h3>We&rsquo;re Here to Help</h3>
<p class="lp-support-tagline">Whether you&rsquo;re troubleshooting an analysis, exploring plan options, or just getting started &mdash; reach out and we&rsquo;ll guide you through it.</p>
<div class="lp-support-contact-item"><div class="lp-support-icon lp-support-icon-email"></div><div><div class="lp-support-contact-label">Response via</div><div class="lp-support-contact-value">Email &mdash; usually within 24h</div></div></div>
<div class="lp-support-contact-item"><div class="lp-support-icon lp-support-icon-clock"></div><div><div class="lp-support-contact-label">Support Hours</div><div class="lp-support-contact-value">Sunday &ndash; Thursday, 9 AM &ndash; 6 PM</div></div></div>
<div class="lp-support-contact-item"><div class="lp-support-icon lp-support-icon-check"></div><div><div class="lp-support-contact-label">We can help with</div><div class="lp-support-contact-value">Platform usage, data questions &amp; account issues</div></div></div>
</div>
''', unsafe_allow_html=True)

    with sup_right:
        st.markdown('<div class="lp-support-right"><h4>Send a Message</h4>', unsafe_allow_html=True)
        with st.form("support_form", clear_on_submit=True):
            support_email = st.text_input("Email Address", placeholder="your@email.com")
            support_name = st.text_input("Full Name", placeholder="Your full name")
            support_message = st.text_area("Message", placeholder="Describe your question, request, or issue…", height=130)
            support_submit = st.form_submit_button("Send Message \u2192", use_container_width=True)

            if support_submit:
                if not support_email or not support_message:
                    st.warning("Please provide your email address and message.")
                else:
                    db = get_db()
                    try:
                        save_support_message(db, support_email, support_name, support_message)
                        try:
                            send_support_notification(support_email, support_name, support_message)
                        except Exception as e:
                            print(f"Support email notification failed: {e}")
                        st.success("Message sent — we'll get back to you shortly.")
                    finally:
                        db.close()
        st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('</div></div></div>', unsafe_allow_html=True)


def show_home_page():
    logo_b64 = get_logo_base64()

    # ── Matrix-rain background (landing page only — too heavy for dashboard) ──
    st.markdown('''
<div class="matrix-bg">
    <div class="matrix-column" style="left: 2%; animation-duration: 12s; animation-delay: 0s;"><span>0</span><span>1</span><span>1</span><span>0</span><span>1</span><span>∑</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 10%; animation-duration: 15s; animation-delay: 2s;"><span>A</span><span>I</span><span>∫</span><span>7</span><span>3</span><span>9</span><span>π</span></div>
    <div class="matrix-column" style="left: 18%; animation-duration: 10s; animation-delay: 4s;"><span>1</span><span>0</span><span>0</span><span>1</span><span>√</span><span>∞</span><span>0</span></div>
    <div class="matrix-column" style="left: 26%; animation-duration: 18s; animation-delay: 1s;"><span>データ</span><span>5</span><span>8</span><span>2</span><span>∑</span></div>
    <div class="matrix-column" style="left: 34%; animation-duration: 14s; animation-delay: 6s;"><span>0</span><span>1</span><span>1</span><span>0</span><span>1</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 42%; animation-duration: 11s; animation-delay: 3s;"><span>π</span><span>4</span><span>2</span><span>0</span><span>∫</span><span>1</span><span>9</span></div>
    <div class="matrix-column" style="left: 50%; animation-duration: 16s; animation-delay: 8s;"><span>分</span><span>析</span><span>3</span><span>1</span><span>4</span><span>∑</span></div>
    <div class="matrix-column" style="left: 58%; animation-duration: 13s; animation-delay: 5s;"><span>1</span><span>0</span><span>1</span><span>1</span><span>0</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 66%; animation-duration: 17s; animation-delay: 0s;"><span>∞</span><span>6</span><span>2</span><span>8</span><span>3</span><span>√</span><span>1</span></div>
    <div class="matrix-column" style="left: 74%; animation-duration: 12s; animation-delay: 7s;"><span>0</span><span>1</span><span>0</span><span>1</span><span>π</span><span>2</span><span>9</span></div>
    <div class="matrix-column" style="left: 82%; animation-duration: 15s; animation-delay: 4s;"><span>5</span><span>3</span><span>∑</span><span>1</span><span>0</span><span>∫</span></div>
    <div class="matrix-column" style="left: 90%; animation-duration: 13s; animation-delay: 6s;"><span>1</span><span>1</span><span>0</span><span>0</span><span>1</span><span>0</span><span>1</span></div>
</div>
''', unsafe_allow_html=True)

    # ── NAVBAR ────────────────────────────────────────────────────────────────
    st.markdown(f'''
<div class="lp-nav"><div class="lp-nav-inner">
<a class="lp-nav-logo" href="/" target="_self"><img src="data:image/png;base64,{logo_b64}" alt="DataVision Pro"></a>
<div class="lp-nav-links">
<a class="lp-nav-link" href="#features">Features</a>
<a class="lp-nav-link" href="#how">How It Works</a>
<a class="lp-nav-link" href="#pricing">Pricing</a>
<a class="lp-nav-link" href="#contact">Contact</a>
</div>
<div class="lp-nav-actions">
<a class="lp-nav-signin-link" href="?signin=1" target="_self">Sign In</a>
</div>
</div></div>
<div class="lp-nav-spacer"></div>
''', unsafe_allow_html=True)

    # ── HERO ──────────────────────────────────────────────────────────────────
    st.markdown(f'''
<div class="lp-hero" style="text-align:center;padding:3rem 0 1.5rem 0;">
<a href="/" target="_self" style="display:inline-block;" class="logo-link"><img src="data:image/png;base64,{logo_b64}" style="max-width:640px;width:100%;border-radius:14px;" alt="DataVision Pro logo"></a>
<h1 style="font-family:&#39;Syne&#39;,sans-serif;font-size:3.75rem;font-weight:800;letter-spacing:-0.04em;background:linear-gradient(135deg,#2dd4bf 0%,#14b8a6 40%,#94a3b8 100%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;margin:1.75rem 0 1rem 0;line-height:1.05;">Intelligent Data Analytics,<br>Done in Seconds</h1>
<p style="font-size:1.15rem;color:#94a3b8;font-weight:400;max-width:560px;margin:0 auto 0.5rem auto;line-height:1.7;">Upload any dataset and get instant cleaning, statistics, charts, and AI-powered insights &mdash; <span style="color:#2dd4bf;font-weight:600;">no code required.</span></p>
</div>
''', unsafe_allow_html=True)

    # ── SINGLE CTA BUTTON ─────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([0.75, 2.5, 0.75])
    with col2:
        st.markdown('<div class="lp-btn-primary">', unsafe_allow_html=True)
        if st.button("Get Started Free \u2192", use_container_width=True, type="primary"):
            st.session_state.page = 'login'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('<div class="lp-cta-tag">60-day free trial &nbsp;<b>\u00b7</b>&nbsp; No credit card &nbsp;<b>\u00b7</b>&nbsp; Instant access</div>', unsafe_allow_html=True)

    # ── TRUST BAR ─────────────────────────────────────────────────────────────
    st.markdown('''
<div class="lp-trust">
<div class="lp-trust-bar">
<span class="lp-trust-pill">1 Million+ Rows Supported</span>
<span class="lp-trust-pill">60-Day Free Trial</span>
<span class="lp-trust-pill">AI-Powered Insights</span>
</div>
</div>
''', unsafe_allow_html=True)

    # ── FEATURE CARDS ─────────────────────────────────────────────────────────
    st.markdown('''
<div class="lp-features" id="features"><div class="lp-section-inner">
<div class="lp-section-header"><h2>Everything You Need</h2><p>From raw data to actionable insights in seconds. No code, no setup, no complexity.</p></div>
<div class="lp-feature-grid">
<div class="lp-feat-card"><div class="lp-feat-icon lp-icon-1"></div><div class="lp-feat-title">Auto Cleaning</div><div class="lp-feat-desc">Removes duplicates, fixes missing values, and eliminates outliers in one click.</div></div>
<div class="lp-feat-card"><div class="lp-feat-icon lp-icon-2"></div><div class="lp-feat-title">Deep Analytics</div><div class="lp-feat-desc">Comprehensive statistics, correlations, distributions, and interactive charts.</div></div>
<div class="lp-feat-card"><div class="lp-feat-icon lp-icon-3"></div><div class="lp-feat-title">AI Powered</div><div class="lp-feat-desc">GPT-driven chat assistant and smart recommendations tailored to your data.</div></div>
<div class="lp-feat-card"><div class="lp-feat-icon lp-icon-4"></div><div class="lp-feat-title">Predictions</div><div class="lp-feat-desc">ML models and trend analysis that forecast what your data will look like next.</div></div>
</div>
</div></div>
''', unsafe_allow_html=True)

    # ── HOW IT WORKS ──────────────────────────────────────────────────────────
    st.markdown('''
<div class="lp-hiw" id="how"><div class="lp-section-inner"><div class="lp-hiw-section">
<h2>How It Works</h2>
<div class="lp-steps-grid">
<div class="lp-step-card"><div class="lp-step-num">01</div><div class="lp-step-title">Upload Your File</div><div class="lp-step-desc">Drop any CSV or Excel file &#8212; up to 1 million rows and 200 MB. No formatting required.</div></div>
<div class="lp-step-card"><div class="lp-step-num">02</div><div class="lp-step-title">Clean and Analyse</div><div class="lp-step-desc">One click auto-cleans your data and runs a comprehensive statistical report instantly.</div></div>
<div class="lp-step-card"><div class="lp-step-num">03</div><div class="lp-step-title">Explore and Export</div><div class="lp-step-desc">Dive into interactive charts, ask the AI assistant, and export professional PDF reports.</div></div>
</div>
</div></div></div>
''', unsafe_allow_html=True)

    # ── TIERS TEASER ──────────────────────────────────────────────────────────
    st.markdown('''
<div class="lp-tiers" id="pricing"><div class="lp-section-inner"><div class="lp-tiers-section">
<h2>Choose Your Plan</h2>
<p class="lp-tiers-sub">All tiers are free during the testing period &mdash; full Tier 3 access for 60 days on sign-up.</p>
<div class="lp-tiers-grid">
<div class="lp-tier-card">
<div class="lp-tier-name">Tier 1</div>
<div class="lp-tier-tagline">Perfect for getting started with your first datasets</div>
<div class="lp-tier-divider"></div>
<ul class="lp-tier-features">
<li><span class="lp-check">&#10003;</span>Up to 10,000 rows</li>
<li><span class="lp-check">&#10003;</span>Auto Cleaning &amp; Statistics</li>
<li><span class="lp-check">&#10003;</span>Interactive Charts</li>
<li><span class="lp-check">&#10003;</span>Files up to 50 MB</li>
</ul>
</div>
<div class="lp-tier-card featured">
<div class="lp-tier-badge">Most Popular</div>
<div class="lp-tier-name">Tier 2</div>
<div class="lp-tier-tagline">For growing teams and business analysts</div>
<div class="lp-tier-divider"></div>
<ul class="lp-tier-features">
<li><span class="lp-check">&#10003;</span>Up to 500,000 rows</li>
<li><span class="lp-check">&#10003;</span>ML Models &amp; Predictions</li>
<li><span class="lp-check">&#10003;</span>K-Means Clustering</li>
<li><span class="lp-check">&#10003;</span>Files up to 200 MB</li>
</ul>
</div>
<div class="lp-tier-card">
<div class="lp-tier-name">Tier 3</div>
<div class="lp-tier-tagline">Full power, unlimited analytical potential</div>
<div class="lp-tier-divider"></div>
<ul class="lp-tier-features">
<li><span class="lp-check">&#10003;</span>Up to 1 Million rows</li>
<li><span class="lp-check">&#10003;</span>AI Chat Assistant</li>
<li><span class="lp-check">&#10003;</span>Export PDF Reports</li>
<li><span class="lp-check">&#10003;</span>Everything in Tier 2</li>
</ul>
</div>
</div>
</div></div></div>
''', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown('<div class="lp-btn-outline">', unsafe_allow_html=True)
        if st.button("View All Plans & Features", use_container_width=True):
            st.session_state.page = 'pricing'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        # ── SUPPORT FORM ──────────────────────────────────────────────────────────
    show_support_section()

    # ── FOOTER ────────────────────────────────────────────────────────────────
    st.markdown(f'''
<div class="lp-footer">
<div class="lp-footer-inner">
<div>
<img src="data:image/png;base64,{logo_b64}" style="height:60px;width:auto;border-radius:6px;" alt="DataVision Pro">
<p class="lp-footer-brand-desc">An intelligent data analytics platform that turns raw datasets into clear, actionable insights &mdash; in seconds, no code required.</p>
</div>
<div>
<div class="lp-footer-col-title">Platform</div>
<ul class="lp-footer-links-list">
<li><a href="#">Features</a></li>
<li><a href="#">How It Works</a></li>
<li><a href="#">Pricing &amp; Plans</a></li>
<li><a href="#">60-Day Free Trial</a></li>
</ul>
</div>
<div>
<div class="lp-footer-col-title">Support</div>
<ul class="lp-footer-links-list">
<li><a href="#">Contact Us</a></li>
<li><a href="#">Documentation</a></li>
<li><a href="#">Account Help</a></li>
<li><a href="#">Report an Issue</a></li>
</ul>
</div>
</div>
<div class="lp-footer-bottom">
<span class="lp-footer-copy">&copy; 2026 DataVision Pro. All rights reserved.</span>
<span class="lp-footer-status">All systems operational</span>
</div>
</div>
''', unsafe_allow_html=True)


logo_b64_main = get_logo_base64()

st.markdown("""
<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    section[data-testid="stSidebarContent"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

if st.session_state.page == 'home':
    show_home_page()
elif st.session_state.page == 'login':
    show_login_page()
elif st.session_state.page == 'register':
    show_register_page()
elif st.session_state.page == 'pricing':
    show_pricing_page()
elif st.session_state.page == 'admin':
    if st.session_state.user and st.session_state.user.get('is_admin'):
        show_admin_panel()
    else:
        st.error("Access denied. Admin privileges required.")
        st.session_state.page = 'dashboard'
        st.rerun()
elif st.session_state.page == 'dashboard':
    show_dashboard()
else:
    show_home_page()
