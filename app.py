import streamlit as st
import pandas as pd
import numpy as np
import hashlib
from datetime import datetime
import io

from models import (
    init_db, get_db, save_dataset_record, find_similar_datasets, 
    get_datasets_by_name, save_chat_message, get_chat_history,
    create_user, authenticate_user, get_user_by_id, get_all_users,
    get_all_datasets, get_admin_stats, increment_analysis_count, User
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
    initial_sidebar_state="expanded"
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
    gap: 6px;
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

FREE_LIMITS = {
    'max_rows': 1000000,  # Temporarily unlimited for testing
    'max_analyses_per_day': 999999,  # Temporarily unlimited for testing
    'max_file_size_mb': 100,  # Temporarily unlimited for testing
    'ai_chat_enabled': True,  # Temporarily enabled for testing
    'predictions_enabled': True,  # Temporarily enabled for testing
    'export_enabled': True  # Temporarily enabled for testing
}

PREMIUM_LIMITS = {
    'max_rows': 1000000,
    'max_analyses_per_day': 999999,
    'max_file_size_mb': 100,
    'ai_chat_enabled': True,
    'predictions_enabled': True,
    'export_enabled': True
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
        'last_login': user.last_login
    }


def get_user_limits():
    if st.session_state.user and st.session_state.user.get('subscription_type') == 'premium':
        return PREMIUM_LIMITS
    return FREE_LIMITS


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
    # Redirect if already logged in
    if st.session_state.user:
        st.session_state.page = 'dashboard'
        st.rerun()
        return
    
    st.markdown('<h2 class="glow-text" style="font-size: 2.5rem;">Create Account</h2>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Start your data analytics journey today</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("register_form"):
            full_name = st.text_input("Full Name", placeholder="Enter your full name")
            username = st.text_input("Username", placeholder="Choose a username")
            email = st.text_input("Email Address", placeholder="Enter your email")
            password = st.text_input("Password", type="password", placeholder="Choose a strong password")
            confirm_password = st.text_input("Confirm Password", type="password", placeholder="Re-enter your password")
            submit = st.form_submit_button("Create Account", use_container_width=True)
            
            if submit:
                if not all([full_name, username, email, password, confirm_password]):
                    st.warning("Please fill in all fields")
                elif password != confirm_password:
                    st.error("Passwords do not match")
                elif len(password) < 6:
                    st.error("Password must be at least 6 characters")
                else:
                    db = get_db()
                    try:
                        user = create_user(db, email, username, password, full_name)
                        if user:
                            st.session_state.user = user_to_dict(user)
                            st.session_state.page = 'dashboard'
                        else:
                            st.error("Email or username already exists")
                    finally:
                        db.close()
        
        # Check if registration was successful and rerun outside form
        if st.session_state.user and st.session_state.page == 'dashboard':
            st.success("Account created successfully!")
            st.rerun()
        
        st.markdown("---")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("← Back to Home", use_container_width=True):
                st.session_state.page = 'home'
                st.rerun()
        with col_b:
            if st.button("Sign In →", use_container_width=True):
                st.session_state.page = 'login'
                st.rerun()


def show_pricing_page():
    st.markdown('<h2 class="glow-text" style="font-size: 2.5rem;">Choose Your Plan</h2>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Select the perfect plan for your data analytics needs</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="pricing-card">
            <div class="pricing-title">Starter</div>
            <div class="pricing-price">$0</div>
            <div class="pricing-period">Free Forever</div>
            <div class="feature-list">
                <div class="feature-item included">✓ Analyze up to 1,000 rows</div>
                <div class="feature-item included">✓ 5 analyses per day</div>
                <div class="feature-item included">✓ Basic visualizations</div>
                <div class="feature-item included">✓ Auto data cleaning</div>
                <div class="feature-item">✗ AI Chat Assistant</div>
                <div class="feature-item">✗ Advanced Predictions</div>
                <div class="feature-item">✗ Export Reports</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Get Started Free", key="free_btn", use_container_width=True):
            st.session_state.page = 'register'
            st.rerun()
    
    with col2:
        st.markdown("""
        <div class="pricing-card premium">
            <div class="pricing-title">Professional</div>
            <div class="pricing-price">$29</div>
            <div class="pricing-period">Per Month</div>
            <div class="feature-list">
                <div class="feature-item included">✓ Unlimited data analysis</div>
                <div class="feature-item included">✓ Unlimited analyses</div>
                <div class="feature-item included">✓ All visualizations</div>
                <div class="feature-item included">✓ Advanced data cleaning</div>
                <div class="feature-item included">✓ AI Chat Assistant</div>
                <div class="feature-item included">✓ Advanced Predictions</div>
                <div class="feature-item included">✓ PDF Report Export</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Subscribe Now", key="premium_btn", use_container_width=True):
            st.info("Stripe payment integration coming soon!")
    
    st.markdown("---")
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
                <div class="admin-stat-icon">💎</div>
                <div class="admin-stat-value">{stats['premium_users']}</div>
                <div class="admin-stat-label">Premium</div>
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
                        'Plan': '💎 Premium' if u.subscription_type == 'premium' else '🆓 Free',
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


def show_dashboard():
    limits = get_user_limits()
    
    with st.sidebar:
        st.markdown('<div class="sidebar-header">🔮 DataVision Pro</div>', unsafe_allow_html=True)
        
        if st.session_state.user:
            user = st.session_state.user
            badge_class = "badge-premium" if user.get('subscription_type') == "premium" else "badge-free"
            badge_text = "💎 Premium" if user.get('subscription_type') == "premium" else "🆓 Free"
            
            st.markdown(f"""
            <div class="user-badge">
                <div style="font-size: 1.1rem; font-weight: 600; color: #fff;">👤 {user.get('full_name') or user.get('username')}</div>
                <div style="margin-top: 0.5rem;"><span class="{badge_class}">{badge_text}</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            if user.get('is_admin'):
                if st.button("⚙️ Admin Panel", use_container_width=True):
                    st.session_state.page = 'admin'
                    st.rerun()
            
            if user.get('subscription_type') != "premium":
                if st.button("💎 Upgrade to Premium", use_container_width=True):
                    st.session_state.page = 'pricing'
                    st.rerun()
            
            if st.button("🚪 Sign Out", use_container_width=True):
                st.session_state.user = None
                st.session_state.page = 'home'
                st.session_state.df = None
                st.session_state.df_cleaned = None
                st.rerun()
        
        st.markdown("---")
        st.header("📤 Upload Data")
        
        uploaded_file = st.file_uploader(
            "Choose CSV or Excel file",
            type=['csv', 'xlsx', 'xls'],
            help="Upload your data file for analysis"
        )
        
        if uploaded_file:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            
            if file_size_mb > limits['max_file_size_mb']:
                st.error(f"File size ({file_size_mb:.1f} MB) exceeds the limit ({limits['max_file_size_mb']} MB)")
            else:
                st.success(f"Uploaded: {uploaded_file.name}")
                
                st.subheader("📅 Time Period")
                col1, col2 = st.columns(2)
                with col1:
                    period_month = st.selectbox("Month", range(1, 13), index=datetime.now().month - 1)
                with col2:
                    period_year = st.selectbox("Year", range(2020, 2030), index=datetime.now().year - 2020)
                
                dataset_name = st.text_input("Dataset Name", value=uploaded_file.name.split('.')[0])
                
                if st.button("🚀 Start Analysis", type="primary", use_container_width=True):
                    with st.spinner("Loading and analyzing data..."):
                        df = load_file(uploaded_file)
                        
                        if df is not None:
                            if len(df) > limits['max_rows']:
                                st.error(f"Row count ({len(df):,}) exceeds the limit ({limits['max_rows']:,})")
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
                                        db,
                                        filename=uploaded_file.name,
                                        dataset_name=dataset_name,
                                        period_month=period_month,
                                        period_year=period_year,
                                        row_count=len(df),
                                        column_count=len(df.columns),
                                        columns_info=columns_info,
                                        data_hash=data_hash,
                                        summary_stats=sanitize_for_json(analysis_results.get('numeric_summary', {}))
                                    )
                                    st.session_state.current_dataset_id = record.id
                                    
                                    similar = find_similar_datasets(db, columns_info)
                                    similar = [s for s in similar if s['record'].id != record.id]
                                    st.session_state.similar_datasets = similar
                                    
                                    if st.session_state.user:
                                        increment_analysis_count(db, st.session_state.user.get('id'))
                                finally:
                                    db.close()
                                
                                st.success("Analysis completed!")
                                st.rerun()
        
        if st.session_state.df is not None:
            st.markdown("---")
            st.subheader("📊 Data Summary")
            st.write(f"**Rows:** {len(st.session_state.df):,}")
            st.write(f"**Columns:** {len(st.session_state.df.columns)}")
            
            if st.session_state.df_cleaned is not None:
                quality = get_data_quality_score(st.session_state.df_cleaned)
                st.metric("Data Quality", f"{quality['overall_score']}%")
    
    st.markdown('<h1 class="glow-text">🔮 DataVision Pro</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Intelligent Data Analytics Platform — Powered by AI</p>', unsafe_allow_html=True)
    
    if st.session_state.df is not None:
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
                    <h3 style="text-align: center;">💎 Premium Feature</h3>
                    <p style="text-align: center; color: #94a3b8;">
                        Advanced predictions and time-series comparisons are available exclusively for Premium subscribers.
                    </p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("💎 Upgrade Now", use_container_width=True, key="upgrade_pred"):
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
                        with st.expander(f"📁 {record.dataset_name} ({record.period_month}/{record.period_year})"):
                            st.write(f"**Similarity:** {similar['similarity']*100:.1f}%")
                            st.write(f"**Rows:** {record.row_count:,}")
                            if record.summary_stats:
                                st.json(record.summary_stats)
                
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
                    <h3 style="text-align: center;">💎 Premium Feature</h3>
                    <p style="text-align: center; color: #94a3b8;">
                        AI-powered data conversations are available exclusively for Premium subscribers.
                    </p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("💎 Upgrade Now", use_container_width=True, key="upgrade_chat"):
                    st.session_state.page = 'pricing'
                    st.rerun()
            else:
                st.markdown("Ask any question about your data and get AI-powered insights")
                
                for msg in st.session_state.chat_messages:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                
                if prompt := st.chat_input("Type your question here..."):
                    st.session_state.chat_messages.append({"role": "user", "content": prompt})
                    
                    with st.chat_message("user"):
                        st.write(prompt)
                    
                    with st.chat_message("assistant"):
                        with st.spinner("Analyzing..."):
                            df_chat = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
                            df_info = {
                                'row_count': len(df_chat),
                                'column_count': len(df_chat.columns),
                                'columns': df_chat.columns.tolist(),
                                'dtypes': df_chat.dtypes.astype(str).to_dict(),
                                'numeric_summary': df_chat.describe().to_dict() if not df_chat.select_dtypes(include=[np.number]).empty else {}
                            }
                            response = chat_about_data(prompt, df_info)
                            st.write(response)
                            st.session_state.chat_messages.append({"role": "assistant", "content": response})
                            
                            db = get_db()
                            try:
                                save_chat_message(db, st.session_state.current_dataset_id, prompt, response)
                            finally:
                                db.close()
        
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
    
    else:
        st.markdown("""
        <div class="neon-card" style="text-align: center; padding: 4rem 2rem;">
            <div class="hero-badge">AI-POWERED ANALYTICS</div>
            <h2 style="margin-bottom: 1rem; font-size: 2rem;">Ready to Analyze</h2>
            <p style="color: #94a3b8; font-size: 1.15rem; max-width: 500px; margin: 0 auto;">
                Upload your data file from the sidebar to start intelligent analysis
            </p>
            <p style="color: #64748b; margin-top: 1rem;">
                Supported formats: CSV, Excel (XLS, XLSX)
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class="neon-card">
                <div style="font-size: 2.5rem; margin-bottom: 1rem;">🧹</div>
                <h3>Smart Cleaning</h3>
                <p style="color: #94a3b8;">
                    Automatic data cleaning with duplicate removal and missing value handling
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="neon-card">
                <div style="font-size: 2.5rem; margin-bottom: 1rem;">📊</div>
                <h3>Deep Analysis</h3>
                <p style="color: #94a3b8;">
                    Comprehensive statistical analysis with interactive visualizations
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="neon-card">
                <div style="font-size: 2.5rem; margin-bottom: 1rem;">🤖</div>
                <h3>AI Assistant</h3>
                <p style="color: #94a3b8;">
                    Chat with your data and get intelligent insights and recommendations
                </p>
            </div>
            """, unsafe_allow_html=True)


def show_home_page():
    st.markdown('<div style="text-align: center;"><span class="hero-badge">NEXT-GEN DATA PLATFORM</span></div>', unsafe_allow_html=True)
    st.markdown('<h1 class="glow-text">DataVision Pro</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">Transform your data into actionable insights with the power of AI</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button("🔐 Sign In", use_container_width=True):
                st.session_state.page = 'login'
                st.rerun()
        with bcol2:
            if st.button("📝 Create Account", use_container_width=True):
                st.session_state.page = 'register'
                st.rerun()
        
        if st.button("🚀 Try Without Account", use_container_width=True, type="primary"):
            st.session_state.page = 'dashboard'
            st.rerun()
    
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">🧹</div>
            <div class="metric-label">Auto Cleaning</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">📊</div>
            <div class="metric-label">Deep Analytics</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">🤖</div>
            <div class="metric-label">AI Powered</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">🔮</div>
            <div class="metric-label">Predictions</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    show_pricing_page()


with st.sidebar:
    if st.session_state.page not in ['home', 'login', 'register', 'pricing']:
        pass
    else:
        st.markdown('<div class="sidebar-header">🔮 DataVision Pro</div>', unsafe_allow_html=True)
        
        if st.button("🏠 Home", use_container_width=True):
            st.session_state.page = 'home'
            st.rerun()
        
        if st.button("🔐 Sign In", use_container_width=True):
            st.session_state.page = 'login'
            st.rerun()
        
        if st.button("📝 Register", use_container_width=True):
            st.session_state.page = 'register'
            st.rerun()
        
        if st.button("💎 Pricing", use_container_width=True):
            st.session_state.page = 'pricing'
            st.rerun()

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
