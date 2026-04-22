import os
import streamlit as st
import pandas as pd
import numpy as np
import hashlib
import json
import copy
from collections import OrderedDict
from datetime import datetime
import io
import base64
import csv as _csv
import re
import time

from context.type_inference import (
    infer_schema, apply_schema, schema_to_dataframe, cast_column, ColumnType
)
from context.step_history import (
    StepHistory, Step,
    serialize_source_df, deserialize_source_df,
    rebuild_history_from_recipes,
)


DATE_FORMAT_PRESETS = {
    "DD-MMM-YYYY (default)": ("DD-MMM-YYYY", "DD-MMM-YYYY HH:mm"),
    "MM/DD/YYYY (US)":       ("MM/DD/YYYY", "MM/DD/YYYY HH:mm"),
    "DD/MM/YYYY (EU)":       ("DD/MM/YYYY", "DD/MM/YYYY HH:mm"),
    "YYYY-MM-DD (ISO)":      ("YYYY-MM-DD", "YYYY-MM-DD HH:mm"),
}

NUMBER_FORMAT_PRESETS = {
    "Thousand separators (1,234.56)": {"int": "localized", "dec": "localized"},
    "Plain (1234.56)":                {"int": "plain",     "dec": "plain"},
    "No decimals (1,235)":            {"int": "localized", "dec": "%.0f"},
    "Two decimals (1,234.57)":        {"int": "%.2f",      "dec": "%.2f"},
}

CURRENCY_FORMAT_PRESETS = {
    "Accounting":     "accounting",
    "Dollar ($)":     "dollar",
    "Euro (\u20ac)":  "euro",
    "Yen (\u00a5)":   "yen",
    "Plain number":   "%.2f",
}

DEFAULT_DISPLAY_PREFS = {
    "date_format":     "DD-MMM-YYYY (default)",
    "number_format":   "Thousand separators (1,234.56)",
    "currency_format": "Accounting",
}


def _resolve_display_prefs(prefs):
    """Look up the actual format strings for a (possibly partial) prefs dict."""
    p = dict(DEFAULT_DISPLAY_PREFS)
    if prefs:
        p.update({k: v for k, v in prefs.items() if v})
    date_fmt, dt_fmt = DATE_FORMAT_PRESETS.get(
        p["date_format"], DATE_FORMAT_PRESETS[DEFAULT_DISPLAY_PREFS["date_format"]]
    )
    num_fmts = NUMBER_FORMAT_PRESETS.get(
        p["number_format"], NUMBER_FORMAT_PRESETS[DEFAULT_DISPLAY_PREFS["number_format"]]
    )
    curr_fmt = CURRENCY_FORMAT_PRESETS.get(
        p["currency_format"], CURRENCY_FORMAT_PRESETS[DEFAULT_DISPLAY_PREFS["currency_format"]]
    )
    return {
        "date": date_fmt, "datetime": dt_fmt,
        "int": num_fmts["int"], "dec": num_fmts["dec"],
        "currency": curr_fmt,
    }


def _column_config_from_schema(schema_iter, df=None, prefs=None):
    """Build a Streamlit column_config dict that pretty-prints inferred types.

    Currency/decimal/date formats come from the user's display preferences
    (see DEFAULT_DISPLAY_PREFS); percentages always render as percent. The
    mapping is driven off whatever schema is captured at the active step, so
    manual overrides automatically flow through to the preview formatting.
    """
    cfg = {}
    if not schema_iter:
        return cfg
    fmts = _resolve_display_prefs(prefs)
    cols_in_df = set(df.columns) if df is not None else None
    for s in schema_iter:
        if isinstance(s, dict):
            col = s.get("column")
            t = (s.get("inferred_type") or "").lower()
            cur_code = s.get("currency_code")
        else:
            col = getattr(s, "column", None)
            t = (getattr(s, "inferred_type", "") or "").lower()
            cur_code = getattr(s, "currency_code", None)
        if not col:
            continue
        if cols_in_df is not None and col not in cols_in_df:
            continue
        try:
            if t == "integer":
                cfg[col] = st.column_config.NumberColumn(format=fmts["int"])
            elif t == "decimal":
                cfg[col] = st.column_config.NumberColumn(format=fmts["dec"])
            elif t == "currency":
                # When the user hasn't overridden the currency format
                # (still on the default "accounting"), prefer the inferred
                # currency_code so symbols/codes show through. An explicit
                # user choice always wins.
                if cur_code and fmts["currency"] == "accounting":
                    # ISO code → suffix ("1234.50 USD"); symbol → prefix ("€ 1234.50").
                    if len(cur_code) == 3 and cur_code.isalpha():
                        fmt = f"%.2f {cur_code}"
                    else:
                        fmt = f"{cur_code} %.2f"
                    cfg[col] = st.column_config.NumberColumn(format=fmt)
                else:
                    cfg[col] = st.column_config.NumberColumn(format=fmts["currency"])
            elif t == "percentage":
                cfg[col] = st.column_config.NumberColumn(format="percent")
            elif t == "date":
                cfg[col] = st.column_config.DateColumn(format=fmts["date"])
            elif t == "datetime":
                cfg[col] = st.column_config.DatetimeColumn(format=fmts["datetime"])
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
    get_user_datasets, get_user_by_email,
    create_password_reset_token, get_valid_password_reset_token,
    consume_password_reset_token, purge_expired_password_reset_tokens,
    create_project, list_user_projects, get_project, update_project,
    delete_project, touch_project, ensure_default_project_for_user,
)
from data_cleaner import (
    clean_data, detect_column_types, get_data_quality_score,
    CLEANING_SUBSTEPS, SUBSTEP_FUNCS, SUBSTEP_REGISTRY,
    DEFAULT_CLEANING_PLAN, run_substep, substep_label,
    SUBSTEP_PARAM_SCHEMA, default_substep_params,
)
from transforms import VALID_AGGS as TRANSFORM_AGGS, infer_examples_op
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
from email_service import send_welcome_email, send_support_notification, send_password_reset_email, send_password_changed_email

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
.lp-footer-inner { max-width: 1200px; margin: 0 auto; display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 3rem; margin-bottom: 3rem; }
@media (max-width: 880px) { .lp-footer-inner { grid-template-columns: 1fr 1fr; } }
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

/* Popover dropdown content (rendered at body level).
   BaseWeb wraps the body in 2-3 layers, any of which can default to
   white. Force every layer transparent / dark so no white frame leaks. */
