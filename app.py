import streamlit as st
import pandas as pd
import numpy as np
import hashlib
from datetime import datetime
import io
import base64

from models import (
    init_db, get_db, save_dataset_record, find_similar_datasets, 
    get_datasets_by_name, save_chat_message, get_chat_history,
    create_user, authenticate_user, get_user_by_id, get_all_users,
    get_all_datasets, get_admin_stats, increment_analysis_count, User,
    update_user_subscription, save_support_message, check_trial_active
)
from data_cleaner import clean_data, detect_column_types, get_data_quality_score
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
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600;700;800&display=swap');

:root {
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

* {
    font-family: 'Inter', sans-serif;
}

.stApp {
    background: linear-gradient(135deg, #020617 0%, #0f172a 50%, #020617 100%);
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
    font-size: 3rem;
    font-weight: 700;
    text-align: center;
    font-family: 'Inter', sans-serif;
    background: linear-gradient(135deg, #14b8a6, #0d9488, #94a3b8);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin-bottom: 0.5rem;
    letter-spacing: -0.02em;
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

/* ===== LANDING PAGE — ENTRANCE ANIMATIONS (viewport-triggered) ===== */
.lp-hero, .lp-trust, .lp-features, .lp-hiw, .lp-tiers {
    opacity: 0;
    transform: translateY(28px);
    transition: opacity 0.38s ease-out, transform 0.38s ease-out;
}
.lp-hero.lp-visible,
.lp-trust.lp-visible,
.lp-features.lp-visible,
.lp-hiw.lp-visible,
.lp-tiers.lp-visible {
    opacity: 1 !important;
    transform: translateY(0) !important;
}
@media (prefers-reduced-motion: reduce) {
    .lp-hero, .lp-trust, .lp-features, .lp-hiw, .lp-tiers {
        opacity: 1 !important;
        transform: none !important;
        transition: none !important;
    }
}

/* ===== LANDING PAGE — TRUST BAR ===== */
.lp-trust-bar {
    display: flex;
    justify-content: center;
    gap: 1rem;
    flex-wrap: wrap;
    margin: 1.5rem 0 2rem 0;
}
.lp-trust-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: rgba(13, 148, 136, 0.08);
    border: 1px solid rgba(20, 184, 166, 0.22);
    border-radius: 30px;
    padding: 0.5rem 1.25rem;
    font-size: 0.875rem;
    color: #14b8a6;
    font-weight: 600;
    letter-spacing: 0.02em;
    backdrop-filter: blur(8px);
}
.lp-trust-pill svg { flex-shrink: 0; }

/* ===== LANDING PAGE — FEATURE CARDS ===== */
.lp-feature-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin: 0 0 2.5rem 0;
}
@media (max-width: 900px) {
    .lp-feature-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 500px) {
    .lp-feature-grid { grid-template-columns: 1fr; }
}
.lp-feat-card {
    background: rgba(15, 23, 42, 0.80);
    border: 1px solid rgba(20, 184, 166, 0.12);
    border-radius: 18px;
    padding: 1.75rem 1.25rem 1.5rem 1.25rem;
    text-align: center;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    transition: border-color 0.25s ease, transform 0.25s ease, box-shadow 0.25s ease;
    cursor: default;
}
.lp-feat-card:hover {
    border-color: rgba(20, 184, 166, 0.35);
    transform: translateY(-4px);
    box-shadow: 0 12px 36px rgba(0,0,0,0.35);
}
.lp-feat-icon {
    width: 48px;
    height: 48px;
    margin: 0 auto 1rem auto;
    background: rgba(13, 148, 136, 0.12);
    border-radius: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
}
.lp-feat-icon svg { color: #14b8a6; }
.lp-feat-title {
    font-size: 0.95rem;
    font-weight: 700;
    color: #e2e8f0;
    margin-bottom: 0.4rem;
    letter-spacing: 0.01em;
}
.lp-feat-desc {
    font-size: 0.8rem;
    color: #64748b;
    line-height: 1.5;
}

/* ===== LANDING PAGE — HOW IT WORKS ===== */
.lp-hiw-section {
    text-align: center;
    margin: 0 0 3rem 0;
}
.lp-hiw-section h2 {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #e2e8f0 !important;
    margin-bottom: 2rem !important;
}
.lp-steps-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1.25rem;
}
@media (max-width: 700px) {
    .lp-steps-grid { grid-template-columns: 1fr; }
}
.lp-step-card {
    background: rgba(15, 23, 42, 0.75);
    border: 1px solid rgba(20, 184, 166, 0.10);
    border-radius: 18px;
    padding: 2rem 1.5rem;
    backdrop-filter: blur(12px);
    position: relative;
    text-align: center;
}
.lp-step-num {
    width: 40px;
    height: 40px;
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1rem;
    font-weight: 800;
    color: #fff;
    margin: 0 auto 1rem auto;
    font-family: 'JetBrains Mono', monospace;
}
.lp-step-title {
    font-size: 1rem;
    font-weight: 700;
    color: #e2e8f0;
    margin-bottom: 0.5rem;
}
.lp-step-desc {
    font-size: 0.825rem;
    color: #64748b;
    line-height: 1.55;
}

/* ===== LANDING PAGE — TIERS TEASER ===== */
.lp-tiers-section {
    margin: 0 0 3rem 0;
    text-align: center;
}
.lp-tiers-section h2 {
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    color: #e2e8f0 !important;
    margin-bottom: 0.5rem !important;
}
.lp-tiers-sub {
    font-size: 0.9rem;
    color: #64748b;
    margin-bottom: 1.75rem;
}
.lp-tiers-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
}
@media (max-width: 700px) {
    .lp-tiers-grid { grid-template-columns: 1fr; }
}
.lp-tier-card {
    background: rgba(15, 23, 42, 0.80);
    border: 1px solid rgba(20, 184, 166, 0.12);
    border-radius: 18px;
    padding: 1.75rem 1.25rem;
    text-align: center;
    backdrop-filter: blur(12px);
    transition: border-color 0.25s ease, transform 0.25s ease;
}
.lp-tier-card.featured {
    border-color: rgba(20, 184, 166, 0.40);
    box-shadow: 0 0 32px rgba(13, 148, 136, 0.12);
    transform: translateY(-4px);
}
.lp-tier-badge {
    display: inline-block;
    background: linear-gradient(135deg, #14b8a6, #0d9488);
    color: #fff;
    font-size: 0.65rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    padding: 3px 10px;
    border-radius: 20px;
    margin-bottom: 0.75rem;
    text-transform: uppercase;
}
.lp-tier-name {
    font-size: 1.1rem;
    font-weight: 700;
    color: #e2e8f0;
    margin-bottom: 0.4rem;
}
.lp-tier-tagline {
    font-size: 0.78rem;
    color: #64748b;
    margin-bottom: 1rem;
    line-height: 1.4;
}
.lp-tier-features {
    list-style: none;
    padding: 0;
    margin: 0;
    text-align: left;
}
.lp-tier-features li {
    font-size: 0.8rem;
    color: #94a3b8;
    padding: 0.3rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
.lp-tier-features li svg { flex-shrink: 0; color: #14b8a6; }

/* ===== LANDING PAGE — SUPPORT FORM ===== */
.lp-support-section {
    margin: 2rem 0 1rem 0;
}
.lp-support-header {
    text-align: center;
    margin-bottom: 1.5rem;
}
.lp-support-header h2 {
    font-size: 1.5rem !important;
    font-weight: 700 !important;
    color: #e2e8f0 !important;
    margin-bottom: 0.4rem !important;
}
.lp-support-header p {
    font-size: 0.9rem;
    color: #64748b;
}
.lp-support-card {
    background: rgba(15, 23, 42, 0.80);
    border: 1px solid rgba(20, 184, 166, 0.12);
    border-radius: 20px;
    padding: 2rem;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
}

/* ===== LANDING PAGE — CTA BUTTON VARIANTS ===== */
.lp-btn-primary > div > button {
    background: linear-gradient(135deg, #14b8a6, #0d9488) !important;
    font-size: 1rem !important;
    padding: 0.8rem 2rem !important;
    border-radius: 14px !important;
    box-shadow: 0 6px 24px rgba(13, 148, 136, 0.30) !important;
}
.lp-btn-secondary > div > button {
    background: rgba(15, 23, 42, 0.8) !important;
    border: 1px solid rgba(20, 184, 166, 0.25) !important;
    color: #14b8a6 !important;
    font-size: 0.9rem !important;
    box-shadow: none !important;
}
.lp-btn-secondary > div > button:hover {
    background: rgba(13, 148, 136, 0.12) !important;
    border-color: rgba(20, 184, 166, 0.50) !important;
    box-shadow: none !important;
    transform: translateY(-1px) !important;
}
.lp-btn-outline > div > button {
    background: transparent !important;
    border: 1px solid rgba(20, 184, 166, 0.30) !important;
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
    box-shadow: none !important;
    font-weight: 500 !important;
}
.lp-btn-outline > div > button:hover {
    border-color: rgba(20, 184, 166, 0.55) !important;
    color: #14b8a6 !important;
    box-shadow: none !important;
    transform: none !important;
}
</style>

<div class="matrix-bg">
    <div class="matrix-column" style="left: 2%; animation-duration: 12s; animation-delay: 0s;"><span>0</span><span>1</span><span>1</span><span>0</span><span>1</span><span>∑</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 6%; animation-duration: 15s; animation-delay: 2s;"><span>A</span><span>I</span><span>∫</span><span>7</span><span>3</span><span>9</span><span>π</span></div>
    <div class="matrix-column" style="left: 10%; animation-duration: 10s; animation-delay: 4s;"><span>1</span><span>0</span><span>0</span><span>1</span><span>√</span><span>∞</span><span>0</span><span>1</span><span>1</span></div>
    <div class="matrix-column" style="left: 14%; animation-duration: 18s; animation-delay: 1s;"><span>データ</span><span>5</span><span>8</span><span>2</span><span>∑</span></div>
    <div class="matrix-column" style="left: 18%; animation-duration: 14s; animation-delay: 6s;"><span>0</span><span>1</span><span>1</span><span>0</span><span>1</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 22%; animation-duration: 11s; animation-delay: 3s;"><span>π</span><span>4</span><span>2</span><span>0</span><span>∫</span><span>1</span><span>9</span><span>7</span></div>
    <div class="matrix-column" style="left: 26%; animation-duration: 16s; animation-delay: 8s;"><span>分</span><span>析</span><span>3</span><span>1</span><span>4</span><span>∑</span></div>
    <div class="matrix-column" style="left: 30%; animation-duration: 13s; animation-delay: 5s;"><span>1</span><span>0</span><span>1</span><span>1</span><span>0</span><span>0</span><span>1</span><span>0</span></div>
    <div class="matrix-column" style="left: 34%; animation-duration: 17s; animation-delay: 0s;"><span>∞</span><span>6</span><span>2</span><span>8</span><span>3</span><span>√</span><span>1</span></div>
    <div class="matrix-column" style="left: 38%; animation-duration: 12s; animation-delay: 7s;"><span>0</span><span>0</span><span>1</span><span>1</span><span>0</span><span>1</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 42%; animation-duration: 19s; animation-delay: 2s;"><span>A</span><span>I</span><span>π</span><span>∑</span><span>5</span><span>9</span></div>
    <div class="matrix-column" style="left: 46%; animation-duration: 11s; animation-delay: 9s;"><span>1</span><span>1</span><span>0</span><span>1</span><span>0</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 50%; animation-duration: 14s; animation-delay: 4s;"><span>√</span><span>3</span><span>7</span><span>∫</span><span>2</span><span>1</span><span>8</span><span>4</span></div>
    <div class="matrix-column" style="left: 54%; animation-duration: 16s; animation-delay: 1s;"><span>0</span><span>1</span><span>0</span><span>1</span><span>1</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 58%; animation-duration: 13s; animation-delay: 6s;"><span>∞</span><span>π</span><span>9</span><span>4</span><span>6</span><span>∑</span><span>2</span></div>
    <div class="matrix-column" style="left: 62%; animation-duration: 18s; animation-delay: 3s;"><span>1</span><span>0</span><span>1</span><span>0</span><span>0</span><span>1</span><span>1</span><span>0</span></div>
    <div class="matrix-column" style="left: 66%; animation-duration: 10s; animation-delay: 8s;"><span>デ</span><span>ー</span><span>タ</span><span>5</span><span>∫</span><span>7</span></div>
    <div class="matrix-column" style="left: 70%; animation-duration: 15s; animation-delay: 0s;"><span>0</span><span>1</span><span>1</span><span>1</span><span>0</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 74%; animation-duration: 12s; animation-delay: 5s;"><span>√</span><span>8</span><span>3</span><span>1</span><span>∞</span><span>6</span><span>2</span><span>π</span></div>
    <div class="matrix-column" style="left: 78%; animation-duration: 17s; animation-delay: 2s;"><span>1</span><span>0</span><span>0</span><span>1</span><span>1</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 82%; animation-duration: 14s; animation-delay: 7s;"><span>A</span><span>I</span><span>∑</span><span>4</span><span>9</span><span>∫</span><span>3</span></div>
    <div class="matrix-column" style="left: 86%; animation-duration: 11s; animation-delay: 4s;"><span>0</span><span>1</span><span>0</span><span>1</span><span>0</span><span>1</span><span>1</span><span>0</span></div>
    <div class="matrix-column" style="left: 90%; animation-duration: 16s; animation-delay: 1s;"><span>∞</span><span>7</span><span>2</span><span>5</span><span>√</span><span>π</span><span>8</span></div>
    <div class="matrix-column" style="left: 94%; animation-duration: 13s; animation-delay: 6s;"><span>1</span><span>1</span><span>0</span><span>0</span><span>1</span><span>0</span><span>1</span></div>
    <div class="matrix-column" style="left: 98%; animation-duration: 15s; animation-delay: 9s;"><span>∑</span><span>6</span><span>1</span><span>4</span><span>∫</span><span>9</span></div>
</div>
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

if 'user' not in st.session_state:
    st.session_state.user = None
if 'page' not in st.session_state:
    st.session_state.page = 'home'
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


def load_file(uploaded_file):
    """Load CSV or Excel file with multi-encoding support for Arabic and other languages"""
    ENCODINGS = [
        'utf-8',
        'utf-8-sig',
        'cp1256',
        'windows-1256', 
        'iso-8859-6',
        'utf-16',
        'latin-1',
        'cp1252'
    ]
    
    try:
        if uploaded_file.name.endswith('.csv'):
            file_bytes = uploaded_file.read()
            
            df = None
            successful_encoding = None
            last_error = None
            
            for encoding in ENCODINGS:
                try:
                    df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
                    
                    if df.empty or len(df.columns) == 0:
                        continue
                    
                    col_text = ''.join(str(c) for c in df.columns)
                    if '\ufffd' in col_text or '?' * 5 in col_text:
                        continue
                    
                    successful_encoding = encoding
                    break
                except (UnicodeDecodeError, UnicodeError) as e:
                    last_error = e
                    continue
                except Exception as e:
                    last_error = e
                    continue
            
            if df is None or df.empty:
                st.error(f"Could not read file with any supported encoding. The file may be corrupted or use an unsupported format.")
                return None
            
            return df
            
        elif uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
            return df
        else:
            st.error("Unsupported file type. Please upload a CSV or Excel file.")
            return None
            
    except Exception as e:
        st.error(f"Error reading file: {str(e)}")
        return None


def show_login_page():
    # Redirect if already logged in
    if st.session_state.user:
        st.session_state.page = 'dashboard'
        st.rerun()
        return
    
    logo_b64 = get_logo_base64()
    st.markdown(f'''
    <div style="text-align: center; margin-bottom: 1rem;">
        <a href="/" target="_self" class="logo-link" style="display: inline-block;">
            <img src="data:image/png;base64,{logo_b64}" style="max-width: 250px; border-radius: 12px;" alt="DataVision Pro">
        </a>
    </div>
    ''', unsafe_allow_html=True)
    
    st.markdown('<h2 class="glow-text" style="font-size: 2.5rem;">Welcome Back</h2>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Sign in to access your dashboard</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            email = st.text_input("Email or Username", placeholder="Enter your email")
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submit = st.form_submit_button("Sign In", use_container_width=True)
            
            if submit:
                if email and password:
                    db = get_db()
                    try:
                        user = authenticate_user(db, email, password)
                        if user:
                            st.session_state.user = user_to_dict(user)
                            st.session_state.page = 'dashboard'
                        else:
                            st.error("Invalid email or password")
                    finally:
                        db.close()
                else:
                    st.warning("Please fill in all fields")
        
        # Check if login was successful and rerun outside form
        if st.session_state.user and st.session_state.page == 'dashboard':
            st.success("Successfully signed in!")
            st.rerun()
        
        st.markdown("---")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("← Back to Home", use_container_width=True):
                st.session_state.page = 'home'
                st.rerun()
        with col_b:
            if st.button("Create Account →", use_container_width=True):
                st.session_state.page = 'register'
                st.rerun()


def show_register_page():
    if st.session_state.user:
        st.session_state.page = 'dashboard'
        st.rerun()
        return
    
    logo_b64 = get_logo_base64()
    st.markdown(f'''
    <div style="text-align: center; margin-bottom: 1rem;">
        <a href="/" target="_self" class="logo-link" style="display: inline-block;">
            <img src="data:image/png;base64,{logo_b64}" style="max-width: 250px; border-radius: 12px;" alt="DataVision Pro">
        </a>
    </div>
    ''', unsafe_allow_html=True)
    
    st.markdown('<h2 class="glow-text" style="font-size: 2.5rem;">Create Your Account</h2>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Start your 60-day free trial with full access to all features</p>', unsafe_allow_html=True)
    
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
        "Data Science & Analytics",
        "Business & Management",
        "Marketing & Advertising",
        "Engineering & Technical",
        "Finance & Accounting",
        "Healthcare & Medicine",
        "Education & Academia",
        "IT & Software Development",
        "Research & Scientific",
        "Government & Public Sector",
        "Legal & Compliance",
        "Media & Communications",
        "Human Resources",
        "Supply Chain & Logistics",
        "Real Estate",
        "Retail & E-Commerce",
        "Consulting",
        "Non-Profit & NGO",
        "Student",
        "Other"
    ]
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("register_form"):
            st.markdown("##### Personal Information")
            full_name = st.text_input("Full Name *", placeholder="Enter your full name")
            
            r1c1, r1c2 = st.columns(2)
            with r1c1:
                email = st.text_input("Email Address *", placeholder="your@email.com")
            with r1c2:
                phone = st.text_input("Phone Number *", placeholder="+1234567890")
            
            r2c1, r2c2 = st.columns(2)
            with r2c1:
                username = st.text_input("Username *", placeholder="Choose a username")
            with r2c2:
                gender = st.selectbox("Gender *", ["Select Gender", "Male", "Female"])
            
            r3c1, r3c2 = st.columns(2)
            with r3c1:
                country = st.selectbox("Country *", COUNTRIES)
            with r3c2:
                specialty = st.selectbox("Specialty *", SPECIALTIES)
            
            specialty_other_val = ""
            if specialty == "Other":
                specialty_other_val = st.text_input("Please specify your specialty", placeholder="Enter your specialty")
            
            st.markdown("##### Security")
            p1, p2 = st.columns(2)
            with p1:
                password = st.text_input("Password *", type="password", placeholder="Min 6 characters")
            with p2:
                confirm_password = st.text_input("Confirm Password *", type="password", placeholder="Re-enter password")
            
            st.markdown("")
            submit = st.form_submit_button("🚀 Create Account & Start Free Trial", use_container_width=True)
            
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
                            st.session_state.user = user_to_dict(user)
                            st.session_state.page = 'dashboard'
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
        
        st.markdown("---")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("← Back to Home", use_container_width=True):
                st.session_state.page = 'home'
                st.rerun()
        with col_b:
            if st.button("Already have an account? Sign In →", use_container_width=True):
                st.session_state.page = 'login'
                st.rerun()


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
                        📧 Contact us at: muayad.demaidi.work@gmail.com
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
    if sub_type == 'tier3':
        badge_text = "⭐ Tier 3"
        badge_color = "#0d9488"
    elif sub_type == 'tier2':
        badge_text = "📈 Tier 2"
        badge_color = "#0d9488"
    else:
        badge_text = "🔹 Tier 1"
        badge_color = "#475569"

    st.markdown(f'''
    <div style="
        background: rgba(15, 23, 42, 0.9); 
        border: 1px solid rgba(20, 184, 166, 0.2); 
        border-radius: 16px; 
        padding: 1rem 2rem; 
        margin-bottom: 1.5rem;
        backdrop-filter: blur(10px);
    ">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.8rem;">
            <div style="display: flex; align-items: center; gap: 1rem;">
                <img src="data:image/png;base64,{logo_b64}" style="height: 45px; border-radius: 10px;" alt="DataVision Pro">
                <div>
                    <div style="color: #e2e8f0; font-weight: 700; font-size: 1.2rem; letter-spacing: 0.5px;">DataVision Pro</div>
                    <div style="color: #64748b; font-size: 0.75rem;">Intelligent Analytics Platform</div>
                </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.8rem;">
                <div style="text-align: right;">
                    <div style="color: #e2e8f0; font-weight: 500; font-size: 0.95rem;">👤 {user.get('full_name') or user.get('username')}</div>
                    <span style="background: {badge_color}; color: white; padding: 0.15rem 0.6rem; border-radius: 12px; font-size: 0.75rem; font-weight: 600;">{badge_text}</span>
                </div>
            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    if user.get('is_admin'):
        c1, c2, c3, c4 = st.columns(4)
    else:
        c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("🏠 Home", use_container_width=True, key="home_dash"):
            st.session_state.page = 'home'
            st.session_state.df = None
            st.session_state.df_cleaned = None
            st.rerun()
    with c2:
        if st.button("📊 View Tiers", use_container_width=True, key="tiers_dash"):
            st.session_state.page = 'pricing'
            st.rerun()
    if user.get('is_admin'):
        with c3:
            if st.button("⚙️ Admin Panel", use_container_width=True, key="admin_dash"):
                st.session_state.page = 'admin'
                st.rerun()
        with c4:
            if st.button("🚪 Sign Out", use_container_width=True, key="signout_dash"):
                st.session_state.user = None
                st.session_state.page = 'home'
                st.session_state.df = None
                st.session_state.df_cleaned = None
                st.rerun()
    else:
        with c3:
            if st.button("🚪 Sign Out", use_container_width=True, key="signout_dash"):
                st.session_state.user = None
                st.session_state.page = 'home'
                st.session_state.df = None
                st.session_state.df_cleaned = None
                st.rerun()

    st.markdown("<div style='margin-top: 1rem;'></div>", unsafe_allow_html=True)

    def run_analysis(file_obj, ds_name, p_month, p_year, lmts):
        with st.spinner("Loading and analyzing data..."):
            df = load_file(file_obj)
            if df is not None:
                if len(df) > lmts['max_rows']:
                    st.error(f"Row count ({len(df):,}) exceeds the limit ({lmts['max_rows']:,})")
                else:
                    st.session_state.df = df
                    df_cleaned, cleaning_report = clean_data(df)
                    st.session_state.df_cleaned = df_cleaned
                    st.session_state.cleaning_report = cleaning_report
                    analysis_results = generate_summary_report(df_cleaned)
                    st.session_state.analysis_results = analysis_results
                    data_hash = calculate_data_hash(df)
                    columns_info = {col: str(df[col].dtype) for col in df.columns}
                    db = get_db()
                    try:
                        record = save_dataset_record(
                            db, filename=file_obj.name, dataset_name=ds_name,
                            period_month=p_month, period_year=p_year,
                            row_count=len(df), column_count=len(df.columns),
                            columns_info=columns_info, data_hash=data_hash,
                            summary_stats=sanitize_for_json(analysis_results.get('numeric_summary', {}))
                        )
                        st.session_state.current_dataset_id = record.id
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
        st.markdown(f'''
        <div style="text-align: center; margin: 2rem 0 1rem 0;">
            <img src="data:image/png;base64,{logo_b64}" style="max-width: 280px; border-radius: 12px; margin-bottom: 1rem;" alt="DataVision Pro">
            <p style="color: #94a3b8; font-size: 1.15rem; max-width: 500px; margin: 0 auto;">
                Intelligent Data Analytics Platform — Powered by AI
            </p>
        </div>
        ''', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.markdown("""<div class="metric-card"><div class="metric-value">🧹</div><div class="metric-label">Smart Cleaning</div></div>""", unsafe_allow_html=True)
        with col2:
            st.markdown("""<div class="metric-card"><div class="metric-value">📊</div><div class="metric-label">Deep Analytics</div></div>""", unsafe_allow_html=True)
        with col3:
            st.markdown("""<div class="metric-card"><div class="metric-value">🤖</div><div class="metric-label">AI Powered</div></div>""", unsafe_allow_html=True)
        with col4:
            st.markdown("""<div class="metric-card"><div class="metric-value">🔮</div><div class="metric-label">Predictions</div></div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        upload_col1, upload_col2, upload_col3 = st.columns([1, 2, 1])
        with upload_col2:
            st.markdown("""
            <div style="text-align: center; background: rgba(13, 148, 136, 0.08); border: 1px solid rgba(20, 184, 166, 0.2); 
                 border-radius: 16px; padding: 2rem; margin-bottom: 1rem;">
                <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📤</div>
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
                    if st.button("🚀 Start Analysis", type="primary", use_container_width=True):
                        run_analysis(uploaded_file, dataset_name, period_month, period_year, limits)

    if st.session_state.df is not None:
        with st.expander("📤 Upload New Data", expanded=False):
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
                    if st.button("🚀 Start Analysis", type="primary", use_container_width=True, key="new_analyze"):
                        run_analysis(new_file, dataset_name, period_month, period_year, limits)

        tabs = st.tabs([
            "📋 Overview",
            "🧹 Cleaning", 
            "📈 Statistics",
            "📊 Visualizations",
            "🔄 Predictions",
            "🤖 ML & Clusters",
            "💬 AI Chat",
            "📝 Report"
        ])
        
        with tabs[0]:
            st.header("📋 Data Overview")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Rows", f"{len(st.session_state.df):,}")
            with col2:
                st.metric("Total Columns", len(st.session_state.df.columns))
            with col3:
                if st.session_state.df_cleaned is not None:
                    quality = get_data_quality_score(st.session_state.df_cleaned)
                    st.metric("Data Quality", f"{quality['overall_score']}%")
            with col4:
                missing_pct = (st.session_state.df.isnull().sum().sum() / st.session_state.df.size) * 100
                st.metric("Missing Values", f"{missing_pct:.1f}%")
            
            st.subheader("Data Preview")
            st.dataframe(st.session_state.df.head(10), use_container_width=True)
            
            st.subheader("Column Types")
            col_types = detect_column_types(st.session_state.df)
            col_types_df = pd.DataFrame({
                'Column': list(col_types.keys()),
                'Type': list(col_types.values())
            })
            st.dataframe(col_types_df, use_container_width=True)
        
        with tabs[1]:
            st.header("🧹 Data Cleaning")
            
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
                        st.markdown(f'<div class="success-box">✓ {change}</div>', unsafe_allow_html=True)
                else:
                    st.success("Data is clean! No modifications needed.")
                
                st.subheader("Data Quality Score")
                if st.session_state.df_cleaned is not None:
                    quality = get_data_quality_score(st.session_state.df_cleaned)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Completeness", f"{quality['completeness']}%")
                    with col2:
                        st.metric("Uniqueness", f"{quality['uniqueness']}%")
                    with col3:
                        st.metric("Overall Score", f"{quality['overall_score']}%")
                
                missing_chart = create_missing_values_chart(st.session_state.df)
                if missing_chart:
                    st.plotly_chart(missing_chart, use_container_width=True)
        
        with tabs[2]:
            st.header("📈 Statistical Analysis")
            
            df_analysis = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
            
            st.subheader("Descriptive Statistics")
            numeric_stats = get_numeric_stats(df_analysis)
            if not numeric_stats.empty:
                st.dataframe(numeric_stats, use_container_width=True)
            else:
                st.info("No numeric columns found")
            
            st.subheader("Categorical Statistics")
            cat_stats = get_categorical_stats(df_analysis)
            if cat_stats:
                for col, stats in cat_stats.items():
                    with st.expander(f"📁 {col}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**Unique Values:** {stats['unique_count']}")
                            st.write(f"**Most Common:** {stats['most_common']}")
                        with col2:
                            st.write(f"**Least Common:** {stats['least_common']}")
                            st.write(f"**Missing Values:** {stats['missing']}")
            
            st.subheader("Strong Correlations")
            correlations = find_strong_correlations(df_analysis)
            if correlations:
                for corr in correlations[:5]:
                    emoji = "🟢" if corr['correlation'] > 0 else "🔴"
                    st.markdown(f"{emoji} **{corr['column1']}** & **{corr['column2']}**: {corr['correlation']:.3f}")
            else:
                st.info("No strong correlations found")
            
            st.subheader("Outlier Detection")
            outliers = detect_outliers(df_analysis)
            if outliers:
                for col, info in outliers.items():
                    st.markdown(f'<div class="warning-box">⚠️ **{col}**: {info["count"]} outliers detected ({info["percentage"]}%)</div>', unsafe_allow_html=True)
            else:
                st.success("No outliers detected")
        
        with tabs[3]:
            st.header("📊 Visualizations")
            
            df_viz = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
            numeric_cols = df_viz.select_dtypes(include=[np.number]).columns.tolist()
            categorical_cols = df_viz.select_dtypes(include=['object']).columns.tolist()
            
            st.subheader("Distribution Overview")
            dist_overview = create_distribution_overview(df_viz)
            if dist_overview:
                st.plotly_chart(dist_overview, use_container_width=True)
            
            corr_heatmap = create_correlation_heatmap(df_viz)
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
        
        with tabs[4]:
            st.header("🔄 Predictions & Comparisons")
            
            if not limits['predictions_enabled']:
                st.markdown("""
                <div class="neon-card">
                    <h3 style="text-align: center;">📈 Tier 2 Feature</h3>
                    <p style="text-align: center; color: #94a3b8;">
                        Advanced predictions and time-series comparisons are available in Tier 2 and above.
                    </p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("📊 View Tiers", use_container_width=True, key="upgrade_pred"):
                    st.session_state.page = 'pricing'
                    st.rerun()
            else:
                df_pred = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
                numeric_cols = df_pred.select_dtypes(include=[np.number]).columns.tolist()
                
                if st.session_state.similar_datasets:
                    st.subheader("📊 Historical Data Comparison")
                    st.info(f"Found {len(st.session_state.similar_datasets)} similar dataset(s)")
                    
                    for similar in st.session_state.similar_datasets[:3]:
                        record = similar['record']
                        with st.expander(f"📁 {record['dataset_name']} ({record['period_month']}/{record['period_year']})"):
                            st.write(f"**Similarity:** {similar['similarity']*100:.1f}%")
                            st.write(f"**Rows:** {record['row_count']:,}")
                            if record.get('summary_stats'):
                                st.json(record['summary_stats'])
                
                st.subheader("📈 Forecasting")
                if numeric_cols:
                    col1, col2 = st.columns(2)
                    with col1:
                        target_col = st.selectbox("Target Column", numeric_cols, key="pred_target")
                    with col2:
                        periods = st.slider("Forecast Periods", 1, 12, 6)
                    
                    if st.button("🔮 Generate Forecast", use_container_width=True):
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
                                        st.markdown(f'<div class="insight-box">📈 **Trend:** {trend_info} | **Confidence:** {confidence}</div>', unsafe_allow_html=True)
                                
                                trend_analysis = analyze_trend(df_pred, target_col)
                                if trend_analysis:
                                    st.markdown(f'<div class="insight-box">📊 **Analysis:** {trend_analysis}</div>', unsafe_allow_html=True)
        
        with tabs[5]:
            st.header("🤖 ML & Clustering Analytics")
            
            df_ml = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
            numeric_cols_ml = df_ml.select_dtypes(include=[np.number]).columns.tolist()
            cat_cols_ml = df_ml.select_dtypes(include=['object', 'category']).columns.tolist()
            
            ml_subtabs = st.tabs(["📊 Categorical Analysis", "🎯 ML Prediction", "🔮 Risk Clustering", "⚠️ Outlier Detection"])
            
            with ml_subtabs[0]:
                st.subheader("📊 Categorical Data Analysis")
                if cat_cols_ml:
                    cat_insights = analyze_categorical_insights(df_ml)
                    
                    for col in cat_cols_ml[:5]:
                        with st.expander(f"📌 {col}", expanded=True):
                            if col in cat_insights:
                                insight = cat_insights[col]
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Unique Values", insight['unique_values'])
                                with col2:
                                    st.metric("Missing", f"{insight['missing_pct']}%")
                                with col3:
                                    st.metric("Balance Ratio", f"{insight['balance_ratio']:.2f}")
                                
                                chart_type = st.radio(f"Chart type for {col}", ["Pie Chart", "Bar Chart"], key=f"cat_chart_{col}", horizontal=True)
                                if chart_type == "Pie Chart":
                                    fig = create_categorical_distribution(df_ml, col)
                                else:
                                    fig = create_categorical_bar_chart(df_ml, col)
                                st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No categorical columns found in the dataset.")
            
            with ml_subtabs[1]:
                st.subheader("🎯 ML Prediction Model")
                st.markdown("Build a machine learning model to predict any target variable in your data.")
                
                if len(numeric_cols_ml) >= 3:
                    target_col_ml = st.selectbox("Select Target Variable to Predict", numeric_cols_ml, key="ml_target")
                    
                    if st.button("🚀 Build Prediction Model", use_container_width=True):
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
                                    st.subheader("📊 Feature Importance")
                                    fig = create_feature_importance_chart(result['feature_importance'])
                                    st.plotly_chart(fig, use_container_width=True)
                                
                                st.subheader("📋 Model Details")
                                st.json(result)
                else:
                    st.warning("Need at least 3 numeric columns for ML prediction.")
            
            with ml_subtabs[2]:
                st.subheader("🔮 Customer/Data Clustering")
                st.markdown("Segment your data into risk-based clusters using K-Means algorithm.")
                
                if len(numeric_cols_ml) >= 2:
                    n_clusters = st.slider("Number of Clusters", 2, 6, 4, key="n_clusters")
                    
                    if st.button("🎯 Create Clusters", use_container_width=True):
                        with st.spinner("Creating clusters..."):
                            result = create_risk_clusters(df_ml, n_clusters)
                            
                            if 'error' in result:
                                st.error(result['error'])
                            else:
                                st.success(f"Created {n_clusters} clusters successfully!")
                                
                                st.subheader("📊 Cluster Distribution")
                                for cluster_name, stats in result['cluster_stats'].items():
                                    with st.expander(f"{cluster_name} ({stats['size']:,} records - {stats['percentage']}%)"):
                                        st.write("**Characteristics:**")
                                        for col, char in stats['characteristics'].items():
                                            st.write(f"- {col}: Mean = {char['mean']}, Std = {char['std']}")
                                
                                st.subheader("📈 Cluster Visualization")
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
            
            with ml_subtabs[3]:
                st.subheader("⚠️ Outlier Detection")
                
                outliers = detect_outliers(df_ml)
                
                if outliers:
                    st.write(f"Found outliers in **{len(outliers)}** columns:")
                    
                    for col, info in outliers.items():
                        with st.expander(f"⚠️ {col} - {info['count']} outliers ({info['percentage']}%)"):
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Outlier Count", info['count'])
                            with col2:
                                st.metric("Lower Bound", f"{info['lower_bound']:.2f}")
                            with col3:
                                st.metric("Upper Bound", f"{info['upper_bound']:.2f}")
                            
                            if info.get('min_outlier') and info.get('max_outlier'):
                                st.write(f"**Range of outliers:** {info['min_outlier']:.2f} to {info['max_outlier']:.2f}")
                            
                            fig = create_outlier_visualization(df_ml, col, info)
                            st.plotly_chart(fig, use_container_width=True)
                else:
                    st.success("No significant outliers detected in the numeric columns.")
        
        with tabs[6]:
            st.header("💬 AI Chat Assistant")
            
            if not limits['ai_chat_enabled']:
                st.markdown("""
                <div class="neon-card">
                    <h3 style="text-align: center;">⭐ Tier 3 Feature</h3>
                    <p style="text-align: center; color: #94a3b8;">
                        AI-powered data conversations are available in Tier 3.
                    </p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("📊 View Tiers", use_container_width=True, key="upgrade_chat"):
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
                            <div style="font-size: 3rem; margin-bottom: 1rem;">💬</div>
                            <p>Start a conversation about your data!</p>
                            <p style="font-size: 0.85rem;">Try asking: "What patterns do you see?" or "Summarize the key insights"</p>
                        </div>
                        """, unsafe_allow_html=True)
                    else:
                        for msg in st.session_state.chat_messages:
                            role_icon = "👤" if msg["role"] == "user" else "🤖"
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
                    
                    with st.spinner("🤖 Analyzing your data..."):
                        df_chat = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
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
        
        with tabs[7]:
            st.header("📝 Comprehensive Report")
            
            df_report = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
            
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
                st.subheader("🤖 AI Insights & Recommendations")
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
            st.subheader("📥 Download Report")
            
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
    
    show_support_section()


def show_support_section():
    st.markdown('''
    <div style="height:1px;background:linear-gradient(90deg,transparent,rgba(20,184,166,0.25),transparent);margin:2rem 0 2.5rem 0;"></div>
    <div class="lp-support-section">
        <div class="lp-support-header">
            <h2>Contact Support</h2>
            <p>Have a question or need help? We&rsquo;re here for you.</p>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="lp-support-card">', unsafe_allow_html=True)
        with st.form("support_form", clear_on_submit=True):
            support_email = st.text_input("Email Address", placeholder="your@email.com")
            support_name = st.text_input("Full Name", placeholder="Your full name")
            support_message = st.text_area("Message", placeholder="Describe your question, request, or issue…", height=140)
            support_submit = st.form_submit_button("Send Message", use_container_width=True)

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
                        st.success("Message sent — we'll get back to you soon.")
                    finally:
                        db.close()
        st.markdown('</div>', unsafe_allow_html=True)


def show_home_page():
    logo_b64 = get_logo_base64()

    # ── HERO ──────────────────────────────────────────────────────────────────
    st.markdown(f'''
    <div class="lp-hero" style="text-align:center;margin-top:2rem;margin-bottom:0.75rem;">
        <a href="/" target="_self" style="display:inline-block;" class="logo-link">
            <img src="data:image/png;base64,{logo_b64}"
                 style="max-width:460px;width:88%;border-radius:12px;"
                 alt="DataVision Pro">
        </a>
        <h1 style="font-size:2rem;font-weight:800;letter-spacing:-0.02em;
                   background:linear-gradient(135deg,#14b8a6,#0d9488,#94a3b8);
                   -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                   background-clip:text;margin:1rem 0 0.4rem 0;line-height:1.2;">
            Intelligent Data Analytics,<br>Done in Seconds
        </h1>
        <p style="font-size:1.1rem;color:#94a3b8;font-weight:400;
                  max-width:540px;margin:0 auto;line-height:1.65;">
            Upload any dataset and get instant cleaning, statistics, charts,
            and AI-powered insights —
            <span style="color:#14b8a6;font-weight:600;">no code required.</span>
        </p>
    </div>
    ''', unsafe_allow_html=True)

    # ── CTA BUTTONS ───────────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="lp-btn-primary">', unsafe_allow_html=True)
        if st.button("Start Your Free Analysis", use_container_width=True, type="primary"):
            st.session_state.page = 'login'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div style="height:0.6rem;"></div>', unsafe_allow_html=True)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown('<div class="lp-btn-secondary">', unsafe_allow_html=True)
            if st.button("Sign In", use_container_width=True):
                st.session_state.page = 'login'
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with c2:
            st.markdown('<div class="lp-btn-secondary">', unsafe_allow_html=True)
            if st.button("Create Account", use_container_width=True):
                st.session_state.page = 'register'
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

    # ── TRUST BAR ─────────────────────────────────────────────────────────────
    st.markdown('''
    <div class="lp-trust">
        <div class="lp-trust-bar">
            <span class="lp-trust-pill">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2.5"
                     stroke-linecap="round" stroke-linejoin="round">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                </svg>
                1 Million+ Rows Supported
            </span>
            <span class="lp-trust-pill">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2.5"
                     stroke-linecap="round" stroke-linejoin="round">
                    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
                    <line x1="16" y1="2" x2="16" y2="6"/>
                    <line x1="8" y1="2" x2="8" y2="6"/>
                    <line x1="3" y1="10" x2="21" y2="10"/>
                </svg>
                60-Day Free Trial
            </span>
            <span class="lp-trust-pill">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2.5"
                     stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="12" cy="12" r="10"/>
                    <path d="M12 8v4l3 3"/>
                </svg>
                AI-Powered Insights
            </span>
            <span class="lp-trust-pill">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24"
                     fill="none" stroke="currentColor" stroke-width="2.5"
                     stroke-linecap="round" stroke-linejoin="round">
                    <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                </svg>
                No Card Required
            </span>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    # ── FEATURE CARDS ─────────────────────────────────────────────────────────
    st.markdown('''
    <div class="lp-features">
        <div class="lp-feature-grid">

            <div class="lp-feat-card">
                <div class="lp-feat-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                         fill="none" stroke="#14b8a6" stroke-width="2"
                         stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="22 11 12 2 2 11"/><path d="M12 2v20"/>
                        <path d="M5 12H2"/><path d="M22 12h-3"/>
                        <circle cx="12" cy="18" r="1"/>
                    </svg>
                </div>
                <div class="lp-feat-title">Auto Cleaning</div>
                <div class="lp-feat-desc">Removes duplicates, fixes missing values, and eliminates outliers in one click.</div>
            </div>

            <div class="lp-feat-card">
                <div class="lp-feat-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                         fill="none" stroke="#14b8a6" stroke-width="2"
                         stroke-linecap="round" stroke-linejoin="round">
                        <line x1="18" y1="20" x2="18" y2="10"/>
                        <line x1="12" y1="20" x2="12" y2="4"/>
                        <line x1="6" y1="20" x2="6" y2="14"/>
                    </svg>
                </div>
                <div class="lp-feat-title">Deep Analytics</div>
                <div class="lp-feat-desc">Comprehensive statistics, correlations, distributions, and interactive charts.</div>
            </div>

            <div class="lp-feat-card">
                <div class="lp-feat-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                         fill="none" stroke="#14b8a6" stroke-width="2"
                         stroke-linecap="round" stroke-linejoin="round">
                        <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
                    </svg>
                </div>
                <div class="lp-feat-title">AI Powered</div>
                <div class="lp-feat-desc">GPT-driven chat assistant and smart recommendations tailored to your data.</div>
            </div>

            <div class="lp-feat-card">
                <div class="lp-feat-icon">
                    <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24"
                         fill="none" stroke="#14b8a6" stroke-width="2"
                         stroke-linecap="round" stroke-linejoin="round">
                        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
                    </svg>
                </div>
                <div class="lp-feat-title">Predictions</div>
                <div class="lp-feat-desc">ML models and trend analysis that forecast what your data will look like next.</div>
            </div>

        </div>
    </div>
    ''', unsafe_allow_html=True)

    # ── HOW IT WORKS ──────────────────────────────────────────────────────────
    st.markdown('''
    <div class="lp-hiw">
        <div class="lp-hiw-section">
            <h2>How It Works</h2>
            <div class="lp-steps-grid">

                <div class="lp-step-card">
                    <div class="lp-step-num">1</div>
                    <div class="lp-step-title">Upload Your File</div>
                    <div class="lp-step-desc">Drop any CSV or Excel file — up to 1 million rows, 200 MB.</div>
                </div>

                <div class="lp-step-card">
                    <div class="lp-step-num">2</div>
                    <div class="lp-step-title">Clean &amp; Analyse</div>
                    <div class="lp-step-desc">One click auto-cleans your data and runs a full statistical report.</div>
                </div>

                <div class="lp-step-card">
                    <div class="lp-step-num">3</div>
                    <div class="lp-step-title">Get Insights</div>
                    <div class="lp-step-desc">Explore interactive charts, AI recommendations, and exportable PDF reports.</div>
                </div>

            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    # ── TIERS TEASER ──────────────────────────────────────────────────────────
    st.markdown('''
    <div class="lp-tiers">
        <div class="lp-tiers-section">
            <h2>Choose Your Plan</h2>
            <p class="lp-tiers-sub">All tiers are free during the testing period — full Tier 3 access for 60 days on sign-up.</p>
            <div class="lp-tiers-grid">

                <div class="lp-tier-card">
                    <div class="lp-tier-name">Tier 1</div>
                    <div class="lp-tier-tagline">Perfect for getting started</div>
                    <ul class="lp-tier-features">
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Up to 10,000 rows
                        </li>
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Auto Cleaning &amp; Analytics
                        </li>
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Files up to 50 MB
                        </li>
                    </ul>
                </div>

                <div class="lp-tier-card featured">
                    <div class="lp-tier-badge">Most Popular</div>
                    <div class="lp-tier-name">Tier 2</div>
                    <div class="lp-tier-tagline">For growing teams &amp; businesses</div>
                    <ul class="lp-tier-features">
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Up to 500,000 rows
                        </li>
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            ML &amp; Predictions
                        </li>
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Files up to 200 MB
                        </li>
                    </ul>
                </div>

                <div class="lp-tier-card">
                    <div class="lp-tier-name">Tier 3</div>
                    <div class="lp-tier-tagline">Full power, unlimited potential</div>
                    <ul class="lp-tier-features">
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Up to 1 Million rows
                        </li>
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            AI Chat &amp; Export Reports
                        </li>
                        <li>
                            <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24"
                                 fill="none" stroke="currentColor" stroke-width="2.5"
                                 stroke-linecap="round" stroke-linejoin="round">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            Everything in Tier 2
                        </li>
                    </ul>
                </div>

            </div>
        </div>
    </div>
    ''', unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div class="lp-btn-outline">', unsafe_allow_html=True)
        if st.button("View All Plans & Features", use_container_width=True):
            st.session_state.page = 'pricing'
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    # ── VIEWPORT-TRIGGERED ANIMATIONS (IntersectionObserver) ─────────────────
    st.components.v1.html("""
    <script>
    (function() {
        var CLASSES = ['lp-hero','lp-trust','lp-features','lp-hiw','lp-tiers'];
        function observe(doc) {
            var prefersReduced = doc.defaultView &&
                doc.defaultView.matchMedia &&
                doc.defaultView.matchMedia('(prefers-reduced-motion: reduce)').matches;
            if (prefersReduced) return;
            var io = new doc.defaultView.IntersectionObserver(function(entries) {
                entries.forEach(function(e) {
                    if (e.isIntersecting) {
                        e.target.classList.add('lp-visible');
                        io.unobserve(e.target);
                    }
                });
            }, { threshold: 0.12 });
            CLASSES.forEach(function(cls) {
                doc.querySelectorAll('.' + cls).forEach(function(el) {
                    io.observe(el);
                });
            });
        }
        function init() {
            try {
                var doc = window.parent.document;
                observe(doc);
                // Re-run after a short delay to catch late-rendered Streamlit elements
                setTimeout(function() { observe(doc); }, 600);
            } catch(e) {}
        }
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', init);
        } else {
            init();
        }
    })();
    </script>
    """, height=0)

    # ── SUPPORT FORM ──────────────────────────────────────────────────────────
    show_support_section()


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