[data-baseweb="popover"],
[data-baseweb="popover"] > div,
[data-baseweb="popover"] > div > div {
    background: transparent !important;
    background-color: transparent !important;
    box-shadow: none !important;
}
/* The actual visible panel that Streamlit renders our content into */
[data-baseweb="popover"] [data-testid="stPopoverBody"] {
    background: linear-gradient(180deg, #0c1829 0%, #07101f 100%) !important;
    background-color: #0c1829 !important;
    color: #cbd5e1 !important;
    border: 1px solid rgba(45,212,191,0.28) !important;
    border-radius: 14px !important;
    box-shadow: 0 18px 48px rgba(0,0,0,0.55),
                0 0 0 1px rgba(45,212,191,0.06),
                inset 0 1px 0 rgba(255,255,255,0.02) !important;
    padding: 1rem 0.85rem !important;
    min-width: 260px !important;
}
/* Ensure every nested wrapper inside the body inherits the dark surface
   (Streamlit's emotion-cached divs occasionally re-introduce white). */
[data-baseweb="popover"] [data-testid="stPopoverBody"] > div,
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stVerticalBlock"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stHorizontalBlock"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stColumn"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stForm"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"] {
    background: transparent !important;
    background-color: transparent !important;
    color: #cbd5e1 !important;
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

/* === Project-row "•••" overflow trigger ============================
   Without this, the row's popover button is the default (invisible)
   Streamlit button and only appears on hover. */
[data-testid="stColumn"]:has(.proj-row-more-marker) [data-testid="stPopover"] > div > button {
    background: rgba(148,163,184,0.06) !important;
    border: 1px solid rgba(148,163,184,0.18) !important;
    color: #cbd5e1 !important;
    font-weight: 700 !important; font-size: 1rem !important;
    letter-spacing: 0.06em !important;
    padding: 0.35rem 0.6rem !important; height: 38px !important;
    min-height: 38px !important;
    border-radius: 10px !important; box-shadow: none !important;
    transition: background 160ms ease, border-color 160ms ease, color 160ms ease !important;
}
[data-testid="stColumn"]:has(.proj-row-more-marker) [data-testid="stPopover"] > div > button:hover {
    background: rgba(45,212,191,0.10) !important;
    border-color: rgba(45,212,191,0.40) !important;
    color: var(--teal) !important;
}
[data-testid="stColumn"]:has(.proj-row-more-marker) [data-testid="stPopover"] > div > button p {
    color: inherit !important; margin: 0 !important; font-size: inherit !important;
}

/* === Popover-panel content readability ============================
   Captions, inputs, dividers and separator inside any popover. */
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stCaptionContainer"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] .st-emotion-cache-* small,
[data-baseweb="popover"] [data-testid="stPopoverBody"] p {
    color: #cbd5e1 !important;
}
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stCaption"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] small {
    color: #94a3b8 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.7rem !important; letter-spacing: 0.10em !important;
    text-transform: uppercase !important;
}
[data-baseweb="popover"] [data-testid="stPopoverBody"] hr,
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stMarkdown"] hr {
    border: none !important;
    border-top: 1px solid rgba(148,163,184,0.14) !important;
    margin: 0.65rem 0 !important;
}
/* Neutralize BaseWeb input/textarea wrappers (they add a white frame) */
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-baseweb="input"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-baseweb="base-input"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-baseweb="textarea"] {
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
}
[data-baseweb="popover"] [data-testid="stPopoverBody"] input[type="text"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] input[type="password"],
[data-baseweb="popover"] [data-testid="stPopoverBody"] textarea {
    background: rgba(7,16,31,0.85) !important;
    background-color: rgba(7,16,31,0.85) !important;
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
    border: 1px solid rgba(148,163,184,0.25) !important;
    border-radius: 9px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.9rem !important;
    padding: 0.55rem 0.75rem !important;
    caret-color: var(--teal) !important;
}
[data-baseweb="popover"] [data-testid="stPopoverBody"] input[type="text"]::placeholder,
[data-baseweb="popover"] [data-testid="stPopoverBody"] textarea::placeholder {
    color: #64748b !important;
}
[data-baseweb="popover"] [data-testid="stPopoverBody"] input[type="text"]:focus,
[data-baseweb="popover"] [data-testid="stPopoverBody"] textarea:focus {
    border-color: rgba(45,212,191,0.55) !important;
    box-shadow: 0 0 0 3px rgba(45,212,191,0.12) !important;
    outline: none !important;
}
/* Make destructive "Yes, delete" stand out without screaming */
[data-baseweb="popover"] [data-testid="stPopoverBody"] [data-testid="stButton"] > button[kind="primary"] {
    background: var(--teal) !important;
    color: #07101f !important;
    border: 1px solid var(--teal) !important;
    font-weight: 700 !important;
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
    if st.query_params.get('reset_token'):
        # Deep-link from password reset email — must land on the reset page
        # even before any sign-in state exists. Preserve the token query param.
        st.session_state.page = 'reset_password'
    elif st.query_params.get('forgot') == '1':
        st.session_state.page = 'forgot_password'
        st.query_params.clear()
    elif st.query_params.get('signin') == '1':
        st.session_state.page = 'login'
        st.query_params.clear()
    elif st.query_params.get('register') == '1':
        st.session_state.page = 'register'
        st.query_params.clear()
    elif st.query_params.get('help') == '1':
        st.session_state.page = 'help'
        st.query_params.clear()
    # Public, token-gated SEO review page (mobile-friendly, no login required).
    # Keep the token in the URL so refreshes stay authorised.
    elif st.query_params.get('review_token'):
        st.session_state.page = 'review'
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
if 'current_project_id' not in st.session_state:
    # The active project a user has opened from the Projects landing page.
    # show_dashboard() refuses to render unless this is set, bouncing the
    # user back to the Projects page so dataset listings stay scoped.
    st.session_state.current_project_id = None
if 'current_project_name' not in st.session_state:
    st.session_state.current_project_name = None
if 'step_histories' not in st.session_state:
    st.session_state.step_histories = {}
if 'inferred_schema' not in st.session_state:
    st.session_state.inferred_schema = {}
if 'type_overrides' not in st.session_state:
    st.session_state.type_overrides = {}
if 'cleaning_substep_states' not in st.session_state:
    st.session_state.cleaning_substep_states = {}
if 'cleaning_substep_plans' not in st.session_state:
    # Per-dataset ordered cleaning plan: list of dicts with
    # {instance_id, key, enabled, params}. Drives reorder/insert and
    # carries each substep's threshold params (missing-value cap,
    # IQR multiplier, etc.) so they survive across rebuilds.
    st.session_state.cleaning_substep_plans = {}
if 'display_prefs' not in st.session_state:
    st.session_state.display_prefs = {}
if 'plan_replay_cache' not in st.session_state:
    # Per-dataset LRU cache mapping prefix-hash -> snapshot of the
    # replayed plan up to and including that step. Lets reorder/toggle
    # actions skip re-executing prefix steps that haven't changed since
    # the last replay. Cleared naturally when the user uploads a new
    # dataset (new ds_key) or the session ends.
    st.session_state.plan_replay_cache = {}


def _ds_key():
    return st.session_state.get('current_dataset_id') or '__local__'


def _get_display_prefs():
    """Return the current dataset's display preferences (created on first use)."""
    key = _ds_key()
    return st.session_state.display_prefs.setdefault(key, dict(DEFAULT_DISPLAY_PREFS))


def _get_step_history(create=False):
    key = _ds_key()
    sh = st.session_state.step_histories.get(key)
    if sh is None and create:
        sh = StepHistory()
        st.session_state.step_histories[key] = sh
    return sh


# ── Phase 1 auto-apply: doubt detection + persistent chat dock ───────────
# Phase 1 (type inference, default cleaning, formatting) runs the moment a
# dataset loads. These helpers surface what was done, flag low-confidence
# decisions ("doubts"), and feed chat answers back into the pipeline.

_DATE_AMBIG_RE = re.compile(
    r'^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})')


def _detect_dataset_doubts(schema, cleaning_report=None, df=None):
    """Return a list of low-confidence Phase 1 decisions worth surfacing.

    Each doubt is a dict {id, kind, column, message, options} where `kind`
    is 'type' | 'currency' | 'outlier' | 'date_format'. Used by the
    auto-applied strip (inline notes) and the chat dock (quick replies +
    free-text routing).
    """
    doubts = []
    for s in (schema or []):
        is_dict = isinstance(s, dict)
        col = s['column'] if is_dict else s.column
        t = s['inferred_type'] if is_dict else s.inferred_type
        conf = float(s.get('confidence', 0) if is_dict else s.confidence)
        cur_code = (s.get('currency_code') if is_dict else s.currency_code)
        if t in ('text', 'empty'):
            continue
        if conf < 0.85:
            doubts.append({
                'id': f"type__{col}", 'kind': 'type',
                'column': col, 'value': t, 'confidence': conf,
                'message': (f"I read **{col}** as **{t}** "
                            f"(confidence {int(conf*100)}%)."),
                'options': [f"Keep as {t}", "Treat as text", "Treat as categorical"],
            })
        if t == 'currency' and not cur_code:
            doubts.append({
                'id': f"currency__{col}", 'kind': 'currency',
                'column': col,
                'message': (f"**{col}** looks like currency but I couldn't "
                            "detect a currency code."),
                'options': ['USD', 'EUR', 'GBP', 'SAR', 'AED'],
            })
        if t in ('date', 'datetime') and df is not None and col in df.columns:
            try:
                vals = df[col].dropna().astype(str).head(60)
            except Exception:
                vals = []
            ambig = 0
            for v in vals:
                m = _DATE_AMBIG_RE.match(v)
                if (m and 1 <= int(m.group(1)) <= 12
                        and 1 <= int(m.group(2)) <= 12
                        and m.group(1) != m.group(2)):
                    ambig += 1
            if ambig >= 3:
                doubts.append({
                    'id': f"date_format__{col}", 'kind': 'date_format',
                    'column': col,
                    'message': (f"`{col}` could be parsed as either day-first "
                                "or month-first dates."),
                    'options': ['Day first (DMY)', 'Month first (MDY)'],
                })
    if cleaning_report:
        for sub in cleaning_report.get('substeps', []):
            key = sub.get('key')
            details = sub.get('details') or {}
            for c in details.get('changes', []):
                if key == 'clip_outliers' and 'left as-is' in c:
                    m = re.search(r'`([^`]+)`', c)
                    col_name = m.group(1) if m else ''
                    doubts.append({
                        'id': f"outlier__{col_name or len(doubts)}",
                        'kind': 'outlier', 'column': col_name,
                        'message': f"Possible outliers: {c}",
                        'options': ['Clip anyway', 'Leave as-is'],
                    })
                if key in ('fill_missing_numeric', 'fill_missing_categorical') \
                        and c.startswith('Skipped'):
                    m = re.search(r'`([^`]+)`.*?([\d.]+)%', c)
                    if not m:
                        continue
                    col_name = m.group(1)
                    pct = m.group(2)
                    flavour = ('numeric' if key == 'fill_missing_numeric'
                               else 'categorical')
                    doubts.append({
                        'id': f"missing__{col_name}",
                        'kind': 'missing', 'column': col_name,
                        'flavour': flavour,
                        'message': (f"`{col_name}` has {pct}% missing values — "
                                    "above the safety cap, so I left it alone. "
                                    "How should I handle it?"),
                        'options': ['Fill anyway', 'Drop column', 'Leave as-is'],
                    })
            if key == 'remove_duplicates':
                rows_removed = details.get('rows_removed') or 0
                total = (cleaning_report.get('original_rows') or 0)
                if total and rows_removed / max(total, 1) > 0.20:
                    pct = int(round(100 * rows_removed / total))
                    doubts.append({
                        'id': "duplicates__bulk",
                        'kind': 'duplicates', 'column': '',
                        'rows_removed': int(rows_removed),
                        'message': (f"I removed {rows_removed:,} duplicate rows "
                                    f"({pct}% of the dataset). Keep them removed?"),
                        'options': ['Keep removed', 'Restore duplicates'],
                    })
    return doubts


def _match_freetext_to_doubt(prompt, doubts):
    """Heuristic: route a chat message to one of the active doubts.

    Returns (doubt, answer_label) or (None, None). We match on the column
    name plus an option keyword, falling back to kind-specific cues
    (currency code regex, type keywords, day/month for dates, etc.).
    """
    if not prompt or not doubts:
        return None, None
    p = prompt.lower()
    for d in doubts:
        col = (d.get('column') or '').lower()
        if col and col not in p:
            continue
        for opt in d.get('options') or []:
            opt_l = opt.lower()
            if opt_l in p:
                return d, opt
            tokens = [t for t in re.split(r'\W+', opt_l) if len(t) > 2]
            if tokens and all(t in p for t in tokens):
                return d, opt
    for d in doubts:
        col = (d.get('column') or '').lower()
        if col and col not in p:
            continue
        if d['kind'] == 'currency':
            m = re.search(
                r'\b(USD|EUR|GBP|SAR|AED|JPY|CNY|KWD|QAR|BHD|OMR|JOD|EGP|ILS|TRY|CAD|AUD|CHF)\b',
                prompt, re.IGNORECASE)
            if m:
                return d, m.group(1).upper()
        elif d['kind'] == 'type':
            for kw in ('text', 'categorical', 'integer', 'decimal',
                       'number', 'date'):
                if kw in p:
                    return d, ('Treat as text' if kw == 'text'
                               else 'Treat as categorical')
        elif d['kind'] == 'date_format':
            if 'day' in p or 'dmy' in p:
                return d, 'Day first (DMY)'
            if 'month' in p or 'mdy' in p:
                return d, 'Month first (MDY)'
        elif d['kind'] == 'missing':
            if 'drop' in p:
                return d, 'Drop column'
            if 'fill' in p or 'impute' in p:
                return d, 'Fill anyway'
            if 'leave' in p or 'keep' in p:
                return d, 'Leave as-is'
        elif d['kind'] == 'outlier':
            if 'clip' in p or 'cap' in p:
                return d, 'Clip anyway'
            if 'leave' in p or 'keep' in p:
                return d, 'Leave as-is'
        elif d['kind'] == 'duplicates':
            if 'restore' in p or 'keep' in p and 'dup' in p:
                return d, 'Restore duplicates'
            if 'remov' in p:
                return d, 'Keep removed'
    return None, None


def _seed_chat_doubts(ds_id, doubts):
    """Prepend a single grouped doubt message to chat, once per dataset load."""
    if not doubts:
        return
    seeded = st.session_state.setdefault('chat_doubts_seeded', set())
    if ds_id in seeded:
        return
    lines = ["Here's what I auto-applied where I wasn't fully sure:"]
    for d in doubts[:6]:
        lines.append(f"• {d['message']}")
    if len(doubts) > 6:
        lines.append(f"…and {len(doubts) - 6} more.")
    lines.append("Tap a quick reply below to confirm any of these.")
    st.session_state.chat_messages.insert(0, {
        'role': 'assistant',
        'content': '\n\n'.join(lines),
    })
    seeded.add(ds_id)


def _resolve_doubt_in_chat(doubt, answer):
    """Apply a chat-resolved doubt back into the active pipeline.

    Returns (mutated, reply_text). `mutated` is True when the pipeline
    was actually rebuilt or an Applied Step was added; `reply_text` is
    the assistant message shown in chat.
    """
    sh = _get_step_history(create=False)
    if sh is None or sh.is_empty():
        return False, "No active dataset."
    ds_key = _ds_key()
    ans = (answer or '').lower()
    kind = doubt['kind']
    col = doubt.get('column') or ''

    if kind == 'type':
        if 'text' in ans:
            target_type = 'text'
        elif 'categorical' in ans:
            target_type = 'categorical'
        elif 'keep' in ans:
            return False, (f"Kept `{col}` as `{doubt.get('value')}` — "
                           "no pipeline change.")
        else:
            return False, ("I didn't catch that — please pick one of: "
                           + ", ".join(doubt.get('options') or []))
        if sh.has_later_steps():
            sh.drop_later()
        base_df = sh.current_df().copy()
        if col in base_df.columns:
            base_df[col] = cast_column(base_df[col], target_type)
        new_schema = infer_schema(base_df)
        sh.add(
            "Changed Type (manual)",
            f"Column `{col}` retyped to `{target_type}` (chat)",
            base_df,
            meta={'override': {col: target_type},
                  'schema': [s.to_dict() for s in new_schema]},
        )
        st.session_state.inferred_schema[ds_key] = [s.to_dict() for s in new_schema]
        st.session_state.type_overrides.setdefault(ds_key, {})[col] = target_type
        st.session_state.df_cleaned = base_df
        try: _persist_step_history()
        except Exception: pass
        return True, (f"Applied — `{col}` is now `{target_type}` and saved as "
                      "a new step in Applied Steps.")

    if kind == 'currency':
        code = (answer or '').strip().upper()
        if not code or len(code) > 6:
            return False, "Please reply with a currency code like USD or EUR."
        # Source the most recent schema-carrying meta. The post-cleaning
        # active step often has no `schema` key, so fall back to the
        # canonical inferred_schema in session state, then walk the
        # history backwards as a last resort.
        sch = [dict(s) for s in
               (st.session_state.inferred_schema.get(ds_key) or [])]
        if not sch:
            for s in reversed(sh.steps):
                m = (s.meta or {}).get('schema')
                if m:
                    sch = [dict(x) for x in m]
                    break
        found = False
        for s in sch:
            if s.get('column') == col:
                s['inferred_type'] = 'currency'
                s['currency_code'] = code
                found = True
        if not found:
            sch.append({'column': col, 'inferred_type': 'currency',
                        'currency_code': code, 'confidence': 1.0,
                        'sample_values': [], 'notes': 'set via chat'})
        if sh.has_later_steps():
            sh.drop_later()
        base_df = sh.current_df().copy()
        sh.add(
            "Changed Type (manual)",
            f"Set currency for `{col}` to `{code}` (chat)",
            base_df,
            meta={'override': {col: 'currency'},
                  'currency_code': {col: code},
                  'schema': sch},
        )
        st.session_state.inferred_schema[ds_key] = sch
        # Track the override so downstream formatting / replay sees it.
        ov = st.session_state.type_overrides.setdefault(ds_key, {})
        ov[col] = 'currency'
        cur_map = st.session_state.setdefault('currency_codes', {})
        cur_map.setdefault(ds_key, {})[col] = code
        try: _persist_step_history()
        except Exception: pass
        return True, (f"Set `{col}` currency to `{code}` and saved it as a "
                      "new step in Applied Steps.")

    if kind == 'date_format':
        prefer_day = 'day' in ans or 'dmy' in ans
        prefer_month = 'month' in ans or 'mdy' in ans
        if not (prefer_day or prefer_month):
            return False, "Please pick day-first or month-first."
        if sh.has_later_steps():
            sh.drop_later()
        base_df = sh.current_df().copy()
        if col in base_df.columns:
            try:
                base_df[col] = pd.to_datetime(
                    base_df[col], errors='coerce',
                    dayfirst=prefer_day, yearfirst=False)
            except Exception:
                pass
        new_schema = infer_schema(base_df)
        label = 'day-first' if prefer_day else 'month-first'
        sh.add(
            "Changed Type (manual)",
            f"Reparsed `{col}` as date ({label}) (chat)",
            base_df,
            meta={'override': {col: 'date'},
                  'date_format': {col: 'dayfirst' if prefer_day else 'monthfirst'},
                  'schema': [s.to_dict() for s in new_schema]},
        )
        st.session_state.inferred_schema[ds_key] = [s.to_dict() for s in new_schema]
        st.session_state.df_cleaned = base_df
        try: _persist_step_history()
        except Exception: pass
        return True, f"Reparsed `{col}` as {label} dates and saved as a new step."

    if kind == 'outlier':
        if 'leave' in ans or 'as-is' in ans:
            return False, "Left outliers as-is — no change."
        if 'clip' not in ans and 'cap' not in ans:
            return False, "Please reply with Clip anyway or Leave as-is."
        plan = _build_unified_plan(sh)
        new_plan, mutated = [], False
        for e in plan:
            meta = e.get('meta_extra') or {}
            if (e.get('kind') == 'cleaning_substep'
                    and meta.get('substep_key') == 'clip_outliers'):
                params = dict(e.get('params') or {})
                params['clip_threshold_pct'] = 100.0
                new_plan.append({**e, 'params': params,
                                 'meta_extra': {**meta, 'substep_params': params}})
                mutated = True
            else:
                new_plan.append(e)
        if not mutated:
            return False, "Couldn't find a Clip Outliers step to update."
        _commit_unified_plan(sh, new_plan, ds_key)
        return True, ("Raised the outlier cap to 100% — all detected outliers "
                      "are now clipped. Pipeline rebuilt.")

    if kind == 'missing':
        flavour = doubt.get('flavour', 'numeric')
        substep_key = ('fill_missing_numeric' if flavour == 'numeric'
                       else 'fill_missing_categorical')
        if 'leave' in ans or 'keep as' in ans:
            return False, f"Left `{col}` untouched — no change."
        plan = _build_unified_plan(sh)
        if 'drop' in ans:
            new_entry = {
                "instance_id": f"drop__{col}__{int(time.time()*1000)}",
                "kind": "cleaning_substep",
                "name": f"Drop Column · {col}",
                "summary": f"Dropped `{col}` (chat)",
                "enabled": True,
                "params": {"column": col},
                "meta_extra": {"substep_key": "drop_column",
                               "substep_params": {"column": col}},
            }
            _commit_unified_plan(sh, plan + [new_entry], ds_key)
            return True, (f"Dropped `{col}` from the dataset. Pipeline rebuilt "
                          "and saved as a new step.")
        if 'fill' in ans or 'impute' in ans or 'anyway' in ans:
            new_plan, mutated = [], False
            for e in plan:
                meta = e.get('meta_extra') or {}
                if (e.get('kind') == 'cleaning_substep'
                        and meta.get('substep_key') == substep_key):
                    params = dict(e.get('params') or {})
                    params['missing_cap_pct'] = 100.0
                    new_plan.append({**e, 'params': params,
                                     'meta_extra': {**meta,
                                                    'substep_params': params}})
                    mutated = True
                else:
                    new_plan.append(e)
            if not mutated:
                return False, "Couldn't find the matching Fill Missing step."
            _commit_unified_plan(sh, new_plan, ds_key)
            return True, (f"Raised the missing-value cap to 100% — `{col}` "
                          "will now be imputed. Pipeline rebuilt.")
        return False, "Please reply with Fill anyway, Drop column, or Leave as-is."

    if kind == 'duplicates':
        plan = _build_unified_plan(sh)
        if 'restore' in ans:
            new_plan, mutated = [], False
            for e in plan:
                meta = e.get('meta_extra') or {}
                if (e.get('kind') == 'cleaning_substep'
                        and meta.get('substep_key') == 'remove_duplicates'):
                    new_plan.append({**e, 'enabled': False})
                    mutated = True
                else:
                    new_plan.append(e)
            if not mutated:
                return False, "Couldn't find the Remove Duplicates step."
            _commit_unified_plan(sh, new_plan, ds_key)
            return True, ("Restored duplicate rows — Remove Duplicates is "
                          "disabled. Pipeline rebuilt.")
        return False, (f"Kept duplicates removed — no change.")

    return False, "Noted."


def _render_phase1_dock(tab_id, limits):
    """Render the auto-applied status strip, doubt notes, and chat dock.

    Mounted on the Cleaning, Statistics, and ML tabs so users always see
    what Phase 1 did, can review the controls in place, and can resolve
    any doubts via chat (when their plan includes it).
    """
    sh = _get_step_history()
    if sh is None or sh.is_empty():
        return
    ds_key = _ds_key()
    plan_now = _build_unified_plan(sh)
    n_clean = sum(1 for e in plan_now
                  if e['kind'] == 'cleaning_substep' and e.get('enabled', True))
    n_typed = sum(1 for e in plan_now
                  if e['kind'] in ('changed_type', 'manual_type'))
    schema_dicts = []
    for s in sh.steps:
        meta = s.meta or {}
        if meta.get('schema'):
            schema_dicts = meta['schema']
    doubts = _detect_dataset_doubts(
        schema_dicts, st.session_state.get('cleaning_report'),
        df=_active_df())
    st.session_state.dataset_doubts = doubts
    if limits.get('ai_chat_enabled'):
        _seed_chat_doubts(ds_key, doubts)

    bits = []
    if n_clean:
        bits.append(f"{n_clean} cleaning step{'s' if n_clean != 1 else ''} applied")
    if n_typed:
        bits.append(f"{n_typed} type pass{'es' if n_typed != 1 else ''} run")
    if not bits:
        bits.append("Phase 1 ran")
    summary = " · ".join(bits)
    if doubts:
        summary += f" · {len(doubts)} doubt{'s' if len(doubts) != 1 else ''}"

    strip_l, strip_r = st.columns([0.78, 0.22])
    with strip_l:
        st.markdown(
            "<div style='padding:0.5rem 0.85rem;border:1px solid rgba(45,212,191,0.18);"
            "border-radius:10px;background:rgba(45,212,191,0.04);color:#cbd5e1;"
            "font-size:0.88rem;'>"
            "<span style='color:#2dd4bf;font-family:JetBrains Mono,monospace;"
            f"font-size:0.72rem;letter-spacing:0.16em;'>AUTO-APPLIED</span> · {summary}"
            "</div>",
            unsafe_allow_html=True,
        )
    with strip_r:
        review_open = st.toggle(
            "Review", value=False, key=f"review_open_{tab_id}_{ds_key}",
            help="Phase 1 controls — steps, parameters, type overrides, "
                 "display preferences — live on the Overview tab.",
        )
    if review_open:
        st.info("Open the **Overview** tab — the Applied Steps panel, type "
                "overrides, and display preferences are all there. Every "
                "former click is still available, just no longer required.")

    for d in doubts[:5]:
        cta = ("confirm in chat below" if limits.get('ai_chat_enabled')
               else "open Review to confirm")
        st.markdown(
            "<div style='padding:0.5rem 0.85rem;margin-top:0.4rem;"
            "border-left:3px solid #f59e0b;background:rgba(245,158,11,0.06);"
            "border-radius:0 6px 6px 0;color:#e2e8f0;font-size:0.85rem;'>"
            f"<b style='color:#f59e0b;'>DataVision wasn't sure:</b> "
            f"{d['message']} — {cta}.</div>",
            unsafe_allow_html=True,
        )

    _render_chat_dock(tab_id, limits, doubts)


def _render_chat_dock(tab_id, limits, doubts):
    """Persistent chat dock shared across the Phase-1 tabs."""
    if not limits.get('ai_chat_enabled'):
        with st.expander("Chat with DataVision (Tier 3)", expanded=False):
            st.caption("AI chat is part of Tier 3. The doubts above stay "
                       "visible as inline notes — open Review on each tab "
                       "to confirm them manually.")
        return

    expanded_default = bool(doubts)
    with st.expander("Chat with DataVision", expanded=expanded_default):
        st.caption("Same conversation across Cleaning, Statistics, and ML tabs.")
        chat_box = st.container(height=300)
        with chat_box:
            if not st.session_state.chat_messages:
                st.caption("Ask anything about your dataset.")
            for msg in st.session_state.chat_messages:
                role_label = "You" if msg["role"] == "user" else "DataVision"
                bg = ("rgba(45,212,191,0.10)" if msg["role"] == "user"
                      else "rgba(30,41,59,0.6)")
                content = (msg.get("content") or "").replace("\n", "<br>")
                st.markdown(
                    f"<div style='padding:0.55rem 0.8rem;margin:0.25rem 0;"
                    f"background:{bg};border-radius:8px;color:#e2e8f0;"
                    f"font-size:0.88rem;'>"
                    f"<b style='color:#94a3b8;font-size:0.7rem;letter-spacing:0.1em;"
                    f"text-transform:uppercase;'>{role_label}</b><br>{content}</div>",
                    unsafe_allow_html=True,
                )
        if doubts:
            st.markdown("**Quick replies**")
            for d in doubts[:5]:
                st.caption(d['message'])
                opts = d.get('options') or []
                cols = st.columns(max(1, len(opts)))
                for j, opt in enumerate(opts):
                    with cols[j]:
                        if st.button(opt, key=f"qr_{tab_id}_{d['id']}_{j}",
                                     use_container_width=True):
                            user_msg = (f"For `{d['column']}`: {opt}"
                                        if d['column'] else opt)
                            st.session_state.chat_messages.append(
                                {"role": "user", "content": user_msg})
                            _, reply = _resolve_doubt_in_chat(d, opt)
                            st.session_state.chat_messages.append(
                                {"role": "assistant", "content": reply})
                            try:
                                db = get_db()
                                save_chat_message(
                                    db, st.session_state.current_dataset_id,
                                    user_msg, reply)
                                db.close()
                            except Exception:
                                pass
                            st.rerun()
        prompt = st.chat_input("Ask DataVision...",
                               key=f"dock_chat_{tab_id}_{_ds_key()}")
        if prompt:
            st.session_state.chat_messages.append(
                {"role": "user", "content": prompt})
            matched_doubt, matched_answer = _match_freetext_to_doubt(
                prompt, doubts)
            if matched_doubt is not None:
                _, response = _resolve_doubt_in_chat(matched_doubt, matched_answer)
            else:
                df_chat = _active_df()
                df_info = {
                    'row_count': len(df_chat),
                    'column_count': len(df_chat.columns),
                    'columns': df_chat.columns.tolist(),
                    'dtypes': df_chat.dtypes.astype(str).to_dict(),
                    'numeric_summary': (df_chat.describe().to_dict()
                        if not df_chat.select_dtypes(include=[np.number]).empty
                        else {}),
                }
                with st.spinner("Thinking..."):
                    response = chat_about_data(prompt, df_info)
            st.session_state.chat_messages.append(
                {"role": "assistant", "content": response})
            try:
                db = get_db()
                save_chat_message(db, st.session_state.current_dataset_id,
                                  prompt, response)
                db.close()
            except Exception:
                pass
            st.rerun()


def _new_instance_id() -> str:
    import uuid
    return uuid.uuid4().hex[:10]


def _default_cleaning_plan() -> list:
    """Build the default ordered cleaning plan (all enabled, params seeded
    from `SUBSTEP_PARAM_SCHEMA` defaults so the UI has values to render)."""
    defaults = default_substep_params()
    return [
        {"instance_id": _new_instance_id(), "key": k,
         "enabled": True, "params": dict(defaults.get(k, {}))}
        for k in DEFAULT_CLEANING_PLAN
    ]


def _get_cleaning_plan(ds_key: str) -> list:
    plans = st.session_state.cleaning_substep_plans
    if ds_key not in plans:
        # Migrate from legacy enabled-map form if present.
        legacy = st.session_state.cleaning_substep_states.get(ds_key)
        plan = _default_cleaning_plan()
        if isinstance(legacy, dict):
            for entry in plan:
                if entry["key"] in legacy:
                    entry["enabled"] = bool(legacy[entry["key"]])
        plans[ds_key] = plan
    return plans[ds_key]


def _apply_cleaning_substeps(history: StepHistory, base_df,
                             plan: list) -> tuple:
    """Append one Step per cleaning substep onto `history`, then return
    (final_df, aggregated_report). Disabled substeps still appear as
    pass-through entries so the user can flip them back on later.

    `plan` is an ordered list of {instance_id, key, enabled, params} dicts.
    Each entry's `params` carries the substep's threshold knobs (e.g.
    missing-value cap %, IQR multiplier); missing keys fall back to
    `SUBSTEP_PARAM_SCHEMA` defaults inside the substep functions.
    """
    report = {
        'original_rows': len(base_df),
        'original_columns': len(base_df.columns),
        'changes': [],
        'substeps': [],
    }
    current = base_df
    for entry in plan:
        key = entry["key"]
        params = entry.get("params") or {}
        on = bool(entry.get("enabled", True))
        label = substep_label(key, params)
        if on:
            current, summary, details = run_substep(key, current, params)
            report['changes'].extend(details.get('changes', []))
        else:
            summary, details = "Disabled — pass through", {}
        # Effective threshold params after default merge — recorded on the
        # Step.meta and report so downstream consumers (UI, persistence)
        # always see the values that were actually used.
        effective_params = {
            p["key"]: params.get(p["key"], p["default"])
            for p in SUBSTEP_PARAM_SCHEMA.get(key, [])
        }
        history.add(label, summary, current,
                    meta={'substep_key': key,
                          'substep_instance': entry["instance_id"],
                          'substep_params': params,
                          'effective_params': effective_params,
                          'enabled': on, 'details': details})
        report['substeps'].append({
            'key': key, 'label': label, 'enabled': on,
            'instance_id': entry["instance_id"],
            'params': params,
            'effective_params': effective_params,
            'summary': summary, 'details': details,
        })
    report['final_rows'] = len(current)
    report['final_columns'] = len(current.columns)
    report['rows_removed'] = report['original_rows'] - report['final_rows']
    return current, report


def _rebuild_cleaning_substeps(sh: StepHistory, plan: list):
    """Rebuild the contiguous cleaning block at the tail of `sh`.

    Drops every step from the first cleaning substep onward (this also
    discards any later manual edits, mirroring `drop_later` semantics
    elsewhere), then re-applies all substeps from `plan`.
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
    final_df, report = _apply_cleaning_substeps(sh, base_df, plan)
    sh.active_index = len(sh.steps) - 1
    return final_df, report


# ── Universal step plan (Power Query-style for ALL step kinds) ─────────────
# The cleaning-substep mechanic (reorder / toggle / remove + rebuild) is
# generalised here to every non-source step in the history: Promoted Headers,
# Changed Type, every cleaning substep, and every manual override. Source
# is pinned at index 0 and locked out of all controls.
#
# A "unified plan" is just the post-source steps reduced to a list of
# entries that the replay engine knows how to execute against Source.df.

_UNIVERSAL_KIND_BY_NAME = {
    "Promoted Headers": "promoted_headers",
    "Changed Type": "changed_type",
    "Changed Type (manual)": "manual_type",
}


def _step_kind(step) -> str:
    meta = step.meta or {}
    if meta.get("substep_key"):
        return "cleaning_substep"
    return _UNIVERSAL_KIND_BY_NAME.get(step.name, "custom")


def _step_instance_id(step) -> str:
    meta = step.meta or {}
    inst = meta.get("substep_instance") or meta.get("step_instance")
    if not inst:
        inst = _new_instance_id()
        meta["step_instance"] = inst
        step.meta = meta
    return inst


def _build_unified_plan(sh: StepHistory) -> list:
    """Derive a unified plan (excluding Source) from the current StepHistory."""
    plan = []
    for i, s in enumerate(sh.steps):
        if i == 0:
            continue
        meta = dict(s.meta or {})
        kind = _step_kind(s)
        plan.append({
            "instance_id": _step_instance_id(s),
            "kind": kind,
            "name": s.name,
            "summary": s.summary,
            "enabled": bool(meta.get("enabled", True)),
            "params": meta.get("substep_params") or {},
            "meta_extra": meta,
        })
    return plan


REPLAY_CACHE_MAX = 10


def _plan_entry_hash(entry: dict) -> str:
    """Stable per-entry hash: kind + enabled + instance_id + params + meta_extra."""
    payload = {
        "kind": entry.get("kind"),
        "enabled": bool(entry.get("enabled", True)),
        "instance_id": entry.get("instance_id"),
        "params": entry.get("params") or {},
        "meta_extra": entry.get("meta_extra") or {},
    }
    try:
        s = json.dumps(payload, sort_keys=True, default=str)
    except Exception:
        s = repr(payload)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def _source_seed_hash(df) -> str:
    """Cheap fingerprint for the source df so distinct sources don't share cache."""
    if df is None:
        return "none"
    try:
        return hashlib.sha1(
            f"{df.shape}|{list(df.columns)}".encode("utf-8")
        ).hexdigest()
    except Exception:
        return "none"


def _get_replay_cache(ds_key) -> "OrderedDict":
    caches = st.session_state.plan_replay_cache
    cache = caches.get(ds_key)
    if cache is None:
        cache = OrderedDict()
        caches[ds_key] = cache
    return cache


def _replay_unified_plan(sh: StepHistory, plan: list):
    """Replay an ordered, enable-aware plan onto sh.steps[0].df.

    Returns (new_steps, cleaning_report). Disabled non-source steps are
    pass-through (df copied unchanged) so they remain visible in the
    Applied Steps panel and can be re-enabled later.

    Uses a per-dataset LRU cache keyed by prefix hash so that toggling /
    reordering / removing a step only re-executes that step and the
    entries downstream of it. The cache is invisible to callers — the
    returned (new_steps, report) shape is unchanged.
    """
    if not sh.steps:
        return None, None
    source_step = sh.steps[0]
    new_steps = [source_step]
    current = source_step.df.copy() if source_step.df is not None else None

    cleaning_report = {
        'original_rows': len(current) if current is not None else 0,
        'original_columns': len(current.columns) if current is not None else 0,
        'changes': [],
        'substeps': [],
    }
    saw_cleaning = False

    # Compute prefix hashes so we can short-circuit on any cached prefix.
    ds_key = _ds_key()
    cache = _get_replay_cache(ds_key)
    src_seed = _source_seed_hash(source_step.df)
    entry_hashes = [_plan_entry_hash(e) for e in plan]
    prefix_hashes = []
    acc = src_seed
    for eh in entry_hashes:
        acc = hashlib.sha1((acc + "|" + eh).encode("utf-8")).hexdigest()
        prefix_hashes.append(acc)

    start_index = 0
    for i in range(len(prefix_hashes) - 1, -1, -1):
        if prefix_hashes[i] in cache:
            cached = cache[prefix_hashes[i]]
            cache.move_to_end(prefix_hashes[i])
            new_steps = [source_step] + [
                Step(
                    name=s['name'],
                    summary=s['summary'],
                    df=s['df'],
                    meta=dict(s['meta'] or {}),
                )
                for s in cached['steps']
            ]
            last_df = cached['steps'][-1]['df'] if cached['steps'] else None
            current = last_df.copy() if last_df is not None else None
            cleaning_report = copy.deepcopy(cached['cleaning_report'])
            saw_cleaning = cached['saw_cleaning']
            start_index = i + 1
            break

    for idx in range(start_index, len(plan)):
        entry = plan[idx]
        kind = entry["kind"]
        enabled = bool(entry.get("enabled", True))
        instance_id = entry["instance_id"]
        params = entry.get("params") or {}
        meta_extra = dict(entry.get("meta_extra") or {})
        # Drop runtime fields we'll re-derive so they don't go stale.
        for k in ("enabled", "details", "effective_params", "step_instance",
                  "substep_instance", "substep_params"):
            meta_extra.pop(k, None)

        name = entry.get("name") or "Step"
        summary = entry.get("summary") or ""
        meta = {**meta_extra, "enabled": enabled, "step_instance": instance_id}

        if kind == "promoted_headers":
            if enabled and current is not None and len(current) > 0 and (
                all(str(c).startswith("Column") for c in current.columns)
            ):
                promoted = current.iloc[1:].reset_index(drop=True)
                promoted.columns = [str(v) for v in current.iloc[0].tolist()]
                current = promoted
                summary = "First row promoted to column names"
            elif not enabled:
                summary = "Disabled — pass through (headers not promoted)"
            name = "Promoted Headers"

        elif kind == "changed_type":
            schema_dicts = meta_extra.get("schema") or []
            schema = [ColumnType(**{
                "column": d.get("column"),
                "inferred_type": d.get("inferred_type", "text"),
                "confidence": float(d.get("confidence", 0.0)),
                "sample_values": list(d.get("sample_values") or []),
                "notes": d.get("notes", "") or "",
            }) for d in schema_dicts if d.get("column") is not None]
            if enabled and schema and current is not None:
                current = apply_schema(current, schema)
            elif not enabled:
                summary = "Disabled — pass through (types not applied)"
            name = "Changed Type"

        elif kind == "cleaning_substep":
            key = meta_extra.get("substep_key")
            label = substep_label(key, params)
            if enabled and key in SUBSTEP_FUNCS and current is not None:
                current, summary, details = run_substep(key, current, params)
                cleaning_report['changes'].extend(details.get('changes', []))
            else:
                summary = "Disabled — pass through" if not enabled else "Skipped — unknown substep"
                details = {}
            effective_params = {
                p["key"]: params.get(p["key"], p["default"])
                for p in SUBSTEP_PARAM_SCHEMA.get(key, [])
            }
            meta = {
                **meta_extra,
                "substep_key": key,
                "substep_instance": instance_id,
                "substep_params": params,
                "effective_params": effective_params,
                "enabled": enabled,
                "details": details,
            }
            name = label
            saw_cleaning = True
            cleaning_report['substeps'].append({
                "key": key, "label": label, "enabled": enabled,
                "instance_id": instance_id,
                "params": params, "effective_params": effective_params,
                "summary": summary, "details": details,
            })

        elif kind == "manual_type":
            override = meta_extra.get("override") or {}
            if enabled and override and current is not None:
                base = current.copy()
                for col, t in override.items():
                    if col in base.columns:
                        base[col] = cast_column(base[col], t)
                current = base
            elif not enabled:
                summary = "Disabled — pass through (override not applied)"
            name = "Changed Type (manual)"

        snap = current.copy() if current is not None else current
        new_steps.append(Step(name=name, summary=summary, df=snap, meta=meta))

        # Memoise this prefix so future replays can short-circuit to it.
        cache[prefix_hashes[idx]] = {
            'steps': [
                {'name': s.name, 'summary': s.summary, 'df': s.df, 'meta': s.meta}
                for s in new_steps[1:]
            ],
            'cleaning_report': copy.deepcopy(cleaning_report),
            'saw_cleaning': saw_cleaning,
        }
        cache.move_to_end(prefix_hashes[idx])
        while len(cache) > REPLAY_CACHE_MAX:
            cache.popitem(last=False)

    if current is not None:
        cleaning_report['final_rows'] = len(current)
        cleaning_report['final_columns'] = len(current.columns)
        cleaning_report['rows_removed'] = (
            cleaning_report['original_rows'] - cleaning_report['final_rows']
        )
    return new_steps, (cleaning_report if saw_cleaning else None)


def _commit_unified_plan(sh: StepHistory, plan: list, ds_key) -> None:
    """Apply a new unified plan: rebuild every step from Source down,
    refresh df / df_cleaned / cleaning_report, keep cleaning_substep_plans
    (the legacy insert UI's source of truth) in sync, and persist."""
    new_steps, report = _replay_unified_plan(sh, plan)
    if new_steps is None:
        return
    prev_active = sh.active_index
    sh.steps = new_steps
    if prev_active >= len(new_steps):
        sh.active_index = len(new_steps) - 1
    else:
        sh.active_index = max(0, prev_active)

    # Keep the cleaning-only plan (used by the Insert UI) in sync.
    cleaning_only = [
        {"instance_id": e["instance_id"],
         "key": (e.get("meta_extra") or {}).get("substep_key"),
         "enabled": e["enabled"],
         "params": dict(e.get("params") or {})}
        for e in plan if e["kind"] == "cleaning_substep"
    ]
    st.session_state.cleaning_substep_plans[ds_key] = cleaning_only
    st.session_state.cleaning_substep_states[ds_key] = {
        e["key"]: e["enabled"] for e in cleaning_only if e["key"]
    }

    # Refresh dashboard-facing dataframes from the rebuilt history.
    last_typed = None
    last_cleaning = None
    for s in new_steps:
        if s.name in ("Changed Type", "Changed Type (manual)"):
            last_typed = s
        if (s.meta or {}).get("substep_key"):
            last_cleaning = s
    if last_typed is not None:
        st.session_state.df = last_typed.df
    elif len(new_steps) >= 2:
        st.session_state.df = new_steps[1].df
    elif new_steps:
        # Only Source survived — keep df in sync so dashboard tabs that
        # read st.session_state.df directly don't show a stale frame.
        st.session_state.df = new_steps[0].df
    if last_cleaning is not None:
        st.session_state.df_cleaned = last_cleaning.df
    else:
        st.session_state.df_cleaned = new_steps[-1].df if new_steps else None
    if report is not None:
        st.session_state.cleaning_report = report

    _persist_step_history()


# --------------------------------------------------------------------------
# Proactive Question Bar
# --------------------------------------------------------------------------
# Detector + UI for the "DataVision asks when uncertain" panel. Runs over
# the active dataframe + inferred schema, surfaces rule-based doubts
# (mixed dtypes, ambiguous date format, multi-currency column,
# Hijri-flagged columns, near-duplicate rows) and writes the chosen
# answer either as a real cleaning substep or as a recorded decision.

from proactive_questions import (
    Question, QuestionOption, detect_questions, resolve_answer,
)


def _proactive_state(ds_key: str) -> dict:
    """Per-dataset bag holding answered/skipped question ids and any
    free-form decisions the user made (kept so we can render an "X
    decided" line in the future without re-asking)."""
    bag = st.session_state.setdefault("proactive_questions", {})
    return bag.setdefault(str(ds_key), {"answered": {}, "skipped": set()})


def _apply_question_substep(ds_key: str, sh: StepHistory,
                            substep_key: str, params: dict) -> None:
    """Append a new cleaning substep to the unified plan, then rebuild.

    Mirrors what the Insert UI does, but at module level so the panel
    can be mounted from any tab. The substep lands at the end of the
    cleaning block so previously-decided steps keep their order."""
    if not sh:
        return
    plan = _build_unified_plan(sh)
    new_entry = {
        "instance_id": _new_instance_id(),
        "kind": "cleaning_substep",
        "name": substep_label(substep_key, params or {}),
        "summary": "",
        "enabled": True,
        "params": dict(params or {}),
        "meta_extra": {"substep_key": substep_key,
                       "origin": "proactive_question"},
    }
    # Insert after the last existing cleaning step, otherwise at the end.
    last_clean = -1
    for i, e in enumerate(plan):
        if e.get("kind") == "cleaning_substep":
            last_clean = i
    insert_at = last_clean + 1 if last_clean >= 0 else len(plan)
    plan.insert(insert_at, new_entry)
    _commit_unified_plan(sh, plan, ds_key)


def _render_questions_panel(ds_key: str, sh: StepHistory,
                            view_df, location: str) -> None:
    """Render the proactive question bar for the active dataset.

    `location` is a short string ("cleaning", "transform") used to
    namespace widget keys so the same question can be rendered in two
    panels without Streamlit complaining about duplicate keys.
    """
    if view_df is None or getattr(view_df, "empty", True):
        return
    schema = st.session_state.inferred_schema.get(ds_key)
    try:
        questions = detect_questions(view_df, schema=schema, ds_key=str(ds_key))
    except Exception:
        # The detector is best-effort: a single broken column shouldn't
        # take down the panel. Surface nothing rather than crash.
        return
    state = _proactive_state(ds_key)
    answered_ids = set(state["answered"].keys())
    skipped_ids = set(state["skipped"])
    open_qs = [q for q in questions
               if q.id not in answered_ids and q.id not in skipped_ids]
    if not open_qs:
        return

    st.markdown(
        f"**Questions from DataVision** · {len(open_qs)} open"
    )
    st.caption("Pick an answer to record the decision as a step. "
               "Skip to dismiss for this session.")
    for q in open_qs:
        with st.container(border=True):
            st.markdown(f"**{q.prompt}**")
            st.caption(q.context)
            cols = st.columns(max(1, len(q.options)))
            for i, opt in enumerate(q.options):
                btn_key = f"pq_{location}_{q.id}_{i}"
                btn_type = "primary" if opt.is_default else "secondary"
                if cols[i].button(opt.label, key=btn_key, type=btn_type,
                                  use_container_width=True):
                    if opt.action == "skip":
                        state["skipped"].add(q.id)
                        st.rerun()
                    else:
                        request = resolve_answer(q, opt)
                        if request and sh is not None:
                            _apply_question_substep(
                                ds_key, sh,
                                request["substep_key"],
                                request.get("params") or {},
                            )
                        state["answered"][q.id] = {
                            "kind": q.kind,
                            "label": opt.label,
                            "action": opt.action,
                            "payload": opt.payload,
                            "applied_substep": (request or {}).get("substep_key"),
                        }
                        st.rerun()


# --------------------------------------------------------------------------
# Transform Toolkit form renderer
# --------------------------------------------------------------------------
# One reusable widget tree per transform substep. Used both when inserting
# a new transform via the "Transform" expander on the Overview tab and when
# editing an already-inserted transform via the per-step Parameters panel.
# Returns the current widget state as a JSON-friendly params dict; the
# caller is responsible for the commit button + plan splice.

_COND_OPS_UI = ["==", "!=", "<", "<=", ">", ">=",
                "contains", "starts_with", "ends_with", "is_null"]


def _safe_index(seq, value, default=0):
    try:
        return seq.index(value)
    except (ValueError, TypeError):
        return default


def _render_transform_form(kind: str, current_params: dict,
                           view_df, key_prefix: str) -> dict:
    """Render structural inputs for a transform substep and return the
    user's current selections. The caller wires this output to a "save"
    button — re-runs of the form during widget interaction don't commit
    anything by themselves."""
    cols_avail = list(view_df.columns) if view_df is not None else []
    p: dict = dict(current_params or {})

    if kind == "merge_columns":
        c1, c2 = st.columns(2)
        with c1:
            p["columns"] = st.multiselect(
                "Columns to merge", cols_avail,
                default=[c for c in (p.get("columns") or []) if c in cols_avail],
                key=f"{key_prefix}_cols",
            )
            p["new_column"] = st.text_input(
                "New column name",
                value=str(p.get("new_column") or "merged"),
                key=f"{key_prefix}_new",
            )
        with c2:
            p["separator"] = st.text_input(
                "Separator", value=str(p.get("separator") if p.get("separator") is not None else " "),
                key=f"{key_prefix}_sep",
            )
            p["keep_originals"] = st.checkbox(
                "Keep original columns",
                value=bool(p.get("keep_originals", True)),
                key=f"{key_prefix}_keep",
            )
        return p

    if kind == "split_column":
        c1, c2 = st.columns(2)
        with c1:
            p["column"] = (st.selectbox(
                "Column to split", cols_avail,
                index=_safe_index(cols_avail, p.get("column"), 0),
                key=f"{key_prefix}_col",
            ) if cols_avail else "")
            p["new_column_prefix"] = st.text_input(
                "New column prefix",
                value=str(p.get("new_column_prefix") or f"{p.get('column') or 'col'}_part"),
                key=f"{key_prefix}_prefix",
            )
        with c2:
            mode_opts = ["delimiter", "width"]
            p["mode"] = st.selectbox(
                "Split by", mode_opts,
                index=_safe_index(mode_opts, p.get("mode", "delimiter"), 0),
                key=f"{key_prefix}_mode",
            )
            if p["mode"] == "delimiter":
                p["delimiter"] = st.text_input(
                    "Delimiter", value=str(p.get("delimiter") or ","),
                    key=f"{key_prefix}_delim",
                )
            else:
                p["width"] = int(st.number_input(
                    "Width (chars)", min_value=1, max_value=200,
                    value=int(p.get("width") or 1), step=1,
                    key=f"{key_prefix}_width",
                ))
            p["keep_original"] = st.checkbox(
                "Keep original column",
                value=bool(p.get("keep_original", True)),
                key=f"{key_prefix}_keep",
            )
        return p

    if kind == "replace_values":
        c1, c2 = st.columns(2)
        with c1:
            p["column"] = (st.selectbox(
                "Column", cols_avail,
                index=_safe_index(cols_avail, p.get("column"), 0),
                key=f"{key_prefix}_col",
            ) if cols_avail else "")
            p["find"] = st.text_input(
                "Find", value=str(p.get("find") or ""),
                key=f"{key_prefix}_find",
            )
            p["replace"] = st.text_input(
                "Replace with", value=str(p.get("replace") or ""),
                key=f"{key_prefix}_repl",
            )
        with c2:
            p["whole_cell"] = st.checkbox(
                "Match whole cell only",
                value=bool(p.get("whole_cell", False)),
                key=f"{key_prefix}_whole",
            )
            p["case_sensitive"] = st.checkbox(
                "Case sensitive",
                value=bool(p.get("case_sensitive", True)),
                key=f"{key_prefix}_case",
            )
        return p

    if kind == "conditional_column":
        c1, c2 = st.columns(2)
        with c1:
            p["source_column"] = (st.selectbox(
                "Source column", cols_avail,
                index=_safe_index(cols_avail, p.get("source_column"), 0),
                key=f"{key_prefix}_src",
            ) if cols_avail else "")
            p["new_column"] = st.text_input(
                "New column name",
                value=str(p.get("new_column") or "category"),
                key=f"{key_prefix}_new",
            )
        with c2:
            p["else_value"] = st.text_input(
                "Else value (when no rule matches)",
                value=str(p.get("else_value") if p.get("else_value") is not None else ""),
                key=f"{key_prefix}_else",
            )
        rules = list(p.get("rules") or [])
        n_key = f"{key_prefix}_n_rules"
        if n_key not in st.session_state:
            st.session_state[n_key] = max(1, len(rules))
        n_rules = int(st.session_state[n_key])
        st.markdown("**Rules** — evaluated top-to-bottom; first match wins")
        new_rules = []
        for ri in range(n_rules):
            existing = rules[ri] if ri < len(rules) else {"op": "==", "value": "", "then": ""}
            rcol1, rcol2, rcol3 = st.columns([1, 1, 1])
            with rcol1:
                op = st.selectbox(
                    f"Rule {ri + 1} · op",
                    _COND_OPS_UI,
                    index=_safe_index(_COND_OPS_UI, existing.get("op", "=="), 0),
                    key=f"{key_prefix}_op_{ri}",
                )
            with rcol2:
                val = st.text_input(
                    f"Rule {ri + 1} · value",
                    value=str(existing.get("value") if existing.get("value") is not None else ""),
                    key=f"{key_prefix}_val_{ri}",
                    disabled=(op == "is_null"),
                )
            with rcol3:
                then = st.text_input(
                    f"Rule {ri + 1} · then output",
                    value=str(existing.get("then") if existing.get("then") is not None else ""),
                    key=f"{key_prefix}_then_{ri}",
                )
            new_rules.append({"op": op, "value": val, "then": then})
        p["rules"] = new_rules
        b1, b2 = st.columns(2)
        with b1:
            if st.button("➕ Add rule", key=f"{key_prefix}_add_rule",
                         use_container_width=True):
                st.session_state[n_key] = n_rules + 1
                st.rerun()
        with b2:
            if n_rules > 1 and st.button("➖ Remove last rule",
                                          key=f"{key_prefix}_rm_rule",
                                          use_container_width=True):
                st.session_state[n_key] = max(1, n_rules - 1)
                st.rerun()
        return p

    if kind == "group_by":
        p["keys"] = st.multiselect(
            "Group keys", cols_avail,
            default=[c for c in (p.get("keys") or []) if c in cols_avail],
            key=f"{key_prefix}_keys",
        )
        aggs = list(p.get("aggregations") or [])
        n_key = f"{key_prefix}_n_aggs"
        if n_key not in st.session_state:
            st.session_state[n_key] = max(1, len(aggs))
        n_aggs = int(st.session_state[n_key])
        st.markdown("**Aggregations**")
        new_aggs = []
        for ai in range(n_aggs):
            existing = (aggs[ai] if ai < len(aggs)
                        else {"column": cols_avail[0] if cols_avail else "",
                              "agg": "sum", "alias": ""})
            ac1, ac2, ac3 = st.columns([1, 1, 1])
            with ac1:
                col = (st.selectbox(
                    f"Agg {ai + 1} · column", cols_avail,
                    index=_safe_index(cols_avail, existing.get("column"), 0),
                    key=f"{key_prefix}_acol_{ai}",
                ) if cols_avail else "")
            with ac2:
                agg = st.selectbox(
                    f"Agg {ai + 1} · function", TRANSFORM_AGGS,
                    index=_safe_index(TRANSFORM_AGGS, existing.get("agg", "sum"), 0),
                    key=f"{key_prefix}_aagg_{ai}",
                )
            with ac3:
                alias = st.text_input(
                    f"Agg {ai + 1} · alias",
                    value=str(existing.get("alias") or f"{col}_{agg}"),
                    key=f"{key_prefix}_aalias_{ai}",
                )
            new_aggs.append({"column": col, "agg": agg, "alias": alias})
        p["aggregations"] = new_aggs
        b1, b2 = st.columns(2)
        with b1:
            if st.button("➕ Add aggregation", key=f"{key_prefix}_add_agg",
                         use_container_width=True):
                st.session_state[n_key] = n_aggs + 1
                st.rerun()
        with b2:
            if n_aggs > 1 and st.button("➖ Remove last aggregation",
                                         key=f"{key_prefix}_rm_agg",
                                         use_container_width=True):
                st.session_state[n_key] = max(1, n_aggs - 1)
                st.rerun()
        return p

    if kind == "add_column_from_examples":
        p["new_column"] = st.text_input(
            "New column name",
            value=str(p.get("new_column") or "new_column"),
            key=f"{key_prefix}_new",
        )
        p["source_columns"] = st.multiselect(
            "Source columns",
            cols_avail,
            default=[c for c in (p.get("source_columns") or []) if c in cols_avail],
            key=f"{key_prefix}_src",
            help="Pick the column(s) the new column should be derived from.",
        )
        st.markdown("**Examples** — type the desired output for the first few "
                    "rows; the system will infer a transform that reproduces them.")
        examples = list(p.get("examples") or [])
        n_examples = 3
        new_examples = []
        for ei in range(n_examples):
            existing = examples[ei] if ei < len(examples) else {}
            row_idx = int(existing.get("row_idx", ei))
            preview_vals = []
            if view_df is not None and row_idx < len(view_df):
                preview_vals = [
                    str(view_df.iloc[row_idx][c])
                    for c in (p.get("source_columns") or []) if c in view_df.columns
                ]
            ec1, ec2 = st.columns([2, 1])
            with ec1:
                st.caption(
                    f"Row {row_idx + 1} input · "
                    f"{' · '.join(preview_vals) if preview_vals else '—'}"
                )
            with ec2:
                target = st.text_input(
                    f"Target output for row {row_idx + 1}",
                    value=str(existing.get("target") or ""),
                    key=f"{key_prefix}_ex_{ei}",
                    label_visibility="collapsed",
                )
            new_examples.append({"row_idx": row_idx, "target": target})
        p["examples"] = new_examples

        # Inference is opt-in — running it on every keystroke would be
        # expensive on million-row frames.
        infer_key = f"{key_prefix}_inferred"
        if st.button("Infer transform from examples",
                     key=f"{key_prefix}_infer"):
            ex_pairs = [(e["row_idx"], e["target"]) for e in new_examples
                        if str(e.get("target", "")).strip()]
            if not p.get("source_columns"):
                st.warning("Pick at least one source column first.")
            elif not ex_pairs:
                st.warning("Type at least one example output.")
            else:
                op, op_params, cov = infer_examples_op(
                    view_df, list(p["source_columns"]), ex_pairs,
                )
                if op is None:
                    st.warning("Could not infer a transform from those examples. "
                               "Try different examples or more source columns.")
                else:
                    st.session_state[infer_key] = {
                        "op": op, "op_params": op_params, "coverage": cov,
                    }
                    st.success(
                        f"Inferred `{op}` (matches {int(cov * 100)}% of examples). "
                        "Click 'Apply transform' to add the column."
                    )

        prev = st.session_state.get(infer_key)
        if prev:
            p["op"] = prev["op"]
            p["op_params"] = prev["op_params"]
            st.caption(
                f"Current op: `{prev['op']}` · params: `{prev['op_params']}` · "
                f"coverage: {int(prev['coverage'] * 100)}%"
            )
        return p

    return p


def _preview_transform(kind: str, params: dict, view_df, n: int = 15):
    """Run the transform on a small head sample so the user sees the
    resulting frame before committing. Returns (preview_df, ok, message);
    ``ok`` is False when params are invalid or execution raises — the
    caller renders the message inline so the user can fix the form."""
    if view_df is None or len(view_df) == 0:
        return None, False, "No data to preview yet."
    ok, msg = _validate_transform_params(kind, params)
    if not ok:
        return None, False, msg
    sample_rows = min(max(50, n + 5), len(view_df))
    sample = view_df.head(sample_rows).copy().reset_index(drop=True)
    fn = SUBSTEP_REGISTRY.get(kind, {}).get("fn")
    if fn is None:
        return None, False, "Unknown transform."
    try:
        out, _summary, _ = fn(sample, **params)
    except Exception as e:
        return None, False, f"Preview failed: {e}"
    return out.head(n), True, ""


def _render_transform_preview(kind: str, params: dict, view_df,
                              new_columns: list | None = None) -> None:
    """Render the inline preview block under a transform form. Highlights
    the column(s) the transform will add when known so the user can
    immediately spot the result."""
    preview_df, ok, msg = _preview_transform(kind, params, view_df)
    st.markdown("**Preview**")
    if not ok:
        st.info(msg)
        return
    if preview_df is None or preview_df.empty:
        st.info("Preview returned no rows.")
        return
    cols = list(preview_df.columns)
    if new_columns:
        # Reorder so the newly added columns sit at the front of the
        # preview — easier to verify the transform did what was wanted.
        ordered = [c for c in new_columns if c in cols] + \
                  [c for c in cols if c not in new_columns]
        preview_df = preview_df[ordered]
    st.dataframe(preview_df, use_container_width=True, hide_index=True)


def _transform_added_columns(kind: str, params: dict) -> list:
    """Best-effort list of columns the transform will add — used to bring
    them to the front of the preview."""
    p = params or {}
    if kind in ("merge_columns", "conditional_column",
                "add_column_from_examples") and p.get("new_column"):
        return [str(p["new_column"])]
    if kind == "split_column":
        # Real output is `prefix_1`, `prefix_2`, ... — return up to 8 so the
        # preview highlight surfaces the actual new columns rather than just
        # the bare prefix (which never appears in the dataframe).
        prefix = p.get("new_column_prefix") or f"{p.get('column') or 'col'}_part"
        max_parts = 8
        if p.get("mode") == "delimiter":
            max_parts = max(1, int(p.get("max_splits") or 0)) + 1 \
                        if p.get("max_splits") else 8
        return [f"{prefix}_{i}" for i in range(1, max_parts + 1)]
    return []


def _validate_transform_params(kind: str, params: dict) -> tuple:
    """Return (ok, message). message is shown to the user when ok is False."""
    p = params or {}
    if kind == "merge_columns":
        if not (p.get("columns") and len(p["columns"]) >= 2):
            return False, "Pick at least two columns to merge."
        if not str(p.get("new_column") or "").strip():
            return False, "Provide a name for the new column."
    elif kind == "split_column":
        if not p.get("column"):
            return False, "Pick a column to split."
    elif kind == "replace_values":
        if not p.get("column"):
            return False, "Pick a column."
        if not str(p.get("find") or "").strip():
            return False, "Find pattern cannot be empty."
    elif kind == "conditional_column":
        if not str(p.get("new_column") or "").strip():
            return False, "Provide a name for the new column."
        if not p.get("rules"):
            return False, "Add at least one rule."
    elif kind == "group_by":
        if not p.get("keys"):
            return False, "Pick at least one group key."
        aggs = p.get("aggregations") or []
        if not aggs:
            return False, "Add at least one aggregation."
        from transforms import VALID_AGGS  # local import — avoids cycle at module load
        valid = [a for a in aggs
                 if isinstance(a, dict)
                 and str(a.get("column") or "").strip()
                 and a.get("agg") in VALID_AGGS]
        if not valid:
            return False, ("Each aggregation needs a column and a "
                           f"supported function ({', '.join(sorted(VALID_AGGS))}).")
    elif kind == "add_column_from_examples":
        if not str(p.get("new_column") or "").strip():
            return False, "Provide a name for the new column."
        if not p.get("source_columns"):
            return False, "Pick at least one source column."
        if not p.get("op"):
            return False, "Click 'Infer transform from examples' first."
    return True, ""


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
                    st.session_state.page = 'projects'
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
        st.session_state.page = 'projects'
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

        _login_flash = st.session_state.pop('login_flash', None)
        if _login_flash:
            st.success(_login_flash)

        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Email Address", placeholder="you@company.com", key="login_email")
            password = st.text_input("Password", type="password", placeholder="Enter your password", key="login_password")
            st.markdown('<div class="auth-aux-row"><a class="auth-aux-link" href="?forgot=1" target="_self">Forgot password?</a></div>', unsafe_allow_html=True)
            submit = st.form_submit_button("Sign In \u2192", use_container_width=True)

            if submit:
                if email and password:
                    db = get_db()
                    try:
                        user = authenticate_user(db, email, password)
                        if user:
                            _tok = issue_session_token(db, user, days=30)
                            st.session_state.user = user_to_dict(user)
                            st.session_state.page = 'projects'
                            st.query_params[SESSION_QP_NAME] = _tok
                        else:
                            st.error("Invalid email or password")
                    finally:
                        db.close()
                else:
                    st.warning("Please enter both email and password")

        if st.session_state.user and st.session_state.page == 'projects':
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
<li><a href="/#how" target="_self">How It Works</a></li>
<li><a href="/#pricing" target="_self">Pricing &amp; Plans</a></li>
</ul>
</div>
<div>
<div class="lp-footer-col-title">Support</div>
<ul class="lp-footer-links-list">
<li><a href="?help=1" target="_self">Help Center</a></li>
<li><a href="?help=1" target="_self">Documentation</a></li>
<li><a href="/#contact" target="_self">Contact Us</a></li>
<li><a href="mailto:muayad.demaidi.work@gmail.com">Email Support</a></li>
<li><a href="?help=1#report-issue" target="_self">Report an Issue</a></li>
</ul>
</div>
<div>
<div class="lp-footer-col-title">Learn</div>
<ul class="lp-footer-links-list">
<li><a href="https://datavisionpro.app/glossary/" target="_blank" rel="noopener">Data Glossary</a></li>
<li><a href="https://datavisionpro.app/guides/" target="_blank" rel="noopener">How-to Guides</a></li>
<li><a href="https://datavisionpro.app/compare/" target="_blank" rel="noopener">Compare</a></li>
<li><a href="https://datavisionpro.app/about/" target="_blank" rel="noopener">About</a></li>
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
        st.session_state.page = 'projects'
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
                            st.session_state.page = 'projects'
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
<a class="lp-footer-link" href="/" target="_self">Home</a>
<a class="lp-footer-link" href="/#features" target="_self">Features</a>
<a class="lp-footer-link" href="/#how" target="_self">How It Works</a>
<a class="lp-footer-link" href="/#pricing" target="_self">Pricing</a>
</div>
<div class="lp-footer-col">
<div class="lp-footer-col-title">SUPPORT</div>
<a class="lp-footer-link" href="?help=1" target="_self">Help Center</a>
<a class="lp-footer-link" href="?help=1" target="_self">Documentation</a>
<a class="lp-footer-link" href="/#contact" target="_self">Contact Us</a>
<a class="lp-footer-link" href="mailto:muayad.demaidi.work@gmail.com">Email Support</a>
<a class="lp-footer-link" href="?help=1#report-issue" target="_self">Report an Issue</a>
</div>
<div class="lp-footer-col">
<div class="lp-footer-col-title">LEARN</div>
<a class="lp-footer-link" href="https://datavisionpro.app/glossary/" target="_blank" rel="noopener">Data Glossary</a>
<a class="lp-footer-link" href="https://datavisionpro.app/guides/" target="_blank" rel="noopener">How-to Guides</a>
<a class="lp-footer-link" href="https://datavisionpro.app/compare/" target="_blank" rel="noopener">Compare</a>
<a class="lp-footer-link" href="https://datavisionpro.app/about/" target="_blank" rel="noopener">About</a>
</div>
</div>
<div class="lp-footer-bottom">
<div class="lp-footer-copy">© 2026 DataVision Pro · All systems operational</div>
<div class="lp-footer-pulse"><span class="lp-pulse-dot"></span>STATUS · LIVE</div>
</div>
</div></div>
''', unsafe_allow_html=True)


def _get_app_base_url():
    """Best-effort base URL for outbound deep-links (password reset emails)."""
    domains = os.environ.get("REPLIT_DOMAINS", "")
    if domains:
        first = domains.split(",")[0].strip()
        if first:
            return f"https://{first}"
    dev_domain = os.environ.get("REPLIT_DEV_DOMAIN", "")
    if dev_domain:
        return f"https://{dev_domain}"
    return ""


def _render_forgot_password_styles():
    """Per-page tweaks shared by forgot/reset screens."""
    st.markdown('''
<style>
.auth-aux-row.center { justify-content: center; margin-top: 0.6rem; }
.auth-inline-help {
    font-family: 'JetBrains Mono', monospace; font-size: 0.7rem;
    color: var(--text-muted); letter-spacing: 0.06em;
    text-align: center; margin: 0.85rem 0 0 0;
}
</style>
''', unsafe_allow_html=True)


def show_forgot_password_page():
    logo_b64 = get_logo_base64()
    _render_auth_chrome(logo_b64, action_label="Sign In", action_href="?signin=1")
    _render_forgot_password_styles()

    col_left, col_right = st.columns([1.05, 1], gap="large")

    with col_left:
        st.markdown('''
<div class="auth-brand-pane">
<div class="auth-brand-eyebrow">Account Recovery</div>
<h1 class="auth-brand-headline">Forgot your password?<br>We&rsquo;ll help you back in.</h1>
<p class="auth-brand-sub">Enter the email address tied to your DataVision Pro account and we&rsquo;ll send you a secure link to choose a new password.</p>
<div class="auth-brand-features">
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">01</div>
<div class="auth-brand-feat-body"><strong>One-Time Link</strong><span>The reset link works once and expires after 60 minutes.</span></div>
</div>
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">02</div>
<div class="auth-brand-feat-body"><strong>Privacy First</strong><span>We never reveal whether an email is registered with us.</span></div>
</div>
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">03</div>
<div class="auth-brand-feat-body"><strong>Your Data Stays Safe</strong><span>Your datasets and analyses remain untouched during recovery.</span></div>
</div>
</div>
</div>
''', unsafe_allow_html=True)

    with col_right:
        st.markdown('''
<div class="auth-eyebrow"><span>Reset your password</span></div>
<div class="auth-headline">
<h1>Reset your password</h1>
<p>Enter your email and we&rsquo;ll send you a reset link.</p>
</div>
''', unsafe_allow_html=True)

        _flash = st.session_state.pop('forgot_flash', None)
        if _flash:
            st.success(_flash)

        with st.form("forgot_password_form", clear_on_submit=False):
            email = st.text_input("Email Address", placeholder="you@company.com", key="forgot_email")
            submit = st.form_submit_button("Send reset link \u2192", use_container_width=True)

            if submit:
                neutral_msg = ("If an account exists for that email, we've sent "
                               "a reset link. Please check your inbox.")
                if not email or "@" not in email:
                    st.warning("Please enter a valid email address.")
                else:
                    db = get_db()
                    try:
                        try:
                            purge_expired_password_reset_tokens(db)
                        except Exception:
                            pass
                        user = get_user_by_email(db, email.strip().lower()) or get_user_by_email(db, email.strip())
                        if user:
                            try:
                                raw_token = create_password_reset_token(db, user, ttl_hours=1)
                                if raw_token:
                                    base = _get_app_base_url()
                                    reset_url = (f"{base}/?reset_token={raw_token}"
                                                 if base else f"?reset_token={raw_token}")
                                    send_password_reset_email(user.email, user.full_name or user.username, reset_url)
                            except Exception as e:
                                print(f"Password reset send failed: {e}")
                        st.session_state['forgot_flash'] = neutral_msg
                        st.rerun()
                    finally:
                        db.close()

        st.markdown('<div class="auth-divider"><span>REMEMBERED IT</span></div>', unsafe_allow_html=True)
        st.markdown('<p class="auth-foot-text">Take me back to the sign-in page.</p>', unsafe_allow_html=True)
        if st.button("Back to Sign In  \u2192", use_container_width=True, key="forgot_to_login"):
            st.session_state.page = 'login'
            st.rerun()

        st.markdown('''
<div class="auth-trust">
<span>ENCRYPTED</span><span class="dot">\u00b7</span><span>ONE-TIME LINK</span><span class="dot">\u00b7</span><span>EXPIRES IN 1 HOUR</span>
</div>
''', unsafe_allow_html=True)


def show_reset_password_page():
    logo_b64 = get_logo_base64()
    _render_auth_chrome(logo_b64, action_label="Sign In", action_href="?signin=1")
    _render_forgot_password_styles()

    raw_token = ""
    try:
        raw_token = st.query_params.get('reset_token') or ""
    except Exception:
        raw_token = ""

    db = get_db()
    try:
        token_record, user = (None, None)
        if raw_token:
            token_record, user = get_valid_password_reset_token(db, raw_token)

        col_left, col_right = st.columns([1.05, 1], gap="large")

        with col_left:
            st.markdown('''
<div class="auth-brand-pane">
<div class="auth-brand-eyebrow">Choose a New Password</div>
<h1 class="auth-brand-headline">Almost there.<br>Set a new password.</h1>
<p class="auth-brand-sub">Pick something strong &mdash; at least 8 characters. Once updated, you&rsquo;ll be redirected to sign in with your new credentials.</p>
<div class="auth-brand-features">
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">01</div>
<div class="auth-brand-feat-body"><strong>Min 8 Characters</strong><span>Longer passwords are dramatically harder to crack.</span></div>
</div>
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">02</div>
<div class="auth-brand-feat-body"><strong>Single-Use Link</strong><span>This link is consumed the moment your password updates.</span></div>
</div>
<div class="auth-brand-feat">
<div class="auth-brand-feat-icon">03</div>
<div class="auth-brand-feat-body"><strong>Bcrypt Hashing</strong><span>We never store your password &mdash; only a salted hash.</span></div>
</div>
</div>
</div>
''', unsafe_allow_html=True)

        with col_right:
            if not token_record or not user:
                st.markdown('''
<div class="auth-eyebrow"><span>Link Invalid</span></div>
<div class="auth-headline">
<h1>This link is no longer valid</h1>
<p>It may have expired, already been used, or been mistyped.</p>
</div>
''', unsafe_allow_html=True)
                st.error("This password reset link is no longer valid \u2014 please request a new one.")
                if st.button("Request a new reset link  \u2192", use_container_width=True, key="reset_invalid_to_forgot"):
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
                    st.session_state.page = 'forgot_password'
                    st.rerun()
                if st.button("Back to Sign In", use_container_width=True, key="reset_invalid_to_login"):
                    try:
                        st.query_params.clear()
                    except Exception:
                        pass
                    st.session_state.page = 'login'
                    st.rerun()
                return

            st.markdown(f'''
<div class="auth-eyebrow"><span>Choose a new password</span></div>
<div class="auth-headline">
<h1>Choose a new password</h1>
<p>Updating the password for <strong style="color:var(--teal);">{user.email}</strong>.</p>
</div>
''', unsafe_allow_html=True)

            with st.form("reset_password_form", clear_on_submit=False):
                new_password = st.text_input("New Password", type="password",
                                             placeholder="Min 8 characters", key="reset_new_pw")
                confirm_password = st.text_input("Confirm New Password", type="password",
                                                 placeholder="Re-enter new password", key="reset_confirm_pw")
                st.markdown('<p class="auth-inline-help">Use at least 8 characters. Both fields must match.</p>',
                            unsafe_allow_html=True)
                submit = st.form_submit_button("Update password  \u2192", use_container_width=True)

                if submit:
                    if not new_password or not confirm_password:
                        st.warning("Please fill in both password fields.")
                    elif len(new_password) < 8:
                        st.error("Password must be at least 8 characters.")
                    elif new_password != confirm_password:
                        st.error("Passwords do not match.")
                    else:
                        try:
                            updated_user = consume_password_reset_token(
                                db, token_record, new_password
                            )
                            if not updated_user:
                                st.error(
                                    "This password reset link is no longer valid "
                                    "\u2014 please request a new one."
                                )
                            else:
                                try:
                                    send_password_changed_email(
                                        updated_user.email,
                                        updated_user.full_name or updated_user.username,
                                    )
                                except Exception as email_err:
                                    print(f"Password changed email failed: {email_err}")
                                st.session_state['login_flash'] = (
                                    "Your password has been updated. Please sign in "
                                    "with your new password."
                                )
                                try:
                                    st.query_params.clear()
                                except Exception:
                                    pass
                                st.session_state.page = 'login'
                                st.rerun()
                        except Exception as e:
                            print(f"Password reset failed: {e}")
                            st.error("Something went wrong updating your password. Please try again.")

            st.markdown('<div class="auth-divider"><span>CHANGED YOUR MIND</span></div>', unsafe_allow_html=True)
            if st.button("Back to Sign In", use_container_width=True, key="reset_to_login"):
                try:
                    st.query_params.clear()
                except Exception:
                    pass
                st.session_state.page = 'login'
                st.rerun()
    finally:
        db.close()


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
        
        admin_tabs = st.tabs(["👥 Users", "📊 Datasets", "💬 Conversations", "🔮 SEO/GEO Agent"])
        
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

        with admin_tabs[3]:
            show_seo_agent_admin()
    
    finally:
        db.close()
    
    st.markdown("---")
    if st.button("← Back to Dashboard", use_container_width=True):
        st.session_state.page = 'dashboard'
        st.rerun()


def show_seo_agent_admin():
    """Admin view for the weekly SEO/GEO automation agent."""
    import json as _json
    from seo_agent.config import load_config, save_config, AgentConfig
    from seo_agent.db import init_agent_db, get_session, AgentRun, GeoCheckResult
    from seo_agent.review import (
        list_drafts, get_draft_payload, approve_draft, reject_draft,
    )
    from seo_agent.runner import run_weekly_cycle
    from seo_agent.db import AgentDraft, AgentBuildJob
    from seo_agent.build_queue import (
        list_build_jobs, retry_build_job, enqueue_build, ensure_worker_running,
        confirm_publish,
    )

    init_agent_db()
    ensure_worker_running()
    cfg = load_config()
    sess = get_session()
    try:
        last_run = sess.query(AgentRun).order_by(AgentRun.started_at.desc()).first()
        recent_runs = sess.query(AgentRun).order_by(AgentRun.started_at.desc()).limit(8).all()
        geo_runs = (sess.query(AgentRun)
                    .filter(AgentRun.summary.isnot(None))
                    .order_by(AgentRun.started_at.desc()).limit(12).all())
    finally:
        sess.close()

    def _next_cron_run(expr: str):
        """Best-effort computation of the next datetime that matches a 5-field cron.
        Supports '*', '*/N', and integer fields. Falls back to None on weird input."""
        from datetime import datetime as _dt, timedelta as _td
        try:
            mn, hr, dom, mo, dow = expr.split()
        except Exception:
            return None
        def _match(field, value, lo, hi):
            if field == "*":
                return True
            if field.startswith("*/"):
                try:
                    n = int(field[2:]); return value % n == 0
                except Exception:
                    return False
            try:
                return int(field) == value
            except Exception:
                return False
        now = _dt.utcnow().replace(second=0, microsecond=0) + _td(minutes=1)
        for _ in range(60 * 24 * 14):  # search up to 14 days out
            cron_dow = (now.weekday() + 1) % 7  # Mon=1..Sun=0 like cron
            if (_match(mn, now.minute, 0, 59) and _match(hr, now.hour, 0, 23)
                    and _match(dom, now.day, 1, 31) and _match(mo, now.month, 1, 12)
                    and _match(dow, cron_dow, 0, 6)):
                return now
            now += _td(minutes=1)
        return None

    st.subheader("Status")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Last run", last_run.started_at.strftime("%Y-%m-%d %H:%M") if last_run else "—")
    with c2:
        st.metric("Last status", (last_run.status if last_run else "never run"))
    with c3:
        pending = len(list_drafts("pending"))
        st.metric("Drafts awaiting review", pending)
    with c4:
        nxt = _next_cron_run(cfg.schedule_cron)
        st.metric("Next scheduled", nxt.strftime("%Y-%m-%d %H:%M") if nxt else cfg.schedule_cron)
    with c5:
        from datetime import datetime as _dt2, timedelta as _td2
        sess2 = get_session()
        try:
            cutoff = _dt2.utcnow() - _td2(days=7)
            published_week = (sess2.query(AgentDraft)
                              .filter(AgentDraft.status == "approved")
                              .filter(AgentDraft.reviewed_at >= cutoff)
                              .count())
        finally:
            sess2.close()
        st.metric("Published this week", published_week)

    if last_run and last_run.summary:
        s = last_run.summary
        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("Drafts created", s.get("drafts_created", 0))
        cc2.metric("Pages refreshed", s.get("drafts_refreshed", 0))
        cc3.metric("Est. cost (USD)", f"${s.get('estimated_cost_usd', 0):.3f}")
        rate = s.get("geo_mention_rate")
        cc4.metric("GEO mention rate", f"{rate*100:.1f}%" if rate is not None else "—")

    st.markdown("---")

    sub_tabs = st.tabs(["📥 Review queue", "🚀 Build & deploy",
                        "📈 GEO trend", "🚦 Top performing pages",
                        "⚙️ Config", "📜 Run history"])

    with sub_tabs[0]:
        st.markdown("#### Drafts awaiting review")
        drafts = list_drafts("pending")
        if not drafts:
            st.info("No drafts pending. Run the agent to generate some.")
        for d in drafts:
            with st.expander(f"[{d.kind}] {d.title} — {d.slug}"):
                st.caption(f"Target query: {d.target_query} · "
                           f"{'Refresh' if d.is_refresh else 'New'} · "
                           f"created {d.created_at.strftime('%Y-%m-%d %H:%M')}")
                if d.info_gain:
                    st.markdown(f"**Information-gain note:** {d.info_gain}")
                payload = get_draft_payload(d.id) or {}
                inner = payload.get("payload", payload)
                edit_mode = st.checkbox("✏️ Edit before approving", key=f"edit_{d.id}")
                edited_text = None
                if edit_mode:
                    edited_text = st.text_area(
                        "Draft JSON (edit then Approve to publish your version)",
                        value=_json.dumps(inner, indent=2, ensure_ascii=False),
                        height=400, key=f"edit_text_{d.id}",
                    )
                else:
                    st.json(inner)
                colA, colB, _ = st.columns([1, 1, 4])
                if colA.button("✅ Approve", key=f"appr_{d.id}"):
                    reviewer = (st.session_state.user or {}).get("email", "admin")
                    edited_payload = None
                    if edit_mode and edited_text:
                        try:
                            edited_payload = _json.loads(edited_text)
                        except Exception as ex:
                            st.error(f"Edit JSON invalid: {ex}")
                            st.stop()
                    res = approve_draft(d.id, reviewer=reviewer,
                                         notes=("edited" if edited_payload else ""),
                                         edited_payload=edited_payload,
                                         source="admin")
                    if res.get("ok"):
                        if res.get("build_queued"):
                            st.success(f"Approved → injected into {res['file']} · "
                                       f"rebuild + redeploy queued (job #{res.get('build_job_id')})")
                        else:
                            st.warning(f"Approved → injected into {res['file']} · "
                                       f"build queue failed: {res.get('build_error', 'unknown')}")
                        st.rerun()
                    else:
                        st.error(f"Approve failed: {res.get('error')}")
                if colB.button("❌ Reject", key=f"rej_{d.id}"):
                    reviewer = (st.session_state.user or {}).get("email", "admin")
                    if reject_draft(d.id, reviewer=reviewer, source="admin"):
                        st.warning("Rejected and archived.")
                        st.rerun()

        st.markdown("---")
        if st.button("▶ Run now (manual trigger)", type="primary"):
            with st.spinner("Running weekly cycle… this may take a few minutes."):
                summary = run_weekly_cycle(cfg=cfg)
            st.success(f"Done. Drafts: {summary.get('drafts_created', 0)} · "
                       f"Refreshed: {summary.get('drafts_refreshed', 0)} · "
                       f"Cost: ${summary.get('estimated_cost_usd', 0):.3f}")
            st.json(summary)

    with sub_tabs[1]:
        st.markdown("#### Build & deploy queue")
        st.caption(
            "After a draft is approved, the marketing site is rebuilt "
            "(`npm run build` in `marketing-site/`) and — if "
            "`SEO_AGENT_DEPLOY_HOOK_URL` is set — a redeploy webhook is "
            "POSTed. Failures retry automatically with exponential backoff."
        )
        bc1, bc2, bc3 = st.columns([1, 1, 4])
        if bc1.button("🔁 Refresh", key="bq_refresh"):
            st.rerun()
        if bc2.button("▶ Trigger build now", key="bq_manual"):
            job = enqueue_build(reason="manual")
            st.success(f"Queued build job #{job.id}")
            st.rerun()

        jobs = list_build_jobs(limit=25)
        if not jobs:
            st.info("No build jobs yet. Approve a draft to kick one off.")
        else:
            _status_emoji = {
                "queued": "⏳", "running": "🔄", "success": "✅",
                "failed": "❌", "skipped": "⏭️", "needs_publish": "📤",
            }
            for j in jobs:
                emoji = _status_emoji.get(j.status, "•")
                dur = ""
                if j.started_at and j.finished_at:
                    secs = (j.finished_at - j.started_at).total_seconds()
                    dur = f" · {secs:.1f}s"
                title = (f"{emoji} #{j.id} · {j.status} · {j.reason or '—'} "
                         f"· attempt {j.attempts}/{j.max_attempts}{dur}")
                with st.expander(title):
                    st.write({
                        "queued_at": j.queued_at.strftime("%Y-%m-%d %H:%M:%S")
                                     if j.queued_at else None,
                        "started_at": j.started_at.strftime("%Y-%m-%d %H:%M:%S")
                                      if j.started_at else None,
                        "finished_at": j.finished_at.strftime("%Y-%m-%d %H:%M:%S")
                                       if j.finished_at else None,
                        "next_attempt_at": j.next_attempt_at.strftime("%Y-%m-%d %H:%M:%S")
                                           if j.next_attempt_at else None,
                        "build_ok": j.build_ok,
                        "deploy_ok": j.deploy_ok,
                        "deploy_target": j.deploy_target,
                        "draft_id": j.draft_id,
                    })
                    if j.error:
                        st.error(j.error)
                    if j.log_tail:
                        st.code(j.log_tail, language="bash")
                    if j.status == "failed":
                        if st.button("🔁 Retry this job", key=f"bq_retry_{j.id}"):
                            if retry_build_job(j.id):
                                st.success("Re-queued.")
                                st.rerun()
                    if j.status == "needs_publish":
                        st.warning(
                            "Build succeeded but the site has not been "
                            "republished yet. Open Replit → Deployments → "
                            "Static deployment for `marketing-site/` and "
                            "click Republish, then mark this job published."
                        )
                        if st.button("✅ Mark as published", key=f"bq_pub_{j.id}"):
                            reviewer = (st.session_state.user or {}).get("email", "admin")
                            if confirm_publish(j.id, reviewer):
                                st.success("Marked as published.")
                                st.rerun()

    with sub_tabs[2]:
        st.markdown("#### GEO mention rate per run")
        rows = []
        for r in reversed(geo_runs):
            if not r.summary:
                continue
            rate = r.summary.get("geo_mention_rate")
            if rate is None:
                continue
            rows.append({"date": r.started_at.strftime("%Y-%m-%d"),
                         "mention_rate_%": round(rate * 100, 1)})
        if rows:
            df = pd.DataFrame(rows)
            st.line_chart(df.set_index("date"))
            st.dataframe(df, use_container_width=True)
        else:
            st.info("No GEO check results yet. Run the agent first.")

        st.markdown("#### Pages published per week")
        from datetime import datetime as _dtw, timedelta as _tdw
        sess3 = get_session()
        try:
            since = _dtw.utcnow() - _tdw(weeks=12)
            approved = (sess3.query(AgentDraft)
                        .filter(AgentDraft.status == "approved")
                        .filter(AgentDraft.reviewed_at >= since)
                        .all())
        finally:
            sess3.close()
        if approved:
            buckets = {}
            for a in approved:
                wk = (a.reviewed_at - _tdw(days=a.reviewed_at.weekday())).strftime("%Y-%m-%d")
                buckets[wk] = buckets.get(wk, 0) + 1
            df2 = pd.DataFrame(
                sorted([{"week": k, "pages_published": v} for k, v in buckets.items()],
                       key=lambda x: x["week"])
            )
            st.bar_chart(df2.set_index("week"))
        else:
            st.caption("No pages published in the last 12 weeks yet.")

    with sub_tabs[3]:
        st.markdown("#### Top performing pages (organic traffic)")
        st.caption(
            "Pulled weekly from the configured free analytics source "
            f"(`{cfg.analytics_source}`). Slugs with zero traffic for "
            f">{cfg.topic_dead_lookback_days} days are down-weighted by the "
            "topic selector; high-performers are boosted."
        )
        from seo_agent.db import PageMetric as _PageMetric
        from datetime import datetime as _dtm, timedelta as _tdm
        from sqlalchemy import func as _sa_func
        sess_pm = get_session()
        try:
            window_days = max(7, int(cfg.topic_dead_lookback_days))
            since_pm = _dtm.utcnow() - _tdm(days=window_days)
            agg_rows = (sess_pm.query(
                            _PageMetric.slug,
                            _PageMetric.kind,
                            _sa_func.max(_PageMetric.url).label("url"),
                            _sa_func.sum(_PageMetric.clicks).label("clicks"),
                            _sa_func.sum(_PageMetric.impressions).label("impressions"),
                            _sa_func.avg(_PageMetric.ctr).label("ctr"),
                            _sa_func.avg(_PageMetric.avg_position).label("avg_position"),
                            _sa_func.max(_PageMetric.fetched_at).label("last_seen"),
                         )
                         .filter(_PageMetric.fetched_at >= since_pm)
                         .group_by(_PageMetric.slug, _PageMetric.kind)
                         .all())
        except Exception as _ex:
            agg_rows = []
            st.warning(f"Could not read page metrics: {_ex}")
        finally:
            sess_pm.close()

        if not agg_rows:
            st.info(
                "No analytics rows yet. Configure an analytics source in "
                "**Config** (Plausible API or a Google Search Console CSV "
                "export) and run the agent."
            )
        else:
            metric_df = pd.DataFrame([{
                "slug": r.slug,
                "kind": r.kind or "",
                "url": r.url or "",
                "clicks": int(r.clicks or 0),
                "impressions": int(r.impressions or 0),
                "ctr_%": round(float(r.ctr or 0) * 100, 2),
                "avg_position": round(float(r.avg_position), 2) if r.avg_position is not None else None,
                "last_seen": r.last_seen.strftime("%Y-%m-%d") if r.last_seen else "",
            } for r in agg_rows])
            metric_df = metric_df.sort_values(
                ["clicks", "impressions"], ascending=[False, False]
            ).reset_index(drop=True)

            top_n = min(20, len(metric_df))
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Pages with traffic data", len(metric_df))
            mc2.metric("Total clicks (window)", int(metric_df["clicks"].sum()))
            mc3.metric("Total impressions (window)", int(metric_df["impressions"].sum()))
            dead_n = int(((metric_df["clicks"] == 0) & (metric_df["impressions"] == 0)).sum())
            mc4.metric("Zero-traffic slugs", dead_n,
                       help=f"No clicks AND no impressions in the last {window_days} days.")

            st.markdown(f"**Top {top_n} pages by clicks**")
            st.dataframe(metric_df.head(top_n), use_container_width=True, hide_index=True)

            with st.expander(f"Slugs with zero traffic in the last {window_days} days "
                             f"({dead_n})"):
                dead_df = metric_df[(metric_df["clicks"] == 0)
                                    & (metric_df["impressions"] == 0)]
                if dead_df.empty:
                    st.caption("None — every tracked page is at least getting impressions.")
                else:
                    st.dataframe(dead_df[["slug", "kind", "url", "last_seen"]],
                                 use_container_width=True, hide_index=True)
                    st.caption("These categories will be down-weighted in the next "
                               "topic-selection pass.")

    with sub_tabs[4]:
        st.markdown("#### Configuration")
        with st.form("seo_agent_cfg"):
            schedule = st.text_input("Cron schedule (UTC)", cfg.schedule_cron)
            max_new = st.number_input("Max new pages per week", 0, 25, cfg.max_new_pages_per_week)
            max_ref = st.number_input("Max refresh pages per week", 0, 25, cfg.max_refresh_pages_per_week)
            model = st.text_input("OpenAI model", cfg.openai_model)
            budget = st.number_input("Weekly budget cap (USD)", 0.0, 200.0, float(cfg.weekly_budget_usd), step=1.0)
            auto_pub = st.checkbox("Auto-publish on generation (skip review)", cfg.auto_publish)
            refresh_days = st.number_input("Refresh pages older than (days)", 7, 365, cfg.refresh_after_days)
            email_to = st.text_input("Weekly report email", cfg.report_email_to)
            notify_on = st.checkbox(
                "📱 Alert me as soon as new drafts are ready",
                value=getattr(cfg, "notify_on_new_drafts", False),
                help="Sends a short email (with the public review link) right "
                     "after every run that creates at least one draft. Off by default.",
            )
            notify_to = st.text_input(
                "Send draft alerts to",
                value=getattr(cfg, "notify_email_to", "") or "",
                placeholder="leave blank to reuse the weekly report email above",
                help="Use a phone-friendly inbox (or an email-to-SMS gateway) to get a push.",
            )
            _suggested_token = st.session_state.pop("_seo_suggested_token", None)
            review_token = st.text_input(
                "Public review token (gates the mobile review URL)",
                _suggested_token if _suggested_token else cfg.admin_review_token,
                type="password",
                help="Anyone with this token + the app URL can approve/reject "
                     "drafts without an admin login. Leave blank to disable. "
                     "Use the 'Generate new token' button below the form to "
                     "create a strong random one, then click Save.",
            )
            from seo_agent.report import (
                autodetect_app_url as _seo_autodetect_url,
                resolve_public_app_url as _seo_resolved_url,
            )
            _detected = _seo_autodetect_url() or ""
            _resolved_now = _seo_resolved_url() or ""
            _placeholder = _detected or "https://your-app.example.com"
            _help_bits = [
                "Base URL of this Streamlit app — used to build the mobile "
                "review link in the weekly email.",
            ]
            if _detected:
                _help_bits.append(f"Auto-detected: {_detected}")
            _help_bits.append(
                "Leave blank to use the auto-detected URL (or set the "
                "`SEO_AGENT_PUBLIC_APP_URL` env var to force a value)."
            )
            public_app_url = st.text_input(
                "Public app URL (mobile review link)",
                cfg.public_app_url,
                placeholder=_placeholder,
                help=" ".join(_help_bits),
            )
            if _resolved_now:
                st.caption(f"Resolved review base URL: `{_resolved_now}`")
            else:
                st.caption(
                    "No public URL detected yet — set one above or deploy "
                    "the app so the URL can be auto-detected."
                )
            st.markdown("**Sources enabled**")
            sc1, sc2, sc3, sc4 = st.columns(4)
            s_reddit = sc1.checkbox("Reddit", cfg.sources_enabled.get("reddit", True))
            s_hn = sc2.checkbox("Hacker News", cfg.sources_enabled.get("hackernews", True))
            s_so = sc3.checkbox("Stack Overflow", cfg.sources_enabled.get("stackoverflow", True))
            s_gt = sc4.checkbox("Google Trends (pytrends)", cfg.sources_enabled.get("google_trends", False))
            prompts_text = st.text_area("GEO check prompts (one per line)",
                                        "\n".join(cfg.geo_prompts), height=220)
            st.markdown("**Organic-traffic analytics (Top performing pages)**")
            ac1, ac2 = st.columns([1, 2])
            an_src = ac1.selectbox(
                "Analytics source",
                ["none", "plausible", "gsc_csv"],
                index=["none", "plausible", "gsc_csv"].index(
                    cfg.analytics_source if cfg.analytics_source in ("none", "plausible", "gsc_csv") else "none"
                ),
                help="plausible needs PLAUSIBLE_API_KEY env var. gsc_csv reads a CSV at GSC_CSV_IMPORT_PATH (default data/gsc_pages.csv).",
            )
            an_site = ac2.text_input(
                "Site URL / Plausible site_id",
                cfg.analytics_site_url,
                placeholder="datavisionpro.app",
            )
            ac3, ac4, ac5 = st.columns(3)
            an_lookback = ac3.number_input("Pull window (days)", 1, 90, int(cfg.analytics_lookback_days))
            dead_days = ac4.number_input("Dead-page lookback (days)", 14, 365, int(cfg.topic_dead_lookback_days))
            dead_factor = ac5.number_input("Dead-overlap score factor", 0.0, 1.0,
                                            float(cfg.topic_dead_score_factor), step=0.1)
            winner_factor = st.number_input("Winner-overlap score factor", 1.0, 5.0,
                                             float(cfg.topic_winner_score_factor), step=0.1)
            submitted = st.form_submit_button("💾 Save configuration")
            if submitted:
                cfg.schedule_cron = schedule
                cfg.max_new_pages_per_week = int(max_new)
                cfg.max_refresh_pages_per_week = int(max_ref)
                cfg.openai_model = model
                cfg.weekly_budget_usd = float(budget)
                cfg.auto_publish = bool(auto_pub)
                cfg.refresh_after_days = int(refresh_days)
                cfg.report_email_to = email_to.strip()
                cfg.notify_on_new_drafts = bool(notify_on)
                cfg.notify_email_to = (notify_to or "").strip()
                cfg.admin_review_token = (review_token or "").strip()
                cfg.public_app_url = (public_app_url or "").strip()
                cfg.sources_enabled = {
                    "reddit": s_reddit, "hackernews": s_hn,
                    "stackoverflow": s_so, "google_trends": s_gt,
                }
                cfg.geo_prompts = [p.strip() for p in prompts_text.splitlines() if p.strip()]
                cfg.analytics_source = an_src
                cfg.analytics_site_url = an_site.strip()
                cfg.analytics_lookback_days = int(an_lookback)
                cfg.topic_dead_lookback_days = int(dead_days)
                cfg.topic_dead_score_factor = float(dead_factor)
                cfg.topic_winner_score_factor = float(winner_factor)
                save_config(cfg)
                st.success("Saved.")

        # Helpers that live outside the form (form_submit_button is the only
        # button allowed *inside* st.form).
        gcol, lcol = st.columns([1, 2])
        with gcol:
            if st.button("🎲 Generate new review token", key="seo_cfg_gen_token"):
                import secrets as _secrets
                st.session_state["_seo_suggested_token"] = _secrets.token_urlsafe(32)
                st.rerun()
        with lcol:
            from seo_agent.report import (
                public_review_url as _pru,
                resolve_public_app_url as _rpau,
            )
            _url = _pru()
            if _url:
                st.success("Public review link is live.")
                st.code(_url, language="text")
            elif (cfg.admin_review_token or "").strip():
                if _rpau():
                    st.info(
                        "Token set and base URL detected, but the link could "
                        "not be built. Double-check the public app URL above."
                    )
                else:
                    st.info(
                        "Token set. Add the deployed Streamlit URL above (or "
                        "publish the app so it can be auto-detected) to enable "
                        "the mobile review link."
                    )
            else:
                st.caption(
                    "Set a review token to enable the public mobile review "
                    "link — the app URL is auto-detected after deploy."
                )

        st.markdown("---")
        st.markdown("##### 👥 Named reviewer tokens")
        st.caption(
            "Issue a separate token to each operator so approvals are "
            "attributed to a real person in the run history."
        )
        existing = list(cfg.admin_review_tokens or [])
        if existing:
            from urllib.parse import urlencode as _urlenc
            from seo_agent.report import resolve_public_app_url as _rpau2
            base_url = (_rpau2() or "").strip()
            for idx, ent in enumerate(existing):
                ent_name = ent.get("name", "")
                ent_token = ent.get("token", "")
                cn, ct, cu, cd = st.columns([2, 4, 4, 1])
                cn.markdown(f"**{ent_name or '(unnamed)'}**")
                ct.code((ent_token[:8] + "…") if ent_token else "—",
                        language="text")
                if base_url and ent_token:
                    cu.code(
                        f"{base_url.rstrip('/')}/?{_urlenc({'review_token': ent_token})}",
                        language="text",
                    )
                else:
                    cu.caption("Set the public app URL above to see link")
                if cd.button("🗑", key=f"del_named_token_{idx}",
                             help="Remove this token"):
                    cfg.admin_review_tokens = [
                        e for i, e in enumerate(existing) if i != idx
                    ]
                    save_config(cfg)
                    st.rerun()
        else:
            st.caption("No named tokens yet.")

        with st.form("seo_add_named_token"):
            ac1, ac2 = st.columns([3, 2])
            new_name = ac1.text_input("Reviewer name (e.g. alice)",
                                       key="new_token_name")
            _suggested_named = st.session_state.pop(
                "_seo_suggested_named_token", "")
            new_token = ac2.text_input("Token", value=_suggested_named,
                                        key="new_token_value",
                                        help="Click 'Generate' below the form "
                                             "to create a strong random one.")
            if st.form_submit_button("➕ Add named token"):
                nm = (new_name or "").strip()
                tk = (new_token or "").strip()
                if not nm or not tk:
                    st.error("Both a name and a token are required.")
                elif any((e.get("name") or "").strip() == nm
                         for e in (cfg.admin_review_tokens or [])):
                    st.error(f"A token named '{nm}' already exists.")
                else:
                    cfg.admin_review_tokens = list(cfg.admin_review_tokens or []) + [
                        {"name": nm, "token": tk}
                    ]
                    save_config(cfg)
                    st.success(f"Added token for '{nm}'.")
                    st.rerun()
        if st.button("🎲 Generate token for a new reviewer",
                     key="gen_named_token"):
            import secrets as _secrets
            st.session_state["_seo_suggested_named_token"] = _secrets.token_urlsafe(32)
            st.rerun()

    with sub_tabs[5]:
        st.markdown("#### Recent runs")
        if not recent_runs:
            st.info("No runs recorded yet.")

        def _source_badge(src: str) -> str:
            s = (src or "").lower()
            if s == "admin":
                return "🛠️ admin panel"
            if s == "public_link":
                return "📱 public link"
            if s == "auto":
                return "🤖 auto-publish"
            return src or "—"

        for r in recent_runs:
            label = (f"{r.started_at.strftime('%Y-%m-%d %H:%M')} · {r.status} · "
                     f"{r.drafts_created or 0} drafts · ${r.estimated_cost_usd or 0:.3f}")
            with st.expander(label):
                # Per-run draft decisions: show who approved/rejected what
                # and from which channel so we have an audit trail.
                sess_h = get_session()
                try:
                    run_drafts = (sess_h.query(AgentDraft)
                                  .filter(AgentDraft.run_id == r.id)
                                  .order_by(AgentDraft.created_at.asc())
                                  .all())
                finally:
                    sess_h.close()
                if run_drafts:
                    rows = []
                    for rd in run_drafts:
                        rows.append({
                            "kind": rd.kind,
                            "title": rd.title,
                            "status": rd.status,
                            "source": _source_badge(rd.review_source),
                            "reviewer": rd.reviewed_by or "—",
                            "reviewed_at": (rd.reviewed_at.strftime("%Y-%m-%d %H:%M")
                                            if rd.reviewed_at else "—"),
                        })
                    st.markdown("**Draft decisions**")
                    st.dataframe(pd.DataFrame(rows), use_container_width=True,
                                 hide_index=True)
                st.markdown("**Run summary**")
                st.json(r.summary or {})
                if r.errors:
                    st.error(r.errors[:2000])


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

# --------------------------------------------------------------------------
# Data Modelling — relationships between datasets (Task #29).
# Loads each saved dataset's *cleaned* dataframe (active step output) so
# suggestions and joins work against the user's curated views, not raw
# uploads. Cached per dataset id + recipe count so flipping between
# datasets stays snappy on million-row frames.
# --------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner=False, max_entries=32)
def _load_dataset_active_df(dataset_id, recipe_sig, owner_uid=None):  # noqa: ARG001 — sig for cache
    """Materialise a saved dataset at its active step. ``recipe_sig`` is a
    cheap fingerprint (recipe count + active index) so the cache busts
    automatically when the user appends or reorders steps elsewhere.

    When ``owner_uid`` is supplied the loader refuses to return any
    dataset whose ``user_id`` does not match — defence-in-depth against
    a tampered dataset id reaching the suggestion engine."""
    db = get_db()
    try:
        DatasetRecord = __import__("models").DatasetRecord
        rec = db.query(DatasetRecord).filter_by(id=dataset_id).first()
        if rec is None or not rec.source_parquet:
            return None
        if owner_uid is not None and rec.user_id != owner_uid:
            return None
        source_df = deserialize_source_df(rec.source_parquet)
        if not rec.step_recipes:
            return source_df
        history = rebuild_history_from_recipes(
            source_df, rec.step_recipes, rec.active_step_index,
        )
        cur = history.current_df()
        return cur if cur is not None else source_df
    except Exception:
        return None
    finally:
        db.close()


def _recipe_signature(rec) -> str:
    """Cheap, deterministic fingerprint for a dataset's recipe state."""
    n = len(rec.step_recipes or [])
    return f"{rec.id}:{n}:{rec.active_step_index or -1}"


def _render_model_section(uid, run_analysis_cb=None, limits=None):
    """Power BI-style relationship modelling tab.

    Lists the user's saved datasets, lets them toggle two or more onto a
    relationship canvas, surfaces auto-suggested join columns, accepts
    confirmed (or fully manual) relationships, persists them, and finally
    materialises a Joined View that can be promoted to the active dataset
    so the rest of the dashboard tabs render against it without any
    special cases."""
    from datetime import datetime
    from data_modelling import (
        suggest_relationships, materialize_join, validate_relationship,
        VALID_JOINS,
    )
    from models import (
        list_relationships, save_relationship, delete_relationship,
        get_user_datasets, delete_dataset_record,
    )

    _section_head(
        "Data Modeling",
        "Combine multiple uploaded datasets the way Power BI does — add "
        "tables to your project, confirm relationships, and the dashboard "
        "tabs will render against the joined view.",
        "03 — Data Modeling",
    )

    if uid is None:
        st.info("Sign in to model relationships across your datasets.")
        return

    # ----- 0. Add tables to the project --------------------------------
    with st.expander("➕ Add tables to this project", expanded=False):
        if run_analysis_cb is None:
            st.caption("Upload a dataset from Overview to add tables to your project.")
        else:
            new_files = st.file_uploader(
                "Upload one or more files (CSV / Excel)",
                type=["csv", "xlsx", "xls"],
                accept_multiple_files=True,
                key=f"model_multi_upload_{uid}",
            )
            if new_files:
                now = datetime.now()
                for nf in new_files:
                    ds_name = nf.name.rsplit(".", 1)[0]
                    try:
                        run_analysis_cb(
                            nf, ds_name, now.month, now.year,
                            limits or get_user_limits(),
                        )
                        st.success(f"Added **{ds_name}** to your project.")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Could not add {nf.name}: {e}")
                st.rerun()

    db = get_db()
    try:
        datasets = get_user_datasets(db, uid,
                                     project_id=st.session_state.get('current_project_id'))
    finally:
        db.close()

    if not datasets:
        st.info("Upload at least two datasets to start modelling relationships.")
        return

    # ----- 1. Dataset cards / canvas ------------------------------------
    canvas_key = f"model_canvas_{uid}"
    st.session_state.setdefault(canvas_key, set())
    canvas_ids: set = st.session_state[canvas_key]

    st.markdown("**Your datasets** — click a card to add/remove from the canvas, or × to delete.")
    cols = st.columns(min(3, max(1, len(datasets))))
    for i, ds in enumerate(datasets):
        col = cols[i % len(cols)]
        with col:
            in_canvas = ds.id in canvas_ids
            label_prefix = "✓ " if in_canvas else "+ "
            card_col, rm_col = st.columns([5, 1])
            with card_col:
                if st.button(
                    f"{label_prefix}{ds.dataset_name}",
                    key=f"model_card_{ds.id}",
                    help=f"{ds.row_count:,} rows · {ds.column_count} cols · "
                         f"updated {ds.upload_date.strftime('%Y-%m-%d')}",
                    use_container_width=True,
                    type=("primary" if in_canvas else "secondary"),
                ):
                    if in_canvas:
                        canvas_ids.discard(ds.id)
                    else:
                        canvas_ids.add(ds.id)
                    st.rerun()
            with rm_col:
                confirm_key = f"model_rm_confirm_{ds.id}"
                if st.session_state.get(confirm_key):
                    if st.button("✓", key=f"model_rm_yes_{ds.id}",
                                 help="Confirm delete", use_container_width=True):
                        db2 = get_db()
                        try:
                            delete_dataset_record(db2, ds.id, uid)
                        finally:
                            db2.close()
                        canvas_ids.discard(ds.id)
                        st.session_state.pop(confirm_key, None)
                        st.success(f"Removed {ds.dataset_name}.")
                        st.rerun()
                else:
                    if st.button("×", key=f"model_rm_{ds.id}",
                                 help="Remove this table from the project",
                                 use_container_width=True):
                        st.session_state[confirm_key] = True
                        st.rerun()
            st.caption(
                f"{ds.row_count:,} rows · {ds.column_count} cols · "
                f"updated {ds.upload_date.strftime('%Y-%m-%d')}"
            )

    if len(canvas_ids) < 2:
        st.markdown("---")
        st.info("Pick at least two datasets to see suggested relationships.")
        return

    # ----- 2. Relationship canvas (chosen datasets) ---------------------
    canvas_records = [d for d in datasets if d.id in canvas_ids]
    canvas_lookup = {d.id: d for d in canvas_records}

    st.markdown("---")
    st.markdown("**Model canvas** — datasets currently in scope:")
    chip_cols = st.columns(min(4, len(canvas_records)))
    for i, ds in enumerate(canvas_records):
        with chip_cols[i % len(chip_cols)]:
            st.markdown(
                f'<div style="padding:0.55rem 0.85rem;border-radius:10px;'
                f'background:rgba(45,212,191,0.10);border:1px solid '
                f'rgba(45,212,191,0.30);font-family:JetBrains Mono,monospace;'
                f'font-size:0.78rem;color:#2dd4bf;letter-spacing:0.05em;">'
                f'{ds.dataset_name}</div>',
                unsafe_allow_html=True,
            )

    # ----- 3. Pair picker + auto-suggestions ----------------------------
    st.markdown("---")
    st.markdown("**Pick a pair to inspect**")
    pc1, pc2 = st.columns(2)
    label_for = lambda d: f"{d.dataset_name} (#{d.id})"
    with pc1:
        left_ds = st.selectbox(
            "Left dataset", canvas_records,
            format_func=label_for, key=f"model_left_{uid}",
        )
    with pc2:
        right_choices = [d for d in canvas_records if d.id != left_ds.id]
        if not right_choices:
            st.info("Add a second dataset to the canvas.")
            return
        right_ds = st.selectbox(
            "Right dataset", right_choices,
            format_func=label_for, key=f"model_right_{uid}",
        )

    left_df = _load_dataset_active_df(left_ds.id, _recipe_signature(left_ds), owner_uid=uid)
    right_df = _load_dataset_active_df(right_ds.id, _recipe_signature(right_ds), owner_uid=uid)
    if left_df is None or right_df is None:
        st.warning("Could not load one of the datasets — re-open it from the Overview tab to refresh.")
        return

    suggestions = suggest_relationships(left_df, right_df)
    st.markdown("**Suggested relationships**")
    if suggestions:
        for s in suggestions:
            row_l, row_m, row_r = st.columns([3, 2, 1])
            with row_l:
                st.markdown(
                    f"`{left_ds.dataset_name}.{s.left_column}` ↔ "
                    f"`{right_ds.dataset_name}.{s.right_column}`"
                )
                st.caption(
                    f"name {s.name_score:.2f} · dtype {s.dtype_score:.2f} · "
                    f"overlap {s.overlap_score:.2f}"
                )
            with row_m:
                st.markdown(
                    f"**{s.cardinality}** · {int(s.confidence * 100)}% confidence"
                )
            with row_r:
                if st.button(
                    "Confirm",
                    key=f"model_confirm_{left_ds.id}_{right_ds.id}_"
                        f"{s.left_column}_{s.right_column}",
                    type="primary",
                ):
                    db = get_db()
                    try:
                        save_relationship(
                            db, uid,
                            left_dataset_id=left_ds.id, left_column=s.left_column,
                            right_dataset_id=right_ds.id, right_column=s.right_column,
                            cardinality=s.cardinality, join_type="left",
                        )
                    finally:
                        db.close()
                    st.success("Relationship saved.")
                    st.rerun()
    else:
        st.caption("No automatic suggestions reached the confidence threshold "
                   "for this pair — define one manually below.")

    # ----- 4. Manual relationship form ----------------------------------
    with st.expander("Define a relationship manually", expanded=not suggestions):
        m1, m2 = st.columns(2)
        with m1:
            l_col = st.selectbox(
                f"{left_ds.dataset_name} column",
                list(left_df.columns), key=f"model_man_lcol_{uid}",
            )
        with m2:
            r_col = st.selectbox(
                f"{right_ds.dataset_name} column",
                list(right_df.columns), key=f"model_man_rcol_{uid}",
            )
        m3, m4 = st.columns(2)
        with m3:
            cardinality = st.selectbox(
                "Cardinality", ["1:1", "1:N", "N:1", "N:N"],
                index=1, key=f"model_man_card_{uid}",
            )
        with m4:
            join_type = st.selectbox(
                "Join type", list(VALID_JOINS),
                index=1, key=f"model_man_join_{uid}",
            )
        diag = validate_relationship(left_df, right_df, l_col, r_col)
        if "error" in diag:
            st.warning(diag["error"])
        elif diag.get("warning"):
            st.warning(diag["warning"])
        else:
            st.caption(
                f"{diag['matching_keys']} matching key value(s) — "
                f"left distinct: {diag['left_distinct_keys']}, "
                f"right distinct: {diag['right_distinct_keys']}, "
                f"cardinality: {diag['cardinality']}"
            )
        if st.button("Save manual relationship", key=f"model_man_save_{uid}"):
            db = get_db()
            try:
                rel = save_relationship(
                    db, uid,
                    left_dataset_id=left_ds.id, left_column=l_col,
                    right_dataset_id=right_ds.id, right_column=r_col,
                    cardinality=cardinality, join_type=join_type,
                )
            finally:
                db.close()
            if rel is None:
                st.warning("That relationship looks like a self-join on the same column — skipped.")
            else:
                st.success("Relationship saved.")
                st.rerun()

    # ----- 5. Saved relationships --------------------------------------
    db = get_db()
    try:
        rels = list_relationships(db, uid)
    finally:
        db.close()

    st.markdown("---")
    st.markdown("**Saved relationships**")
    if not rels:
        st.caption("No relationships saved yet.")
    else:
        ds_name = {d.id: d.dataset_name for d in datasets}
        for rel in rels:
            r_l, r_r = st.columns([6, 1])
            with r_l:
                left_name = ds_name.get(rel.left_dataset_id,
                                        f"#{rel.left_dataset_id}")
                right_name = ds_name.get(rel.right_dataset_id,
                                         f"#{rel.right_dataset_id}")
                st.markdown(
                    f"`{left_name}.{rel.left_column}` → "
                    f"`{right_name}.{rel.right_column}` · "
                    f"{rel.cardinality} · {rel.join_type} join"
                )
            with r_r:
                if st.button("Remove", key=f"model_del_{rel.id}"):
                    db = get_db()
                    try:
                        delete_relationship(db, uid, rel.id)
                    finally:
                        db.close()
                    st.rerun()

    # ----- 6. Joined View preview & promotion ---------------------------
    st.markdown("---")
    st.markdown("**Joined view**")
    jv1, jv2 = st.columns([3, 1])
    with jv1:
        st.caption(
            f"Materialise `{left_ds.dataset_name}` joined with "
            f"`{right_ds.dataset_name}` using the matching saved "
            "relationship (or the manual form above if you haven't saved one)."
        )
    with jv2:
        join_pick = st.selectbox(
            "Join", list(VALID_JOINS), index=1, key=f"model_jv_join_{uid}",
        )

    # Find the most recent saved relationship for this pair, fall back
    # to the manual form's current selection.
    saved = next(
        (r for r in rels
         if {r.left_dataset_id, r.right_dataset_id} ==
            {left_ds.id, right_ds.id}),
        None,
    )
    if saved and saved.left_dataset_id == left_ds.id:
        eff_lcol, eff_rcol = saved.left_column, saved.right_column
    elif saved:
        eff_lcol, eff_rcol = saved.right_column, saved.left_column
    else:
        eff_lcol, eff_rcol = l_col, r_col

    if st.button("Build joined view", key=f"model_build_jv_{uid}",
                 type="primary"):
        try:
            joined = materialize_join(
                left_df, right_df, eff_lcol, eff_rcol,
                join_type=join_pick,
                left_label=left_ds.dataset_name[:12].replace(" ", "_") or "left",
                right_label=right_ds.dataset_name[:12].replace(" ", "_") or "right",
            )
        except Exception as e:
            st.error(f"Join failed: {e}")
            joined = None
        if joined is not None:
            st.session_state[f"model_jv_df_{uid}"] = joined
            st.session_state[f"model_jv_meta_{uid}"] = {
                "left": left_ds.dataset_name, "right": right_ds.dataset_name,
                "left_col": eff_lcol, "right_col": eff_rcol,
                "join": join_pick,
            }

    jv_df = st.session_state.get(f"model_jv_df_{uid}")
    jv_meta = st.session_state.get(f"model_jv_meta_{uid}")
    if jv_df is not None and jv_meta is not None:
        st.success(
            f"Joined view ready — {len(jv_df):,} rows × {len(jv_df.columns)} cols "
            f"({jv_meta['left']} ⋈ {jv_meta['right']} on "
            f"{jv_meta['left_col']} = {jv_meta['right_col']}, {jv_meta['join']} join)"
        )
        st.dataframe(jv_df.head(20), use_container_width=True)
        if st.button(
            "Use joined view as active dataset",
            key=f"model_promote_jv_{uid}",
            type="primary",
        ):
            # Synthesise a fresh dataset id + step history holding the
            # joined frame as a single Source step. Existing tabs read
            # from `current_dataset_id` + `step_histories`, so once we
            # flip those they pick the joined view up automatically.
            from datetime import datetime as _dt
            jv_id = f"joined_{_dt.utcnow().strftime('%Y%m%d_%H%M%S')}"
            jv_history = StepHistory()
            jv_history.add(
                "Source",
                f"Joined view: {jv_meta['left']} ⋈ {jv_meta['right']}",
                jv_df, meta={"is_joined_view": True, **jv_meta},
            )
            st.session_state.current_dataset_id = jv_id
            st.session_state.step_histories[jv_id] = jv_history
            st.session_state.df = jv_df
            st.session_state.df_cleaned = jv_df
            st.session_state.cleaning_report = None
            st.session_state.dashboard_section = _TAB_LABELS[0]
            st.success("Switched to the joined view — open Overview to start analysing it.")
            st.rerun()


def _clear_workspace_state():
    """Wipe per-dataset state when leaving a project so the next project starts clean."""
    for k in ('df', 'df_cleaned', 'analysis_results', 'ai_insights',
              'cleaning_report', 'inferred_schema_obj', 'similar_datasets',
              '_auto_analyzed_sig'):
        if k in st.session_state:
            st.session_state[k] = None if k != 'similar_datasets' else []
    st.session_state.chat_messages = []
    st.session_state.current_dataset_id = None
    # Per-dataset dicts can stay (they're keyed by dataset id) but the
    # active pointer is cleared so the dashboard re-prompts for an upload.


def _open_project(project_id, project_name):
    """Set the active project and route into the dashboard."""
    _clear_workspace_state()
    st.session_state.current_project_id = project_id
    st.session_state.current_project_name = project_name
    db = get_db()
    try:
        touch_project(db, project_id, st.session_state.user.get('id'))
    finally:
        db.close()
    st.session_state.page = 'dashboard'


def _projects_page_css():
    """CSS for the Projects landing page — bento grid, Data Noir aesthetic."""
    return """
<style>
.proj-shell { max-width: 1240px; margin: 0 auto; padding: 1.25rem 0 4rem; }
.proj-eyebrow {
    font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
    letter-spacing: 0.22em; text-transform: uppercase;
    color: var(--teal); opacity: 0.85; margin-bottom: 0.55rem;
}
.proj-h1 {
    font-family: 'Syne', sans-serif; font-weight: 800;
    font-size: 2.6rem; line-height: 1.05; color: #e2e8f0;
    margin: 0 0 0.6rem 0; letter-spacing: -0.015em;
}
.proj-h1 .accent {
    background: linear-gradient(120deg, var(--teal) 0%, #94f0e2 60%, #cbd5e1 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.proj-sub {
    color: #94a3b8; font-size: 1.02rem; max-width: 640px;
    line-height: 1.55; margin: 0 0 2.2rem 0;
}
.proj-stats {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px;
    margin: 0 0 2rem 0;
}
.proj-stat {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 14px; padding: 1.15rem 1.3rem;
}
.proj-stat-num {
    font-family: 'JetBrains Mono', monospace; font-size: 1.65rem;
    color: #e2e8f0; font-weight: 600; letter-spacing: -0.01em;
    font-variant-numeric: tabular-nums;
}
.proj-stat-label {
    font-size: 0.74rem; color: #64748b; text-transform: uppercase;
    letter-spacing: 0.14em; margin-top: 0.35rem;
}
.proj-section-head {
    display: flex; align-items: center; justify-content: space-between;
    margin: 1.4rem 0 0.4rem 0;
    padding-bottom: 0.7rem;
    border-bottom: 1px solid rgba(148,163,184,0.10);
}
.proj-section-title {
    font-family: 'Syne', sans-serif; font-weight: 700;
    font-size: 1.05rem; color: #cbd5e1; letter-spacing: 0.02em;
    display: flex; align-items: baseline; gap: 0.7rem;
}
.proj-section-title .count-pill {
    font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
    color: #94a3b8; letter-spacing: 0.10em;
    background: rgba(148,163,184,0.08);
    border: 1px solid rgba(148,163,184,0.14);
    padding: 0.18rem 0.55rem; border-radius: 999px;
    font-variant-numeric: tabular-nums;
}
.proj-section-meta {
    font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
    color: #475569; letter-spacing: 0.14em;
}
/* === LIST-MENU rows (replaces bento card grid) ====================== */
.proj-list { margin: 0.2rem 0 0 0; }
.proj-row {
    position: relative;
    padding: 1.05rem 1.1rem 1.05rem 1.25rem;
    border-bottom: 1px solid rgba(148,163,184,0.07);
    transition: background 180ms ease;
    overflow: hidden;
    min-height: 76px;
    display: flex; flex-direction: column; justify-content: center;
}
.proj-row::before {
    content: ""; position: absolute; left: 0; top: 14%; bottom: 14%;
    width: 2px; background: var(--teal);
    transform: scaleY(0); transform-origin: center;
    transition: transform 220ms ease;
    border-radius: 2px;
}
.proj-row:hover {
    background: linear-gradient(90deg,
        rgba(45,212,191,0.04) 0%, rgba(45,212,191,0) 80%);
}
.proj-row:hover::before { transform: scaleY(1); }
.proj-row-title {
    font-family: 'Syne', sans-serif; font-weight: 700;
    font-size: 1.05rem; color: #e2e8f0; margin: 0;
    line-height: 1.25; letter-spacing: -0.005em;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.proj-row-desc {
    color: #94a3b8; font-size: 0.82rem; line-height: 1.45;
    margin: 0.25rem 0 0 0;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    max-width: 56ch;
}
.proj-row-desc.empty { color: #475569; font-style: italic; }
.proj-row-meta {
    display: flex; gap: 1.4rem; align-items: center;
    justify-content: flex-end; height: 100%;
    font-family: 'JetBrains Mono', monospace; font-size: 0.74rem;
    color: #64748b; letter-spacing: 0.04em;
    font-variant-numeric: tabular-nums;
}
.proj-row-meta .stat { display: flex; flex-direction: column; align-items: flex-end; gap: 0.15rem; }
.proj-row-meta .stat .v { color: #cbd5e1; font-size: 0.86rem; font-weight: 500; }
.proj-row-meta .stat .l { color: #475569; font-size: 0.62rem;
    letter-spacing: 0.14em; text-transform: uppercase; }
.proj-row-meta .when {
    color: #64748b; font-size: 0.74rem; letter-spacing: 0.06em;
    border-left: 1px solid rgba(148,163,184,0.12);
    padding-left: 1.4rem;
}
/* Small "+ New project" ghost pill in the section header.
   Targets the 2nd column of the section-head row. */
.proj-newpill-slot [data-testid="stButton"] > button {
    background: transparent !important;
    border: 1px solid rgba(45,212,191,0.40) !important;
    color: var(--teal) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important; font-size: 0.82rem !important;
    padding: 0.35rem 0.95rem !important;
    border-radius: 999px !important;
    letter-spacing: 0.02em !important;
    transition: background 180ms ease, border-color 180ms ease, transform 160ms ease !important;
    min-height: 34px !important; height: 34px !important;
    width: auto !important;
}
.proj-newpill-slot [data-testid="stButton"] > button:hover {
    background: rgba(45,212,191,0.10) !important;
    border-color: var(--teal) !important;
    transform: translateY(-1px);
}
.proj-newpill-slot [data-testid="stButton"] { display: flex; justify-content: flex-end; }
.proj-empty {
    text-align: center; padding: 4rem 2rem;
    background: var(--surface); border: 1px dashed var(--border);
    border-radius: 18px;
}
.proj-empty-icon {
    width: 64px; height: 64px; border-radius: 16px; margin: 0 auto 1.2rem;
    background: rgba(45,212,191,0.10); color: var(--teal);
    display: flex; align-items: center; justify-content: center;
    font-size: 1.8rem; font-weight: 300;
    border: 1px solid rgba(45,212,191,0.25);
}
.proj-empty-title {
    font-family: 'Syne', sans-serif; font-weight: 700;
    color: #e2e8f0; font-size: 1.45rem; margin: 0 0 0.5rem;
}
.proj-empty-sub { color: #94a3b8; max-width: 420px; margin: 0 auto 1.5rem;
    line-height: 1.55; font-size: 0.95rem; }

/* The Open / Rename / Delete row that sits under each card uses default
   Streamlit buttons — restyled so they match the card aesthetic. */
[data-testid="stButton"] > button[kind="primary"].proj-open {
    background: var(--teal); color: #0c1829; border: none; font-weight: 600;
}
/* === New Project Dialog (st.dialog modal) ============================ */
/* Backdrop dim */
[data-testid="stDialog"] > div:first-child,
div[role="dialog"] > div:first-child {
    background: rgba(2, 8, 18, 0.72) !important;
    backdrop-filter: blur(6px);
    -webkit-backdrop-filter: blur(6px);
}
/* Modal panel */
[data-testid="stDialog"] [role="dialog"],
div[role="dialog"][aria-modal="true"] {
    background: linear-gradient(180deg, #0c1829 0%, #07101f 100%) !important;
    background-color: #0c1829 !important;
    border: 1px solid rgba(45,212,191,0.28) !important;
    border-radius: 18px !important;
    box-shadow: 0 32px 80px rgba(0,0,0,0.6),
                0 0 0 1px rgba(45,212,191,0.06),
                inset 0 1px 0 rgba(255,255,255,0.02) !important;
    padding: 1.4rem 1.6rem 1.4rem !important;
    color: #cbd5e1 !important;
}
/* Modal title row (Streamlit shows the dialog title at the top) */
[data-testid="stDialog"] h1,
[data-testid="stDialog"] h2,
[data-testid="stDialog"] h3,
div[role="dialog"] h1,
div[role="dialog"] h2,
div[role="dialog"] h3 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 800 !important;
    color: #f1f5f9 !important;
    font-size: 1.55rem !important;
    letter-spacing: -0.01em !important;
    margin: 0 0 0.85rem 0 !important;
}
/* Cascade transparent on inner Streamlit containers */
[data-testid="stDialog"] [data-testid="stVerticalBlock"],
[data-testid="stDialog"] [data-testid="stHorizontalBlock"],
[data-testid="stDialog"] [data-testid="stColumn"],
[data-testid="stDialog"] [data-testid="stForm"],
[data-testid="stDialog"] [data-testid="stMarkdownContainer"] {
    background: transparent !important;
    background-color: transparent !important;
    color: #cbd5e1 !important;
}
/* Eyebrow + helper microcopy in our dialog header */
.proj-dialog-eyebrow {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.66rem; letter-spacing: 0.22em;
    text-transform: uppercase; color: var(--teal);
    margin-bottom: 0.5rem; opacity: 0.9;
}
.proj-dialog-sub {
    color: #94a3b8; font-size: 0.88rem; line-height: 1.55;
    margin-bottom: 1.25rem;
}
.proj-dialog-actions { margin-top: 0.4rem; }
/* Field labels inside dialog */
[data-testid="stDialog"] label,
[data-testid="stDialog"] [data-testid="stWidgetLabel"] p {
    color: #cbd5e1 !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.82rem !important; font-weight: 600 !important;
    letter-spacing: 0.01em !important;
}
/* Neutralize BaseWeb input wrappers inside dialog */
[data-testid="stDialog"] [data-baseweb="input"],
[data-testid="stDialog"] [data-baseweb="base-input"],
[data-testid="stDialog"] [data-baseweb="textarea"] {
    background: transparent !important;
    background-color: transparent !important;
    border: none !important;
}
/* Inputs */
[data-testid="stDialog"] input[type="text"],
[data-testid="stDialog"] textarea {
    background: rgba(7,16,31,0.85) !important;
    background-color: rgba(7,16,31,0.85) !important;
    color: #f1f5f9 !important;
    -webkit-text-fill-color: #f1f5f9 !important;
    border: 1px solid rgba(148,163,184,0.22) !important;
    border-radius: 10px !important;
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.95rem !important;
    padding: 0.7rem 0.85rem !important;
    caret-color: var(--teal) !important;
    transition: border-color 160ms ease, box-shadow 160ms ease !important;
}
[data-testid="stDialog"] input[type="text"]::placeholder,
[data-testid="stDialog"] textarea::placeholder {
    color: #64748b !important;
}
[data-testid="stDialog"] input[type="text"]:focus,
[data-testid="stDialog"] textarea:focus {
    border-color: rgba(45,212,191,0.55) !important;
    box-shadow: 0 0 0 3px rgba(45,212,191,0.14) !important;
    outline: none !important;
}
/* Character counter */
[data-testid="stDialog"] [data-testid="InputInstructions"] {
    color: #475569 !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.68rem !important;
}
/* Footer button row */
[data-testid="stDialog"] [data-testid="stForm"] [data-testid="stHorizontalBlock"] {
    gap: 0.65rem !important;
    padding-top: 0.6rem !important;
    border-top: 1px solid rgba(148,163,184,0.10) !important;
    margin-top: 0.85rem !important;
}
[data-testid="stDialog"] button[kind="primary"],
[data-testid="stDialog"] button[kind="primaryFormSubmit"] {
    background: var(--teal) !important;
    color: #07101f !important;
    border: 1px solid var(--teal) !important;
    font-weight: 700 !important;
    font-family: 'DM Sans', sans-serif !important;
    border-radius: 10px !important;
    padding: 0.65rem 1.1rem !important;
    box-shadow: 0 8px 24px -8px rgba(45,212,191,0.4) !important;
    transition: transform 140ms ease, box-shadow 140ms ease !important;
}
[data-testid="stDialog"] button[kind="primary"]:hover,
[data-testid="stDialog"] button[kind="primaryFormSubmit"]:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 30px -8px rgba(45,212,191,0.55) !important;
}
[data-testid="stDialog"] button[kind="secondary"],
[data-testid="stDialog"] button[kind="secondaryFormSubmit"] {
    background: transparent !important;
    color: #94a3b8 !important;
    border: 1px solid rgba(148,163,184,0.22) !important;
    font-family: 'DM Sans', sans-serif !important;
    font-weight: 600 !important;
    border-radius: 10px !important;
    padding: 0.65rem 1.1rem !important;
    transition: color 140ms ease, border-color 140ms ease !important;
}
[data-testid="stDialog"] button[kind="secondary"]:hover,
[data-testid="stDialog"] button[kind="secondaryFormSubmit"]:hover {
    color: #f1f5f9 !important;
    border-color: rgba(148,163,184,0.40) !important;
    background: transparent !important;
}
/* Streamlit's built-in dialog close (X) — make it visible on dark */
[data-testid="stDialog"] button[aria-label="Close"],
div[role="dialog"] button[aria-label="Close"] {
    color: #94a3b8 !important;
    background: transparent !important;
}
[data-testid="stDialog"] button[aria-label="Close"]:hover,
div[role="dialog"] button[aria-label="Close"]:hover {
    color: var(--teal) !important;
}
</style>
"""


def _format_relative_time(dt):
    """Compact human-readable 'last opened' string."""
    if dt is None:
        return "just now"
    delta = datetime.utcnow() - dt
    secs = int(delta.total_seconds())
    if secs < 60: return "just now"
    if secs < 3600: return f"{secs // 60}m ago"
    if secs < 86400: return f"{secs // 3600}h ago"
    if secs < 86400 * 7: return f"{secs // 86400}d ago"
    if secs < 86400 * 30: return f"{secs // (86400 * 7)}w ago"
    return dt.strftime("%b %-d, %Y") if hasattr(dt, 'strftime') else "a while ago"


@st.dialog("New project", width="small")
def _show_new_project_dialog(user_id: int):
    """Modal dialog for creating a new project (Data Noir styled)."""
    st.markdown('''
<div class="proj-dialog-head">
  <div class="proj-dialog-eyebrow">Workspace · New</div>
  <div class="proj-dialog-sub">A project is a folder for the sheets, models,
  and chats that belong to one analysis.</div>
</div>
''', unsafe_allow_html=True)

    with st.form("proj_create_dlg_form", clear_on_submit=False):
        new_name = st.text_input(
            "Project name",
            placeholder="e.g. Q2 Sales Review",
            max_chars=120, key="proj_dlg_name")
        new_desc = st.text_area(
            "Description (optional)",
            placeholder="What is this project about?",
            max_chars=500, height=88, key="proj_dlg_desc")
        st.markdown('<div class="proj-dialog-actions">', unsafe_allow_html=True)
        f1, f2 = st.columns([1, 1.4])
        with f1:
            cancelled = st.form_submit_button("Cancel",
                                              use_container_width=True)
        with f2:
            submitted = st.form_submit_button("Create project",
                                              use_container_width=True,
                                              type="primary")
        st.markdown('</div>', unsafe_allow_html=True)

    if cancelled:
        st.rerun()
    if submitted:
        if not (new_name or "").strip():
            st.error("Please enter a project name.")
            return
        _db = get_db()
        try:
            proj = create_project(_db, user_id, new_name, new_desc)
        finally:
            _db.close()
        if proj is None:
            st.error("Could not create project. Please try again.")
            return
        _open_project(proj.id, proj.name)
        st.rerun()


def show_projects_page():
    """Post-login landing page: a grid of the user's projects."""
    if not st.session_state.user:
        st.session_state.page = 'login'
        st.rerun()
        return

    user = st.session_state.user
    user_id = user.get('id')

    # Trial gate — same logic as the dashboard.
    db = get_db()
    try:
        user_obj = get_user_by_id(db, user_id)
        if user_obj and not check_trial_active(user_obj):
            st.markdown('''
            <div style="text-align: center; padding: 3rem;">
                <h2 style="color: #e2e8f0;">Your Free Trial Has Ended</h2>
                <p style="color: #94a3b8; max-width: 520px; margin: 1rem auto;">
                    Your 60-day trial period has expired. Contact our team for activation.
                </p>
                <p style="color: var(--teal);">muayad.demaidi.work@gmail.com</p>
            </div>
            ''', unsafe_allow_html=True)
            show_support_section()
            return
        # One-shot back-fill for users who had datasets before projects existed.
        ensure_default_project_for_user(db, user_id)
        projects = list_user_projects(db, user_id)
    finally:
        db.close()

    st.markdown(_projects_page_css(), unsafe_allow_html=True)

    display_name = user.get('full_name') or user.get('username') or 'Analyst'
    avatar_letter = (display_name[:1] or 'A').upper()
    first_name = display_name.split()[0] if display_name else 'Analyst'

    # ── Top bar: brand + account popover (mirrors dashboard chrome) ──────
    nav_brand_col, _, nav_user_col = st.columns([5, 0.3, 1.6], gap="small")
    with nav_brand_col:
        st.markdown(
            '<div class="dn-topbar">'
            '<span class="dn-topbar-brand">DataVision <span style="color:var(--teal);">Pro</span></span>'
            '<span class="dn-topbar-eyebrow">Projects</span>'
            '</div>', unsafe_allow_html=True)
    with nav_user_col:
        st.markdown('<div class="dn-pop-trigger-marker"></div>', unsafe_allow_html=True)
        with st.popover(f"{avatar_letter}   {first_name}   ▾", use_container_width=True):
            tier_label = {"tier1": "Tier 01 · Starter", "tier2": "Tier 02 · Growth",
                          "tier3": "Tier 03 · Full Access"}.get(
                user.get('subscription_type', 'tier3'), "Tier 03 · Full Access")
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
            if user.get('is_admin'):
                if st.button("  Admin Panel", use_container_width=True, key="proj_pop_admin"):
                    st.session_state.page = 'admin'; st.rerun()
            if st.button("→   Sign Out", use_container_width=True, key="proj_pop_signout"):
                _uid = user_id
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
                except Exception:
                    pass
                _clear_workspace_state()
                st.session_state.current_project_id = None
                st.session_state.current_project_name = None
                st.session_state.user = None
                st.session_state.page = 'home'
                st.rerun()

    st.markdown('<div class="proj-shell">', unsafe_allow_html=True)

    # ── Hero header ────────────────────────────────────────────────────
    st.markdown(f'''
<div class="proj-eyebrow">Workspace</div>
<h1 class="proj-h1">Welcome back, <span class="accent">{first_name}</span>.</h1>
<p class="proj-sub">Each project is a folder for the sheets, models, and chats
that belong to one analysis. Open one to keep going, or start a fresh one.</p>
''', unsafe_allow_html=True)

    # ── Quick stats ────────────────────────────────────────────────────
    total_projects = len(projects)
    total_sheets = sum(p['sheet_count'] for p in projects)
    total_rows = sum(p['total_rows'] for p in projects)
    st.markdown(f'''
<div class="proj-stats">
  <div class="proj-stat">
    <div class="proj-stat-num">{total_projects}</div>
    <div class="proj-stat-label">Projects</div>
  </div>
  <div class="proj-stat">
    <div class="proj-stat-num">{total_sheets}</div>
    <div class="proj-stat-label">Sheets</div>
  </div>
  <div class="proj-stat">
    <div class="proj-stat-num">{total_rows:,}</div>
    <div class="proj-stat-label">Rows analysed</div>
  </div>
</div>
''', unsafe_allow_html=True)

    # ── Empty state ────────────────────────────────────────────────────
    if not projects:
        st.markdown('''
<div class="proj-empty">
  <div class="proj-empty-icon">+</div>
  <div class="proj-empty-title">No projects yet</div>
  <p class="proj-empty-sub">Spin up your first project to start uploading
sheets, building models, and chatting with the data.</p>
</div>
''', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([1, 1.2, 1])
        with c2:
            if st.button("Create your first project",
                         use_container_width=True, type="primary",
                         key="proj_empty_create"):
                _show_new_project_dialog(user_id)
                return
        st.markdown('</div>', unsafe_allow_html=True)
        return

    # ── Section heading: title + count + small "+ New project" pill ──
    sh_title, sh_action = st.columns([5, 1.2], gap="small")
    with sh_title:
        st.markdown(f'''
<div class="proj-section-head" style="border:none;padding-bottom:0;margin-bottom:0;">
  <div class="proj-section-title">
    Your projects <span class="count-pill">{total_projects:02d}</span>
  </div>
</div>
''', unsafe_allow_html=True)
    with sh_action:
        st.markdown('<div class="proj-newpill-slot">', unsafe_allow_html=True)
        if st.button("+  New project", key="proj_new_pill_btn"):
            _show_new_project_dialog(user_id)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="border-bottom:1px solid rgba(148,163,184,0.10);'
        'margin:0.4rem 0 0.2rem 0;"></div>',
        unsafe_allow_html=True)

    # ── Project list-menu (one row per project) ───────────────────────
    st.markdown('<div class="proj-list">', unsafe_allow_html=True)
    for p in projects:
        desc = (p["description"] or "").strip()
        desc_html = (f'<div class="proj-row-desc">{desc}</div>'
                     if desc else
                     '<div class="proj-row-desc empty">No description</div>')
        sheets_n = p['sheet_count']
        rows_n = p['total_rows'] or 0
        rel = _format_relative_time(p['last_opened_at'] or p['created_at'])

        row_main, row_meta, row_open, row_more = st.columns(
            [3.6, 2.6, 0.95, 0.55], gap="small")
        with row_main:
            st.markdown(f'''
<div class="proj-row">
  <div class="proj-row-title">{p["name"]}</div>
  {desc_html}
</div>
''', unsafe_allow_html=True)
        with row_meta:
            st.markdown(f'''
<div class="proj-row" style="padding-top:1.05rem;padding-bottom:1.05rem;">
  <div class="proj-row-meta">
    <div class="stat"><span class="v">{sheets_n}</span><span class="l">sheets</span></div>
    <div class="stat"><span class="v">{rows_n:,}</span><span class="l">rows</span></div>
    <span class="when">{rel}</span>
  </div>
</div>
''', unsafe_allow_html=True)
        with row_open:
            st.markdown('<div style="padding-top:1.15rem;">', unsafe_allow_html=True)
            if st.button("Open  →", key=f"proj_open_{p['id']}",
                         use_container_width=True, type="primary"):
                _open_project(p['id'], p['name'])
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with row_more:
            st.markdown(
                '<div class="proj-row-more-marker" style="padding-top:1.15rem;">',
                unsafe_allow_html=True)
            with st.popover("•••", use_container_width=True):
                st.caption("Manage project")
                new_label = st.text_input(
                    "Rename", value=p['name'],
                    key=f"proj_rename_{p['id']}",
                    label_visibility="collapsed",
                    placeholder="New name")
                if st.button("Save name", use_container_width=True,
                             key=f"proj_save_{p['id']}"):
                    _db = get_db()
                    try:
                        update_project(_db, p['id'], user_id, name=new_label)
                    finally:
                        _db.close()
                    st.rerun()
                st.markdown("---")
                confirm_key = f"proj_del_confirm_{p['id']}"
                if st.session_state.get(confirm_key):
                    st.caption(f"This deletes **{p['name']}** and "
                               f"all {p['sheet_count']} sheet(s).")
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("Yes, delete",
                                     use_container_width=True,
                                     key=f"proj_del_yes_{p['id']}"):
                            _db = get_db()
                            try:
                                delete_project(_db, p['id'], user_id)
                            finally:
                                _db.close()
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                    with cc2:
                        if st.button("Cancel",
                                     use_container_width=True,
                                     key=f"proj_del_no_{p['id']}"):
                            st.session_state.pop(confirm_key, None)
                            st.rerun()
                else:
                    if st.button("Delete project",
                                 use_container_width=True,
                                 key=f"proj_del_{p['id']}"):
                        st.session_state[confirm_key] = True
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)  # close .proj-list

    st.markdown('</div>', unsafe_allow_html=True)  # close .proj-shell


def show_dashboard():
    limits = get_user_limits()
    logo_b64 = get_logo_base64()

    # Hard gate: dashboard only renders inside an open project. If the user
    # arrived here without one (e.g. deep-link refresh, or after sign-out),
    # bounce back to the Projects page so dataset queries stay scoped.
    if st.session_state.user and not st.session_state.get('current_project_id'):
        st.session_state.page = 'projects'
        st.rerun()
        return

    if st.session_state.user:
        user_id = st.session_state.user.get('id')
        # Re-validate that the project still belongs to this user.
        _pdb = get_db()
        try:
            _proj = get_project(_pdb, st.session_state.current_project_id, user_id)
            if _proj is None:
                st.session_state.current_project_id = None
                st.session_state.current_project_name = None
                st.session_state.page = 'projects'
                _pdb.close()
                st.rerun()
                return
            st.session_state.current_project_name = _proj.name
            touch_project(_pdb, _proj.id, user_id)
        finally:
            _pdb.close()
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

    _proj_name = (st.session_state.get('current_project_name') or 'Project').strip()
    _proj_name_safe = (_proj_name[:48] + '…') if len(_proj_name) > 48 else _proj_name
    nav_back_col, nav_brand_col, _, nav_user_col = st.columns(
        [1.2, 4.0, 0.3, 1.6], gap="small")
    with nav_back_col:
        if st.button("← Projects", key="dash_back_projects",
                     use_container_width=True,
                     help="Back to your projects"):
            _clear_workspace_state()
            st.session_state.current_project_id = None
            st.session_state.current_project_name = None
            st.session_state.page = 'projects'
            st.rerun()
    with nav_brand_col:
        st.markdown(f'''
<div class="dn-topbar">
  <span class="dn-topbar-brand">DataVision <span style="color:var(--teal);">Pro</span></span>
  <span class="dn-topbar-eyebrow">Project · {_proj_name_safe}</span>
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
                _clear_workspace_state()
                st.session_state.current_project_id = None
                st.session_state.current_project_name = None
                st.session_state.user = None
                st.session_state.page = 'home'
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
                         delimiter=None, has_header=None, content_hash=None):
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
                # Stamp the content hash so subsequent uploads of the same
                # file can hydrate the saved recipe instead of re-running.
                if content_hash and isinstance(parse_meta, dict):
                    parse_meta['content_hash'] = content_hash
                if len(df_raw) > lmts['max_rows']:
                    st.error(f"Row count ({len(df_raw):,}) exceeds the limit ({lmts['max_rows']:,})")
                    return

                # Build pipeline: Source -> Promoted Headers -> Changed Type -> Cleaning
                # Source step shows the *unpromoted* view (Column1..N + original
                # header sitting as the first data row), exactly like Power
                # Query, so navigating back to it actually shows a different
                # snapshot than Promoted Headers.
                history = StepHistory()
                src_summary = (f"Read {parse_meta.get('kind','file')} — "
                               f"delimiter `{parse_meta.get('delimiter') or 'n/a'}`, "
                               f"encoding `{parse_meta.get('encoding') or 'n/a'}`, "
                               f"{len(df_raw):,} rows × {len(df_raw.columns)} cols")

                if parse_meta.get('has_header'):
                    # Reconstruct the pre-promotion view: original header values
                    # become the first data row, and columns are auto-named.
                    header_row = pd.DataFrame([list(df_raw.columns)],
                                              columns=df_raw.columns)
                    df_unpromoted = pd.concat([header_row, df_raw],
                                              ignore_index=True)
                    df_unpromoted.columns = [f"Column{i+1}" for i in range(len(df_raw.columns))]
                    history.add("Source", src_summary, df_unpromoted,
                                meta={'parse': parse_meta})
                    history.add("Promoted Headers",
                                "First row promoted to column names",
                                df_raw, meta={})
                else:
                    history.add("Source", src_summary, df_raw,
                                meta={'parse': parse_meta})
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
                # Users can later reorder, insert, or remove substeps, and
                # tune each substep's threshold params (cap %, IQR×, …).
                cleaning_plan = _default_cleaning_plan()
                df_cleaned, cleaning_report = _apply_cleaning_substeps(
                    history, df_typed, cleaning_plan
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
                        project_id=st.session_state.get('current_project_id'),
                        source_parquet=source_blob,
                        parse_meta=parse_meta if isinstance(parse_meta, dict) else None,
                        step_recipes=history.to_recipes(),
                        active_step_index=history.active_index,
                    )
                    st.session_state.current_dataset_id = record.id
                    st.session_state.step_histories[record.id] = history
                    st.session_state.inferred_schema[record.id] = [s.to_dict() for s in schema]
                    st.session_state.type_overrides[record.id] = {}
                    st.session_state.cleaning_substep_plans[record.id] = cleaning_plan
                    st.session_state.cleaning_substep_states[record.id] = {
                        e["key"]: e["enabled"] for e in cleaning_plan
                    }
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
                        # Auto-run Phase 1 the moment a fresh file is uploaded
                        # (no "Start Analysis" click needed). Sensible defaults:
                        # filename as dataset name, current month/year, sniffed
                        # CSV options. Users can still re-run with a custom
                        # name from the "Upload New Data" panel later. If the
                        # file's content hash matches a previously persisted
                        # dataset that already has a saved recipe, hydrate
                        # from the DB instead of re-running the pipeline.
                        try:
                            file_bytes = uploaded_file.getvalue()
                        except Exception:
                            file_bytes = b''
                        content_hash = hashlib.sha1(file_bytes).hexdigest() if file_bytes else None
                        sig = f"{uploaded_file.name}|{uploaded_file.size}|{content_hash or ''}"
                        if st.session_state.get('_auto_analyzed_sig') != sig:
                            st.session_state['_auto_analyzed_sig'] = sig
                            hydrated = False
                            if content_hash:
                                _uid_now = (st.session_state.user or {}).get('id')
                                if _uid_now:
                                    _hdb = get_db()
                                    try:
                                        _existing = get_user_datasets(
                                            _hdb, _uid_now,
                                            project_id=st.session_state.get('current_project_id'))
                                    except Exception:
                                        _existing = []
                                    finally:
                                        _hdb.close()
                                    for _r in _existing:
                                        _meta = _r.parse_meta or {}
                                        if (_meta.get('content_hash') == content_hash
                                                and _r.source_parquet
                                                and _r.step_recipes):
                                            if _hydrate_dataset_from_db(_r.id):
                                                st.success(
                                                    f"Reopened previous analysis "
                                                    f"of `{uploaded_file.name}` — "
                                                    "no re-run needed.")
                                                hydrated = True
                                                st.rerun()
                                            break
                            if not hydrated:
                                csv_delim, csv_hdr = _csv_options_panel(uploaded_file, "first")
                                run_analysis(
                                    uploaded_file,
                                    uploaded_file.name.rsplit('.', 1)[0],
                                    datetime.now().month, datetime.now().year,
                                    limits, delimiter=csv_delim, has_header=csv_hdr,
                                    content_hash=content_hash,
                                )
                        else:
                            st.success(f"Uploaded: {uploaded_file.name}")
                            st.caption("Auto-analysis already running — please wait…")

                # ── Recent datasets ─ reopen a previously analysed file with
                # its full Applied Steps history rebuilt from the database.
                _u = st.session_state.user or {}
                _uid = _u.get('id')
                if _uid:
                    _rdb = get_db()
                    try:
                        _recent = get_user_datasets(
                            _rdb, _uid,
                            project_id=st.session_state.get('current_project_id'))
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
                        # Same auto-run pattern as the empty-state uploader:
                        # hash the bytes, hydrate from a saved recipe if the
                        # same file was analysed before, otherwise auto-run
                        # Phase 1 immediately. The metadata fields below are
                        # pre-filled from the file and let the user re-run
                        # with a custom name/period if they want.
                        try:
                            new_bytes = new_file.getvalue()
                        except Exception:
                            new_bytes = b''
                        new_hash = hashlib.sha1(new_bytes).hexdigest() if new_bytes else None
                        new_sig = f"new|{new_file.name}|{new_file.size}|{new_hash or ''}"
                        st.success(f"Uploaded: {new_file.name}")
                        col1, col2 = st.columns(2)
                        with col1:
                            period_month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1, key="new_month")
                        with col2:
                            period_year = st.selectbox("Year", range(2020, 2030), index=datetime.now().year - 2020, key="new_year")
                        dataset_name = st.text_input("Dataset Name", value=new_file.name.split('.')[0], key="new_name")
                        csv_delim2, csv_hdr2 = _csv_options_panel(new_file, "next")
                        if st.session_state.get('_auto_analyzed_sig') != new_sig:
                            st.session_state['_auto_analyzed_sig'] = new_sig
                            hydrated = False
                            if new_hash:
                                _uid_now = (st.session_state.user or {}).get('id')
                                if _uid_now:
                                    _hdb = get_db()
                                    try:
                                        _existing = get_user_datasets(
                                            _hdb, _uid_now,
                                            project_id=st.session_state.get('current_project_id'))
                                    except Exception:
                                        _existing = []
                                    finally:
                                        _hdb.close()
                                    for _r in _existing:
                                        _meta = _r.parse_meta or {}
                                        if (_meta.get('content_hash') == new_hash
                                                and _r.source_parquet
                                                and _r.step_recipes):
                                            if _hydrate_dataset_from_db(_r.id):
                                                st.success(
                                                    f"Reopened previous analysis "
                                                    f"of `{new_file.name}` — "
                                                    "no re-run needed.")
                                                hydrated = True
                                                st.rerun()
                                            break
                            if not hydrated:
                                run_analysis(new_file, dataset_name, period_month, period_year,
                                             limits, delimiter=csv_delim2, has_header=csv_hdr2,
                                             content_hash=new_hash)
                        if st.button("Re-run with these settings",
                                     use_container_width=True, key="new_analyze"):
                            run_analysis(new_file, dataset_name, period_month, period_year,
                                         limits, delimiter=csv_delim2, has_header=csv_hdr2,
                                         content_hash=new_hash)
    
            _TAB_LABELS = [
                "Overview",
                "Cleaning",
                "Data Modeling",
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
                                   "Every step (except Source) can be toggled on/off, "
                                   "reordered, or removed — and the chain is recomputed "
                                   "live. Cleaning substeps also expose threshold params "
                                   "under Parameters.")

                        ds_key = _ds_key()
                        # Universal plan: index 0 is Source (locked); the rest
                        # are post-source steps that share the same controls.
                        u_plan = _build_unified_plan(sh)
                        u_idx_by_inst = {e["instance_id"]: i for i, e in enumerate(u_plan)}

                        def _commit_unified(new_plan):
                            _commit_unified_plan(sh, new_plan, ds_key)

                        steps_col, ctrl_col = st.columns([3, 1])
                        with steps_col:
                            for i, step in enumerate(sh.steps):
                                is_source = (i == 0)
                                is_active = (i == sh.active_index)
                                is_future = (i > sh.active_index)
                                meta = step.meta or {}
                                substep_key = meta.get('substep_key')
                                step_inst = meta.get('substep_instance') or meta.get('step_instance')
                                kind = _step_kind(step)
                                enabled = bool(meta.get('enabled', True))
                                pidx = u_idx_by_inst.get(step_inst) if not is_source else None

                                badge = "▶" if is_active else ("◌" if is_future else "✓")
                                color = "#2dd4bf" if is_active else ("#64748b" if is_future else "#94a3b8")
                                weight = "700" if is_active else "500"
                                opacity = "0.55" if is_future else (
                                    "0.55" if (not is_source and not enabled) else "1")
                                # Active row gets a subtle teal-tinted background +
                                # thicker rail so it reads like a selected tab.
                                bg = "rgba(45,212,191,0.08)" if is_active else "transparent"
                                rail = "4px" if is_active else "3px"
                                disabled_tag = (" <span style='color:#f59e0b;font-size:0.7rem;"
                                                "letter-spacing:0.08em;'>· DISABLED</span>"
                                                if not is_source and not enabled else "")
                                locked_tag = (" <span style='color:#64748b;font-size:0.7rem;"
                                              "letter-spacing:0.08em;'>· LOCKED</span>"
                                              if is_source else "")
                                # Source has no controls; everything else gets
                                # ↑ / ↓ / toggle / ✕ in a single layout so the
                                # panel reads as one unified editor.
                                if is_source:
                                    row_l, row_btn = st.columns([0.78, 0.22])
                                    row_ctrls = None
                                else:
                                    row_l, row_ctrls, row_btn = st.columns([0.55, 0.27, 0.18])
                                with row_l:
                                    st.markdown(
                                        f"<div style='padding:0.45rem 0.6rem;border-left:{rail} solid {color};"
                                        f"background:{bg};border-radius:0 6px 6px 0;"
                                        f"opacity:{opacity};font-weight:{weight};color:#e2e8f0;'>"
                                        f"<span style='color:{color};font-family:JetBrains Mono,monospace;"
                                        f"font-size:0.78rem;letter-spacing:0.1em;'>{badge} STEP {i+1}</span>"
                                        f"{locked_tag}{disabled_tag}<br>"
                                        f"<b>{step.name}</b> · <span style='color:#94a3b8;font-size:0.85rem;'>"
                                        f"{step.summary}</span><br>"
                                        f"<span style='color:#64748b;font-size:0.75rem;'>{step.rows:,} rows × {step.cols} cols</span>"
                                        f"</div>",
                                        unsafe_allow_html=True,
                                    )
                                if row_ctrls is not None and pidx is not None:
                                    with row_ctrls:
                                        c_up, c_dn, c_chk, c_rm = st.columns(4)
                                        with c_up:
                                            if st.button(
                                                "↑", key=f"u_up_{ds_key}_{step_inst}",
                                                help="Move this step up",
                                                disabled=(pidx == 0),
                                                use_container_width=True,
                                            ) and pidx > 0:
                                                np_ = list(u_plan)
                                                np_[pidx - 1], np_[pidx] = np_[pidx], np_[pidx - 1]
                                                _commit_unified(np_)
                                                st.rerun()
                                        with c_dn:
                                            if st.button(
                                                "↓", key=f"u_dn_{ds_key}_{step_inst}",
                                                help="Move this step down",
                                                disabled=(pidx >= len(u_plan) - 1),
                                                use_container_width=True,
                                            ) and pidx < len(u_plan) - 1:
                                                np_ = list(u_plan)
                                                np_[pidx + 1], np_[pidx] = np_[pidx], np_[pidx + 1]
                                                _commit_unified(np_)
                                                st.rerun()
                                        with c_chk:
                                            new_enabled = st.checkbox(
                                                "On", value=enabled,
                                                key=f"u_toggle_{ds_key}_{step_inst}",
                                                help="Toggle this step on/off (pass through when off)",
                                                label_visibility="collapsed",
                                            )
                                            if new_enabled != enabled:
                                                np_ = list(u_plan)
                                                np_[pidx] = {**np_[pidx], "enabled": new_enabled}
                                                _commit_unified(np_)
                                                st.rerun()
                                        with c_rm:
                                            if st.button(
                                                "✕", key=f"u_rm_{ds_key}_{step_inst}",
                                                help="Remove this step from the plan",
                                                use_container_width=True,
                                            ):
                                                np_ = [e for j, e in enumerate(u_plan) if j != pidx]
                                                _commit_unified(np_)
                                                st.rerun()
                                with row_btn:
                                    if not is_active:
                                        if st.button("Go to", key=f"goto_step_{i}_{sig}",
                                                     use_container_width=True):
                                            sh.go_to(i)
                                            _persist_step_history()
                                            st.rerun()
                                # Per-substep parameter controls.
                                # Transforms (Add Column from Examples,
                                # Merge, Split, Replace, Conditional, Group
                                # By) get the same structural form they
                                # were inserted with so users can tweak
                                # find/replace targets, separators, rules,
                                # etc. without removing and re-inserting
                                # the step. Cleaning substeps with declared
                                # threshold params get the legacy numeric
                                # editor below.
                                is_transform_step = (
                                    kind == "cleaning_substep"
                                    and SUBSTEP_REGISTRY.get(substep_key, {}).get("transform")
                                )
                                if (is_transform_step and step_inst is not None
                                        and pidx is not None):
                                    plan_entry = u_plan[pidx]
                                    current_params = dict(plan_entry.get("params") or {})
                                    with st.expander("Parameters", expanded=False):
                                        if not enabled:
                                            st.caption("This transform is disabled — "
                                                       "re-enable it to apply parameter changes.")
                                        # Edits apply against the dataframe
                                        # going INTO this step (the previous
                                        # step's output) so the preview shows
                                        # what the transform will do once
                                        # re-run with the new params.
                                        in_df = (sh.steps[i - 1].df if i > 0
                                                 else step.df)
                                        new_params = _render_transform_form(
                                            substep_key, current_params, in_df,
                                            key_prefix=f"trf_edit_{ds_key}_{step_inst}",
                                        )
                                        _render_transform_preview(
                                            substep_key, new_params, in_df,
                                            new_columns=_transform_added_columns(
                                                substep_key, new_params,
                                            ),
                                        )
                                        save_col, _ = st.columns([1, 3])
                                        with save_col:
                                            if st.button(
                                                "Save changes",
                                                key=f"trf_save_{ds_key}_{step_inst}",
                                                use_container_width=True,
                                                type="primary",
                                            ):
                                                ok, msg = _validate_transform_params(
                                                    substep_key, new_params,
                                                )
                                                if not ok:
                                                    st.warning(msg)
                                                else:
                                                    np_ = list(u_plan)
                                                    np_[pidx] = {
                                                        **np_[pidx],
                                                        "params": new_params,
                                                        "name": substep_label(
                                                            substep_key, new_params,
                                                        ),
                                                    }
                                                    _commit_unified(np_)
                                                    st.rerun()
                                if (kind == "cleaning_substep" and step_inst is not None
                                        and pidx is not None
                                        and SUBSTEP_PARAM_SCHEMA.get(substep_key)):
                                    schema_entries = SUBSTEP_PARAM_SCHEMA[substep_key]
                                    plan_entry = u_plan[pidx]
                                    current_params = dict(plan_entry.get("params") or {})
                                    for entry in schema_entries:
                                        current_params.setdefault(entry["key"], entry["default"])
                                    with st.expander("Parameters", expanded=False):
                                        if not enabled:
                                            st.caption("This substep is disabled — "
                                                       "re-enable it to apply parameter changes.")
                                        new_params = dict(current_params)
                                        for entry in schema_entries:
                                            new_params[entry["key"]] = st.number_input(
                                                entry["label"],
                                                min_value=float(entry["min"]),
                                                max_value=float(entry["max"]),
                                                value=float(current_params[entry["key"]]),
                                                step=float(entry["step"]),
                                                help=entry.get("help"),
                                                key=f"substep_param_{ds_key}_{step_inst}_{entry['key']}",
                                                disabled=not enabled,
                                            )
                                        if (enabled and any(
                                            float(new_params[e["key"]]) != float(current_params[e["key"]])
                                            for e in schema_entries
                                        )):
                                            np_ = list(u_plan)
                                            np_[pidx] = {
                                                **np_[pidx],
                                                "params": {
                                                    **(np_[pidx].get("params") or {}),
                                                    **new_params,
                                                },
                                            }
                                            _commit_unified(np_)
                                            st.rerun()
                        # Aliases used by the existing Insert UI below.
                        plan = _get_cleaning_plan(ds_key)

                        def _commit_plan(new_plan):
                            # Map cleaning-only mutations onto the unified plan
                            # while preserving the position of every
                            # non-cleaning step (Promoted Headers, Changed
                            # Type, manual overrides). The whole cleaning
                            # block is rewritten in-place at the slot of
                            # the first existing cleaning step; if there
                            # was none, the new cleaning entries land at
                            # the end of the unified plan.
                            u_now = _build_unified_plan(sh)
                            new_cleaning_entries = []
                            for entry in new_plan:
                                existing = next((e for e in u_now
                                                 if e["instance_id"] == entry["instance_id"]), None)
                                if existing:
                                    new_cleaning_entries.append({
                                        **existing,
                                        "enabled": entry["enabled"],
                                        "params": dict(entry.get("params") or {}),
                                    })
                                else:
                                    new_cleaning_entries.append({
                                        "instance_id": entry["instance_id"],
                                        "kind": "cleaning_substep",
                                        "name": substep_label(entry["key"], entry.get("params") or {}),
                                        "summary": "",
                                        "enabled": bool(entry.get("enabled", True)),
                                        "params": dict(entry.get("params") or {}),
                                        "meta_extra": {"substep_key": entry["key"]},
                                    })
                            merged = []
                            inserted = False
                            for e in u_now:
                                if e["kind"] == "cleaning_substep":
                                    if not inserted:
                                        merged.extend(new_cleaning_entries)
                                        inserted = True
                                    # drop original cleaning entries — the new
                                    # block has already been spliced in
                                else:
                                    merged.append(e)
                            if not inserted:
                                merged.extend(new_cleaning_entries)
                            _commit_unified_plan(sh, merged, ds_key)

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

                        # ── Insert step affordance ──
                        with st.expander("➕ Insert step", expanded=False):
                            st.caption("Add a new cleaning substep at any position. "
                                       "The chain is rebuilt from the first cleaning substep onward.")
                            insertable = [(k, meta["label"]) for k, meta in SUBSTEP_REGISTRY.items()
                                          if meta.get("insertable")]
                            ins_col1, ins_col2 = st.columns([2, 1])
                            with ins_col1:
                                ins_choice = st.selectbox(
                                    "Substep",
                                    options=[k for k, _ in insertable],
                                    format_func=lambda k: SUBSTEP_REGISTRY[k]["label"],
                                    key=f"ins_choice_{ds_key}",
                                )
                            with ins_col2:
                                # Position: 1 = beginning, len(plan)+1 = end.
                                pos_options = list(range(1, len(plan) + 2))
                                pos_default = len(plan)  # before last (end)
                                ins_pos = st.selectbox(
                                    "Insert at position",
                                    options=pos_options,
                                    index=len(pos_options) - 1,
                                    format_func=lambda p: (
                                        f"{p} · before `{plan[p-1]['key']}`"
                                        if p <= len(plan) else f"{p} · at end"
                                    ),
                                    key=f"ins_pos_{ds_key}",
                                )
                            # Render param inputs for the chosen substep.
                            param_specs = SUBSTEP_REGISTRY[ins_choice].get("params", [])
                            param_values = {}
                            if param_specs:
                                cur_cols = list(view_df.columns)
                                pcols = st.columns(max(1, len(param_specs)))
                                for j, spec in enumerate(param_specs):
                                    with pcols[j]:
                                        if spec["kind"] == "column":
                                            if cur_cols:
                                                param_values[spec["name"]] = st.selectbox(
                                                    spec["label"], cur_cols,
                                                    key=f"ins_p_{ds_key}_{ins_choice}_{spec['name']}",
                                                )
                                            else:
                                                st.info("No columns available")
                                        else:
                                            param_values[spec["name"]] = st.text_input(
                                                spec["label"],
                                                key=f"ins_p_{ds_key}_{ins_choice}_{spec['name']}",
                                            )
                            if st.button("Insert substep", key=f"ins_apply_{ds_key}",
                                         type="primary"):
                                # Validate required params.
                                missing = [s["label"] for s in param_specs
                                           if not str(param_values.get(s["name"], "")).strip()]
                                if missing:
                                    st.warning(f"Please provide: {', '.join(missing)}")
                                else:
                                    new_entry = {
                                        "instance_id": _new_instance_id(),
                                        "key": ins_choice,
                                        "enabled": True,
                                        "params": param_values,
                                    }
                                    new_plan = list(plan)
                                    insert_at = ins_pos - 1
                                    new_plan.insert(insert_at, new_entry)
                                    _commit_plan(new_plan)
                                    st.success(f"Inserted `{SUBSTEP_REGISTRY[ins_choice]['label']}` "
                                               f"at position {ins_pos}")
                                    st.rerun()

                        # ── Transform Toolkit ──
                        # Power Query-style column-shaping transforms. Each
                        # one registers as its own substep so reorder /
                        # toggle / remove / Parameters all reuse the same
                        # universal Applied Steps editor.
                        with st.expander("⚙️ Transform", expanded=False):
                            st.caption(
                                "Add Power Query-style column transforms — Add Column "
                                "from Examples, Merge / Split / Replace / Conditional / "
                                "Group By. Each one becomes its own step in Applied "
                                "Steps and can be toggled, reordered, or removed."
                            )
                            _render_questions_panel(ds_key, sh, view_df,
                                                    location="transform")
                            transform_keys = [
                                k for k, m in SUBSTEP_REGISTRY.items()
                                if m.get("transform")
                            ]
                            t_col1, t_col2 = st.columns([2, 1])
                            with t_col1:
                                t_choice = st.selectbox(
                                    "Transform",
                                    options=transform_keys,
                                    format_func=lambda k: SUBSTEP_REGISTRY[k]["label"],
                                    key=f"trf_choice_{ds_key}",
                                )
                            with t_col2:
                                t_pos_options = list(range(1, len(plan) + 2))
                                t_pos = st.selectbox(
                                    "Insert at position",
                                    options=t_pos_options,
                                    index=len(t_pos_options) - 1,
                                    format_func=lambda p: (
                                        f"{p} · before `{plan[p-1]['key']}`"
                                        if p <= len(plan) else f"{p} · at end"
                                    ),
                                    key=f"trf_pos_{ds_key}",
                                )
                            t_params = _render_transform_form(
                                t_choice, {}, view_df,
                                key_prefix=f"trf_{ds_key}_{t_choice}",
                            )
                            _render_transform_preview(
                                t_choice, t_params, view_df,
                                new_columns=_transform_added_columns(t_choice, t_params),
                            )
                            if st.button(
                                "Apply transform",
                                key=f"trf_apply_{ds_key}_{t_choice}",
                                type="primary",
                            ):
                                ok, msg = _validate_transform_params(t_choice, t_params)
                                if not ok:
                                    st.warning(msg)
                                else:
                                    new_entry = {
                                        "instance_id": _new_instance_id(),
                                        "key": t_choice,
                                        "enabled": True,
                                        "params": t_params,
                                    }
                                    new_plan = list(plan)
                                    new_plan.insert(t_pos - 1, new_entry)
                                    _commit_plan(new_plan)
                                    # Drop the cached inferred op so the next
                                    # Add-Column-from-Examples insert starts
                                    # fresh instead of reusing stale state.
                                    st.session_state.pop(
                                        f"trf_{ds_key}_{t_choice}_inferred", None,
                                    )
                                    st.success(
                                        f"Inserted `{SUBSTEP_REGISTRY[t_choice]['label']}` "
                                        f"at position {t_pos}"
                                    )
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

                    # ── Display preferences ──
                    with st.expander("Display preferences", expanded=False):
                        st.caption(
                            "Choose how dates, numbers, and currency values are "
                            "displayed in preview tables. Preferences apply to the "
                            "Overview preview, Column Types samples, and the "
                            "Statistics descriptive table for this dataset."
                        )
                        prefs = _get_display_prefs()
                        date_keys = list(DATE_FORMAT_PRESETS.keys())
                        num_keys = list(NUMBER_FORMAT_PRESETS.keys())
                        curr_keys = list(CURRENCY_FORMAT_PRESETS.keys())
                        pc1, pc2, pc3 = st.columns(3)
                        with pc1:
                            new_date = st.selectbox(
                                "Date format", date_keys,
                                index=date_keys.index(prefs.get("date_format",
                                    DEFAULT_DISPLAY_PREFS["date_format"]))
                                if prefs.get("date_format") in date_keys else 0,
                                key=f"pref_date_{_ds_key()}",
                            )
                        with pc2:
                            new_num = st.selectbox(
                                "Number format", num_keys,
                                index=num_keys.index(prefs.get("number_format",
                                    DEFAULT_DISPLAY_PREFS["number_format"]))
                                if prefs.get("number_format") in num_keys else 0,
                                key=f"pref_num_{_ds_key()}",
                            )
                        with pc3:
                            new_curr = st.selectbox(
                                "Currency format", curr_keys,
                                index=curr_keys.index(prefs.get("currency_format",
                                    DEFAULT_DISPLAY_PREFS["currency_format"]))
                                if prefs.get("currency_format") in curr_keys else 0,
                                key=f"pref_curr_{_ds_key()}",
                            )
                        prefs["date_format"] = new_date
                        prefs["number_format"] = new_num
                        prefs["currency_format"] = new_curr

                    active_prefs = _get_display_prefs()

                    st.subheader("Data Preview")
                    st.dataframe(
                        view_df.head(10),
                        use_container_width=True,
                        column_config=_column_config_from_schema(
                            schema_for_format, view_df, prefs=active_prefs),
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

                    _render_phase1_dock("cleaning", limits)

                    view_df = _active_df()
                    sig = _active_step_signature()
                    _render_questions_panel(_ds_key(), _get_step_history(),
                                            view_df, location="cleaning")
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
            
                elif active_tab == _TAB_LABELS[3]:
                    _section_head("Statistical Analysis", "Descriptive statistics, correlations, and outlier signals.", "04 — Statistics")

                    _render_phase1_dock("stats", limits)

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
                        stats_fmts = _resolve_display_prefs(_get_display_prefs())
                        for c in stats_display.columns:
                            if c == "column":
                                continue
                            try:
                                if c in int_like:
                                    stats_cfg[c] = st.column_config.NumberColumn(format=stats_fmts["int"])
                                elif c == "missing_pct":
                                    stats_cfg[c] = st.column_config.NumberColumn(format="%.2f%%")
                                else:
                                    stats_cfg[c] = st.column_config.NumberColumn(format=stats_fmts["dec"])
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
            
                elif active_tab == _TAB_LABELS[4]:
                    _section_head("Visualizations", "Distributions, relationships, and custom charts.", "05 — Visualizations")
                
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
            
                elif active_tab == _TAB_LABELS[5]:
                    _section_head("Predictions & Comparisons", "Forecast a target column and compare against historical periods.", "06 — Predictions")
                
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
            
                elif active_tab == _TAB_LABELS[6]:
                    _section_head("ML & Clustering", "Categorical analysis, ML models, clusters, and outliers.", "07 — Machine Learning")

                    _render_phase1_dock("ml", limits)

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
            
                elif active_tab == _TAB_LABELS[2]:
                    _render_model_section(uid, run_analysis_cb=run_analysis, limits=limits)

                elif active_tab == _TAB_LABELS[7]:
                    _section_head("AI Assistant", "Ask questions about your data in natural language.", "08 — AI Chat")
                
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
                            
                                # `chat_history.dataset_id` is an Integer column, but
                                # virtual joined-view datasets carry a synthetic
                                # string id (`joined_<ts>`). Skip persistence in
                                # that case so the chat tab never raises on a
                                # type-mismatched insert.
                                _cur_id = st.session_state.current_dataset_id
                                if isinstance(_cur_id, int):
                                    db = get_db()
                                    try:
                                        save_chat_message(db, _cur_id, prompt, response)
                                    finally:
                                        db.close()
                        
                            st.rerun()
            
                elif active_tab == _TAB_LABELS[8]:
                    _section_head("Comprehensive Report", "Executive summary, AI insights, and downloadable artefacts.", "09 — Report")
                
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


def show_help_page():
    logo_b64 = get_logo_base64()

    _render_auth_chrome(
        logo_b64,
        action_label="Dashboard" if st.session_state.user else "Sign In",
        action_href="/" if st.session_state.user else "?signin=1",
    )

    st.markdown(
        '<h1 class="glow-text" style="font-size:2.75rem;margin-top:1rem;">Help Center</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="sub-title">Everything you need to get the most out of DataVision Pro &mdash; '
        'from your first upload to advanced cleaning and AI insights.</p>',
        unsafe_allow_html=True,
    )

    st.markdown("### Jump to a topic")
    topic_cols = st.columns(4)
    topics = [
        ("Getting Started", "#getting-started"),
        ("Uploading Data", "#uploading-data"),
        ("Cleaning Recipe", "#cleaning-recipe"),
        ("Analytics Report", "#analytics-report"),
        ("AI Assistant", "#ai-assistant"),
        ("Account & Billing", "#account-billing"),
        ("Report an Issue", "#report-issue"),
        ("FAQ", "#faq"),
    ]
    for i, (label, anchor) in enumerate(topics):
        with topic_cols[i % 4]:
            st.markdown(f"- [{label}]({anchor})")

    st.divider()

    # ── Getting Started ─────────────────────────────────────────────────────
    st.markdown('<a id="getting-started"></a>', unsafe_allow_html=True)
    st.header("Getting Started")
    st.markdown(
        "DataVision Pro turns spreadsheets and CSVs into clean datasets, "
        "descriptive statistics, charts, and AI-powered insights — without writing code."
    )
    st.markdown(
        "**Five-minute walkthrough:**\n"
        "1. **Create an account** from the Sign In page (free 60-day trial, no credit card required).\n"
        "2. **Open the Dashboard** — this is your home base for uploading data and reviewing results.\n"
        "3. **Upload a file** (CSV or Excel). The platform will auto-detect encoding, delimiter, and header row.\n"
        "4. **Run the cleaning recipe** to remove duplicates, fix types, normalise text, and handle missing values.\n"
        "5. **Read the analytics report** for descriptive statistics, distributions, correlations, and visualisations.\n"
        "6. **Ask the AI assistant** any question about the dataset in plain English."
    )

    st.divider()

    # ── Uploading Data ──────────────────────────────────────────────────────
    st.markdown('<a id="uploading-data"></a>', unsafe_allow_html=True)
    st.header("Uploading Data")
    st.markdown(
        "**Supported formats:** `.csv`, `.xlsx`, `.xls`.\n\n"
        "**What happens on upload:**\n"
        "- Encoding (UTF-8, Latin-1, Windows-1252, …) is auto-detected so accented characters render correctly.\n"
        "- The CSV delimiter (comma, semicolon, tab, pipe) is sniffed from the first lines.\n"
        "- Header detection decides whether the first row contains column names.\n"
        "- If anything looks ambiguous, you can override the delimiter, header, and encoding before parsing.\n\n"
        "**Tips for clean uploads:**\n"
        "- Keep one table per sheet — extra summary rows or merged headers can confuse parsing.\n"
        "- Remove totals/subtotals at the bottom of the file before uploading.\n"
        "- For very wide spreadsheets, only upload the columns you actually need to analyse.\n"
        "- Files are stored privately to your account; you can save snapshots and reload them later."
    )

    st.divider()

    # ── Cleaning Recipe ─────────────────────────────────────────────────────
    st.markdown('<a id="cleaning-recipe"></a>', unsafe_allow_html=True)
    st.header("Cleaning Recipe")
    st.markdown(
        "The cleaning recipe is a sequence of steps the platform applies to your raw data. "
        "Every step is transparent and reversible — you can review, reorder, or remove any of them."
    )
    st.markdown(
        "**Steps you'll typically see:**\n"
        "- **Remove duplicate rows** — exact duplicates are dropped.\n"
        "- **Fix column types** — numbers, dates, booleans, and currencies are inferred from values.\n"
        "- **Normalise text** — trim whitespace, collapse double spaces, standardise casing.\n"
        "- **Handle missing values** — choose between leaving blanks, filling with a default, or dropping rows.\n"
        "- **Detect currencies** — values like `$1,200.50` or `€ 12,30` are parsed into numeric amounts with a currency code.\n"
        "- **Parse dates** — common formats are recognised; ambiguous ones are flagged for review.\n\n"
        "**Reviewing the recipe:** every tab in the dashboard has a *Review* panel that shows what was applied "
        "and lets you tweak settings before the report regenerates."
    )

    st.divider()

    # ── Reading the Analytics Report ────────────────────────────────────────
    st.markdown('<a id="analytics-report"></a>', unsafe_allow_html=True)
    st.header("Reading the Analytics Report")
    st.markdown(
        "Once cleaning is done, the report is split into focused sections:"
    )
    st.markdown(
        "- **Overview** — row/column counts, data types, missingness, and data quality flags.\n"
        "- **Descriptive statistics** — for numeric columns: count, mean, median, standard deviation, min/max, "
        "and quartiles. For text columns: unique values, top categories, and frequency.\n"
        "- **Distributions** — histograms for numeric data and bar charts for categorical data.\n"
        "- **Correlations** — a heatmap that shows which numeric columns move together.\n"
        "- **Trends over time** — when a date column is detected, key metrics are charted by day, week, or month.\n"
        "- **Insights** — short, plain-English notes calling out anomalies, outliers, and notable patterns.\n\n"
        "Charts and tables can be exported, and you can download the cleaned dataset as CSV or Excel."
    )

    st.divider()

    # ── AI Assistant ────────────────────────────────────────────────────────
    st.markdown('<a id="ai-assistant"></a>', unsafe_allow_html=True)
    st.header("AI Assistant")
    st.markdown(
        "The AI assistant lets you ask questions about your dataset in natural language. "
        "It has full context of your cleaned data, column types, and summary statistics."
    )
    st.markdown(
        "**Example questions:**\n"
        "- *Which product category had the highest average revenue last quarter?*\n"
        "- *Are there any unusual spikes in returns this month?*\n"
        "- *Compare conversion rates between regions A and B.*\n"
        "- *Suggest three follow-up analyses I should run.*\n\n"
        "**Best practices:**\n"
        "- Be specific about the column or metric you mean.\n"
        "- Ask one question at a time for the clearest answer.\n"
        "- The assistant will tell you when it's uncertain — treat those moments as a cue to clarify your question or check the data."
    )

    st.divider()

    # ── Account & Billing ───────────────────────────────────────────────────
    st.markdown('<a id="account-billing"></a>', unsafe_allow_html=True)
    st.header("Account & Billing Basics")
    st.markdown(
        "**Your account:**\n"
        "- Sign up with email and password — passwords are hashed with bcrypt and stored securely.\n"
        "- Forgot your password? Use the *Forgot Password* link on the Sign In page to receive a reset email.\n"
        "- You can update your email and password from the dashboard settings.\n\n"
        "**Plans & trial:**\n"
        "- New accounts start with a 60-day free trial — no credit card required.\n"
        "- Plan tiers and limits are shown on the Pricing page (use the *View Pricing* button at the bottom of this page).\n"
        "- Saved datasets, cleaning recipes, and reports remain available for the lifetime of your account.\n\n"
        "**Privacy & data:**\n"
        "- Your data is private to your account and is never used to train shared models.\n"
        "- You can delete saved datasets at any time from the dashboard."
    )

    st.divider()

    # ── Report an Issue ─────────────────────────────────────────────────────
    st.markdown('<a id="report-issue"></a>', unsafe_allow_html=True)
    st.header("Report an Issue")
    st.markdown(
        "Found a bug, hit an error, or have a feature request? Send us a note and we'll get back within 24 hours."
    )
    st.markdown(
        "**When reporting an issue, please include:**\n"
        "- What you were trying to do (e.g. *upload a CSV with semicolons as delimiters*).\n"
        "- What happened instead (the error message, or what looked wrong).\n"
        "- The size and format of the file if it's data-related (rows × columns, CSV vs Excel).\n"
        "- Browser and device, if it's a display or layout issue."
    )

    show_support_section()

    st.divider()

    # ── FAQ ─────────────────────────────────────────────────────────────────
    st.markdown('<a id="faq"></a>', unsafe_allow_html=True)
    st.header("FAQ")
    with st.expander("Is my data private?"):
        st.write(
            "Yes. Datasets you upload are stored privately to your account, never shared with other users, "
            "and never used to train shared AI models."
        )
    with st.expander("What file size and format limits apply?"):
        st.write(
            "CSV and Excel files are supported. Very large files may take longer to clean and analyse — "
            "if you hit a limit, the dashboard will let you know and suggest a smaller upload."
        )
    with st.expander("Can I save and reload datasets?"):
        st.write(
            "Yes. Cleaned datasets can be saved from the dashboard and reopened later from your saved datasets list."
        )
    with st.expander("How accurate are the AI insights?"):
        st.write(
            "The AI assistant uses your actual cleaned data, summary statistics, and column metadata to ground its "
            "answers, but it can still make mistakes. Always double-check important conclusions against the underlying tables and charts."
        )
    with st.expander("How do I cancel or change my plan?"):
        st.write(
            "Plan changes can be requested through the support form above. Your data stays intact across plan changes."
        )

    st.divider()

    nav_cols = st.columns([1, 1, 1])
    with nav_cols[0]:
        if st.button("← Back to Home", use_container_width=True, key="help_back_home"):
            st.session_state.page = 'home'
            st.rerun()
    with nav_cols[1]:
        if st.session_state.user:
            if st.button("Open Dashboard", use_container_width=True, key="help_open_dashboard"):
                st.session_state.page = 'dashboard'
                st.rerun()
        else:
            if st.button("Sign In", use_container_width=True, key="help_sign_in"):
                st.session_state.page = 'login'
                st.rerun()
    with nav_cols[2]:
        if st.button("View Pricing", use_container_width=True, key="help_pricing"):
            st.session_state.page = 'pricing'
            st.rerun()


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
<li><a href="/" target="_self">Home</a></li>
<li><a href="/#features" target="_self">Features</a></li>
<li><a href="/#how" target="_self">How It Works</a></li>
<li><a href="/#pricing" target="_self">Pricing &amp; Plans</a></li>
</ul>
</div>
<div>
<div class="lp-footer-col-title">Support</div>
<ul class="lp-footer-links-list">
<li><a href="?help=1" target="_self">Help Center</a></li>
<li><a href="?help=1" target="_self">Documentation</a></li>
<li><a href="/#contact" target="_self">Contact Us</a></li>
<li><a href="mailto:muayad.demaidi.work@gmail.com">Email Support</a></li>
<li><a href="?help=1#report-issue" target="_self">Report an Issue</a></li>
</ul>
</div>
<div>
<div class="lp-footer-col-title">Learn</div>
<ul class="lp-footer-links-list">
<li><a href="https://datavisionpro.app/glossary/" target="_blank" rel="noopener">Data Glossary</a></li>
<li><a href="https://datavisionpro.app/guides/" target="_blank" rel="noopener">How-to Guides</a></li>
<li><a href="https://datavisionpro.app/compare/" target="_blank" rel="noopener">Compare</a></li>
<li><a href="https://datavisionpro.app/about/" target="_blank" rel="noopener">About</a></li>
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

def show_public_review_page():
    """Token-gated, login-free draft review page for non-admin reviewers
    (e.g. operator approving from a phone via the link in the weekly email).

    URL: ``/?review_token=<AgentConfig.admin_review_token>``
    """
    import json as _json
    import hmac as _hmac
    from seo_agent.config import load_config
    from seo_agent.db import init_agent_db
    from seo_agent.review import (
        list_drafts, get_draft_payload, approve_draft, reject_draft,
    )

    supplied = (st.query_params.get('review_token') or '').strip()
    cfg = load_config()
    legacy = (cfg.admin_review_token or '').strip()
    named_tokens = list(cfg.admin_review_tokens or [])

    st.markdown(
        '<h2 style="margin-bottom:0.25rem;">Draft review</h2>'
        '<p style="color:#94a3b8;margin-top:0;">Approve or reject pending '
        'SEO/GEO drafts from anywhere — no admin login required.</p>',
        unsafe_allow_html=True,
    )

    if not legacy and not named_tokens:
        st.error(
            "Public review is not enabled. Add a review token in the agent "
            "configuration first."
        )
        return

    # Match the supplied token against named tokens (preferred — gives us
    # an attributable reviewer label) and finally the legacy single token.
    reviewer_name = None
    if supplied:
        for entry in named_tokens:
            entry_token = (entry.get("token") or "").strip()
            entry_name = (entry.get("name") or "").strip()
            if entry_token and _hmac.compare_digest(supplied, entry_token):
                reviewer_name = entry_name or "public-review-link"
                break
        if reviewer_name is None and legacy and _hmac.compare_digest(supplied, legacy):
            reviewer_name = "public-review-link"

    if not reviewer_name:
        st.error("Invalid or missing review token.")
        return
    st.caption(f"Signed in via public link as: **{reviewer_name}**")

    init_agent_db()
    drafts = list_drafts("pending")
    st.caption(f"{len(drafts)} draft(s) awaiting review.")

    if not drafts:
        st.info("Nothing to review right now. Check back after the next agent run.")
        return

    for d in drafts:
        with st.expander(f"[{d.kind}] {d.title}", expanded=False):
            st.caption(
                f"slug: `{d.slug}` · {'Refresh' if d.is_refresh else 'New'} · "
                f"created {d.created_at.strftime('%Y-%m-%d %H:%M')}"
            )
            if d.target_query:
                st.markdown(f"**Target query:** {d.target_query}")
            if d.info_gain:
                st.markdown(f"**Information-gain note:** {d.info_gain}")

            payload = get_draft_payload(d.id) or {}
            inner = payload.get("payload", payload)

            edit_mode = st.checkbox("✏️ Edit JSON before approving",
                                    key=f"pub_edit_{d.id}")
            edited_text = None
            if edit_mode:
                edited_text = st.text_area(
                    "Draft JSON",
                    value=_json.dumps(inner, indent=2, ensure_ascii=False),
                    height=320, key=f"pub_edit_text_{d.id}",
                )
            else:
                with st.expander("Show full draft JSON"):
                    st.json(inner)

            # Stack buttons full-width so they're easy to tap on a phone.
            if st.button("✅ Approve & publish", key=f"pub_appr_{d.id}",
                         type="primary", use_container_width=True):
                edited_payload = None
                if edit_mode and edited_text:
                    try:
                        edited_payload = _json.loads(edited_text)
                    except Exception as ex:
                        st.error(f"Edit JSON invalid: {ex}")
                        st.stop()
                res = approve_draft(
                    d.id,
                    reviewer=reviewer_name,
                    notes=("edited via public link" if edited_payload
                           else "approved via public link"),
                    edited_payload=edited_payload,
                    source="public_link",
                )
                if res.get("ok"):
                    st.success(
                        f"Approved → injected into {res['file']}"
                        + (" · build triggered" if res.get("build_triggered")
                           else " · build skipped")
                    )
                    st.rerun()
                else:
                    st.error(f"Approve failed: {res.get('error')}")
            if st.button("❌ Reject", key=f"pub_rej_{d.id}",
                         use_container_width=True):
                if reject_draft(d.id, reviewer=reviewer_name,
                                notes="rejected via public link",
                                source="public_link"):
                    st.warning("Rejected and archived.")
                    st.rerun()


if st.session_state.page == 'home':
    show_home_page()
elif st.session_state.page == 'login':
    show_login_page()
elif st.session_state.page == 'register':
    show_register_page()
elif st.session_state.page == 'forgot_password':
    show_forgot_password_page()
elif st.session_state.page == 'reset_password':
    show_reset_password_page()
elif st.session_state.page == 'pricing':
    show_pricing_page()
elif st.session_state.page == 'review':
    show_public_review_page()
elif st.session_state.page == 'help':
    show_help_page()
elif st.session_state.page == 'admin':
    if st.session_state.user and st.session_state.user.get('is_admin'):
        show_admin_panel()
    else:
        st.error("Access denied. Admin privileges required.")
        st.session_state.page = 'dashboard'
        st.rerun()
elif st.session_state.page == 'projects':
    if st.session_state.user:
        show_projects_page()
    else:
        st.session_state.page = 'login'
        st.rerun()
elif st.session_state.page == 'dashboard':
    show_dashboard()
else:
    show_home_page()
