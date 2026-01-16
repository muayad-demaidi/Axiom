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
    create_distribution_overview, create_comparison_chart, create_trend_chart
)
from predictions import (
    compare_datasets, simple_forecast, analyze_trend, 
    predict_column, calculate_growth_metrics
)
from ai_assistant import (
    generate_data_insights, chat_about_data, 
    generate_comparison_insights, generate_prediction_insights
)

st.set_page_config(
    page_title="DataVision Pro - نظام تحليل البيانات الذكي",
    page_icon="🔮",
    layout="wide",
    initial_sidebar_state="expanded"
)

NEON_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700&display=swap');

:root {
    --neon-purple: #a855f7;
    --neon-pink: #ec4899;
    --neon-blue: #3b82f6;
    --neon-cyan: #06b6d4;
    --dark-bg: #0f0f1a;
    --dark-card: #1a1a2e;
    --dark-card-hover: #252542;
    --text-primary: #ffffff;
    --text-secondary: #a0a0b0;
}

.stApp {
    background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #0f0f1a 100%);
}

.main-container {
    font-family: 'Cairo', sans-serif;
}

.animated-bg {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: -1;
    overflow: hidden;
}

.floating-data {
    position: absolute;
    font-family: 'Courier New', monospace;
    color: rgba(168, 85, 247, 0.15);
    font-size: 14px;
    animation: float-up 15s linear infinite;
    white-space: nowrap;
}

@keyframes float-up {
    0% {
        transform: translateY(100vh) rotate(0deg);
        opacity: 0;
    }
    10% {
        opacity: 1;
    }
    90% {
        opacity: 1;
    }
    100% {
        transform: translateY(-100vh) rotate(360deg);
        opacity: 0;
    }
}

.glow-text {
    font-size: 3rem;
    font-weight: 700;
    text-align: center;
    background: linear-gradient(135deg, #a855f7, #ec4899, #3b82f6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    text-shadow: 0 0 30px rgba(168, 85, 247, 0.5);
    margin-bottom: 0.5rem;
}

.sub-title {
    font-size: 1.2rem;
    text-align: center;
    color: #a0a0b0;
    margin-bottom: 2rem;
}

.neon-card {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 1px solid rgba(168, 85, 247, 0.3);
    border-radius: 16px;
    padding: 1.5rem;
    margin: 1rem 0;
    box-shadow: 0 8px 32px rgba(168, 85, 247, 0.15);
    transition: all 0.3s ease;
}

.neon-card:hover {
    border-color: rgba(168, 85, 247, 0.6);
    box-shadow: 0 12px 40px rgba(168, 85, 247, 0.25);
    transform: translateY(-2px);
}

.metric-card {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 1px solid rgba(168, 85, 247, 0.3);
    border-radius: 12px;
    padding: 1.2rem;
    text-align: center;
    box-shadow: 0 4px 20px rgba(168, 85, 247, 0.1);
}

.metric-value {
    font-size: 2rem;
    font-weight: 700;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.metric-label {
    font-size: 0.9rem;
    color: #a0a0b0;
    margin-top: 0.3rem;
}

.pricing-card {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 2px solid rgba(168, 85, 247, 0.3);
    border-radius: 20px;
    padding: 2rem;
    text-align: center;
    transition: all 0.3s ease;
    position: relative;
    overflow: hidden;
}

.pricing-card.premium {
    border-color: #a855f7;
    box-shadow: 0 0 40px rgba(168, 85, 247, 0.3);
}

.pricing-card.premium::before {
    content: 'الأكثر شعبية';
    position: absolute;
    top: 15px;
    right: -35px;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    color: white;
    padding: 5px 40px;
    font-size: 0.75rem;
    transform: rotate(45deg);
}

.pricing-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 0.5rem;
}

.pricing-price {
    font-size: 2.5rem;
    font-weight: 700;
    background: linear-gradient(135deg, #a855f7, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}

.pricing-period {
    color: #a0a0b0;
    font-size: 0.9rem;
}

.feature-list {
    text-align: right;
    margin: 1.5rem 0;
}

.feature-item {
    padding: 0.5rem 0;
    color: #a0a0b0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.feature-item.included {
    color: #10b981;
}

.neon-button {
    background: linear-gradient(135deg, #a855f7, #ec4899);
    color: white;
    border: none;
    padding: 12px 30px;
    border-radius: 25px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s ease;
    box-shadow: 0 4px 20px rgba(168, 85, 247, 0.4);
}

.neon-button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 30px rgba(168, 85, 247, 0.6);
}

.auth-container {
    max-width: 400px;
    margin: 2rem auto;
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 1px solid rgba(168, 85, 247, 0.3);
    border-radius: 20px;
    padding: 2rem;
    box-shadow: 0 20px 60px rgba(168, 85, 247, 0.2);
}

.sidebar-header {
    background: linear-gradient(135deg, #a855f7, #ec4899);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    font-size: 1.5rem;
    font-weight: 700;
    text-align: center;
    margin-bottom: 1rem;
}

.user-badge {
    background: linear-gradient(145deg, #252542, #1a1a2e);
    border: 1px solid rgba(168, 85, 247, 0.3);
    border-radius: 12px;
    padding: 1rem;
    text-align: center;
    margin-bottom: 1rem;
}

.badge-free {
    background: linear-gradient(135deg, #6b7280, #4b5563);
    padding: 4px 12px;
    border-radius: 15px;
    font-size: 0.75rem;
    color: white;
}

.badge-premium {
    background: linear-gradient(135deg, #a855f7, #ec4899);
    padding: 4px 12px;
    border-radius: 15px;
    font-size: 0.75rem;
    color: white;
}

.admin-stat-card {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 1px solid rgba(168, 85, 247, 0.3);
    border-radius: 16px;
    padding: 1.5rem;
    text-align: center;
}

.admin-stat-icon {
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
}

.admin-stat-value {
    font-size: 2rem;
    font-weight: 700;
    color: #a855f7;
}

.admin-stat-label {
    color: #a0a0b0;
    font-size: 0.9rem;
}

.insight-box {
    background: linear-gradient(145deg, rgba(168, 85, 247, 0.1), rgba(236, 72, 153, 0.05));
    border-right: 4px solid #a855f7;
    padding: 1rem;
    margin: 1rem 0;
    border-radius: 8px;
}

.warning-box {
    background: linear-gradient(145deg, rgba(239, 68, 68, 0.1), rgba(239, 68, 68, 0.05));
    border-right: 4px solid #ef4444;
    padding: 1rem;
    margin: 1rem 0;
    border-radius: 8px;
}

.success-box {
    background: linear-gradient(145deg, rgba(16, 185, 129, 0.1), rgba(16, 185, 129, 0.05));
    border-right: 4px solid #10b981;
    padding: 1rem;
    margin: 1rem 0;
    border-radius: 8px;
}

[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 100%);
    border-right: 1px solid rgba(168, 85, 247, 0.2);
}

[data-testid="stSidebar"] [data-testid="stMarkdown"] {
    color: #ffffff;
}

.stButton > button {
    background: linear-gradient(135deg, #a855f7, #ec4899);
    color: white;
    border: none;
    border-radius: 25px;
    padding: 0.5rem 2rem;
    font-weight: 600;
    transition: all 0.3s ease;
    box-shadow: 0 4px 15px rgba(168, 85, 247, 0.3);
}

.stButton > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 25px rgba(168, 85, 247, 0.5);
}

.stTextInput > div > div > input,
.stSelectbox > div > div > div,
.stTextArea > div > div > textarea {
    background-color: #1a1a2e !important;
    border: 1px solid rgba(168, 85, 247, 0.3) !important;
    border-radius: 10px !important;
    color: #ffffff !important;
}

.stTextInput > div > div > input:focus,
.stSelectbox > div > div > div:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #a855f7 !important;
    box-shadow: 0 0 10px rgba(168, 85, 247, 0.3) !important;
}

.stTabs [data-baseweb="tab-list"] {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border-radius: 15px;
    padding: 5px;
    gap: 5px;
}

.stTabs [data-baseweb="tab"] {
    background: transparent;
    color: #a0a0b0;
    border-radius: 10px;
    padding: 10px 20px;
}

.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, #a855f7, #ec4899);
    color: white;
}

.stDataFrame {
    background: #1a1a2e;
    border-radius: 10px;
}

.stMetric {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 1px solid rgba(168, 85, 247, 0.2);
    border-radius: 12px;
    padding: 1rem;
}

.stMetric label {
    color: #a0a0b0 !important;
}

.stMetric [data-testid="stMetricValue"] {
    color: #a855f7 !important;
}

.stExpander {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 1px solid rgba(168, 85, 247, 0.2);
    border-radius: 12px;
}

h1, h2, h3, h4, h5, h6 {
    color: #ffffff !important;
}

p, span, div {
    color: #e0e0e0;
}

.stFileUploader {
    background: linear-gradient(145deg, #1a1a2e, #252542);
    border: 2px dashed rgba(168, 85, 247, 0.4);
    border-radius: 15px;
    padding: 1rem;
}

.stFileUploader:hover {
    border-color: #a855f7;
}
</style>

<div class="animated-bg">
    <div class="floating-data" style="left: 5%; animation-delay: 0s;">01001010 DATA 11010</div>
    <div class="floating-data" style="left: 15%; animation-delay: 2s;">📊 ANALYTICS 📈</div>
    <div class="floating-data" style="left: 25%; animation-delay: 4s;">{ json: "data" }</div>
    <div class="floating-data" style="left: 35%; animation-delay: 6s;">SELECT * FROM</div>
    <div class="floating-data" style="left: 45%; animation-delay: 8s;">🔮 AI INSIGHTS</div>
    <div class="floating-data" style="left: 55%; animation-delay: 1s;">∑ μ σ² π</div>
    <div class="floating-data" style="left: 65%; animation-delay: 3s;">PREDICT()</div>
    <div class="floating-data" style="left: 75%; animation-delay: 5s;">📉 TREND 📈</div>
    <div class="floating-data" style="left: 85%; animation-delay: 7s;">ML MODEL</div>
    <div class="floating-data" style="left: 95%; animation-delay: 9s;">BIG DATA</div>
    <div class="floating-data" style="left: 10%; animation-delay: 10s;">∫ f(x) dx</div>
    <div class="floating-data" style="left: 30%; animation-delay: 11s;">NEURAL NET</div>
    <div class="floating-data" style="left: 50%; animation-delay: 12s;">CLUSTER</div>
    <div class="floating-data" style="left: 70%; animation-delay: 13s;">REGRESSION</div>
    <div class="floating-data" style="left: 90%; animation-delay: 14s;">FORECAST</div>
</div>
"""

st.markdown(NEON_CSS, unsafe_allow_html=True)

FREE_LIMITS = {
    'max_rows': 1000,
    'max_analyses_per_day': 5,
    'max_file_size_mb': 5,
    'ai_chat_enabled': False,
    'predictions_enabled': False,
    'export_enabled': False
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


def get_user_limits():
    if st.session_state.user and st.session_state.user.subscription_type == 'premium':
        return PREMIUM_LIMITS
    return FREE_LIMITS


def calculate_data_hash(df):
    columns_str = '_'.join(sorted(df.columns.tolist()))
    return hashlib.md5(columns_str.encode()).hexdigest()


def load_file(uploaded_file):
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        elif uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            st.error("نوع الملف غير مدعوم. يرجى رفع ملف CSV أو Excel.")
            return None
        return df
    except Exception as e:
        st.error(f"خطأ في قراءة الملف: {str(e)}")
        return None


def show_login_page():
    st.markdown('<h2 class="glow-text" style="font-size: 2rem;">🔐 تسجيل الدخول</h2>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("login_form"):
            email = st.text_input("البريد الإلكتروني أو اسم المستخدم", placeholder="أدخل بريدك الإلكتروني")
            password = st.text_input("كلمة المرور", type="password", placeholder="أدخل كلمة المرور")
            submit = st.form_submit_button("دخول", use_container_width=True)
            
            if submit:
                if email and password:
                    db = get_db()
                    try:
                        user = authenticate_user(db, email, password)
                        if user:
                            st.session_state.user = user
                            st.session_state.page = 'dashboard'
                            st.success("تم تسجيل الدخول بنجاح!")
                            st.rerun()
                        else:
                            st.error("البريد الإلكتروني أو كلمة المرور غير صحيحة")
                    finally:
                        db.close()
                else:
                    st.warning("يرجى ملء جميع الحقول")


def show_register_page():
    st.markdown('<h2 class="glow-text" style="font-size: 2rem;">📝 إنشاء حساب جديد</h2>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        with st.form("register_form"):
            full_name = st.text_input("الاسم الكامل", placeholder="أدخل اسمك الكامل")
            username = st.text_input("اسم المستخدم", placeholder="اختر اسم مستخدم")
            email = st.text_input("البريد الإلكتروني", placeholder="أدخل بريدك الإلكتروني")
            password = st.text_input("كلمة المرور", type="password", placeholder="اختر كلمة مرور قوية")
            confirm_password = st.text_input("تأكيد كلمة المرور", type="password", placeholder="أعد إدخال كلمة المرور")
            submit = st.form_submit_button("إنشاء الحساب", use_container_width=True)
            
            if submit:
                if not all([full_name, username, email, password, confirm_password]):
                    st.warning("يرجى ملء جميع الحقول")
                elif password != confirm_password:
                    st.error("كلمتا المرور غير متطابقتين")
                elif len(password) < 6:
                    st.error("كلمة المرور يجب أن تكون 6 أحرف على الأقل")
                else:
                    db = get_db()
                    try:
                        user = create_user(db, email, username, password, full_name)
                        if user:
                            st.session_state.user = user
                            st.session_state.page = 'dashboard'
                            st.success("تم إنشاء الحساب بنجاح!")
                            st.rerun()
                        else:
                            st.error("البريد الإلكتروني أو اسم المستخدم مستخدم بالفعل")
                    finally:
                        db.close()


def show_pricing_page():
    st.markdown('<h2 class="glow-text" style="font-size: 2rem;">💎 خطط الاشتراك</h2>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">اختر الخطة المناسبة لاحتياجاتك</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div class="pricing-card">
            <div class="pricing-title">المجانية</div>
            <div class="pricing-price">$0</div>
            <div class="pricing-period">مجاناً للأبد</div>
            <div class="feature-list">
                <div class="feature-item included">✅ تحليل حتى 1,000 صف</div>
                <div class="feature-item included">✅ 5 تحليلات يومياً</div>
                <div class="feature-item included">✅ رسومات بيانية أساسية</div>
                <div class="feature-item included">✅ تنظيف البيانات التلقائي</div>
                <div class="feature-item">❌ المحادثة مع AI</div>
                <div class="feature-item">❌ التنبؤات المتقدمة</div>
                <div class="feature-item">❌ تصدير التقارير</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("ابدأ مجاناً", key="free_btn", use_container_width=True):
            st.session_state.page = 'register'
            st.rerun()
    
    with col2:
        st.markdown("""
        <div class="pricing-card premium">
            <div class="pricing-title">الاحترافية</div>
            <div class="pricing-price">$29</div>
            <div class="pricing-period">شهرياً</div>
            <div class="feature-list">
                <div class="feature-item included">✅ تحليل غير محدود للبيانات</div>
                <div class="feature-item included">✅ تحليلات غير محدودة</div>
                <div class="feature-item included">✅ جميع الرسومات البيانية</div>
                <div class="feature-item included">✅ تنظيف البيانات المتقدم</div>
                <div class="feature-item included">✅ المحادثة مع AI</div>
                <div class="feature-item included">✅ التنبؤات المتقدمة</div>
                <div class="feature-item included">✅ تصدير التقارير PDF</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("اشترك الآن", key="premium_btn", use_container_width=True):
            st.info("سيتم تفعيل نظام الدفع قريباً عبر Stripe")


def show_admin_panel():
    st.markdown('<h2 class="glow-text" style="font-size: 2rem;">⚙️ لوحة تحكم الأدمن</h2>', unsafe_allow_html=True)
    
    db = get_db()
    try:
        stats = get_admin_stats(db)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">👥</div>
                <div class="admin-stat-value">{stats['total_users']}</div>
                <div class="admin-stat-label">إجمالي المستخدمين</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">💎</div>
                <div class="admin-stat-value">{stats['premium_users']}</div>
                <div class="admin-stat-label">المشتركين</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">📊</div>
                <div class="admin-stat-value">{stats['total_datasets']}</div>
                <div class="admin-stat-label">البيانات المرفوعة</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div class="admin-stat-card">
                <div class="admin-stat-icon">🔬</div>
                <div class="admin-stat-value">{stats['total_analyses']}</div>
                <div class="admin-stat-label">التحليلات</div>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        admin_tabs = st.tabs(["👥 المستخدمين", "📊 البيانات المرفوعة", "💬 المحادثات"])
        
        with admin_tabs[0]:
            st.subheader("قائمة المستخدمين")
            users = get_all_users(db)
            if users:
                users_data = []
                for u in users:
                    users_data.append({
                        'ID': u.id,
                        'الاسم': u.full_name or u.username,
                        'البريد': u.email,
                        'الاشتراك': '💎 احترافي' if u.subscription_type == 'premium' else '🆓 مجاني',
                        'التحليلات': u.analysis_count or 0,
                        'تاريخ التسجيل': u.created_at.strftime('%Y-%m-%d') if u.created_at else '-',
                        'آخر دخول': u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '-'
                    })
                st.dataframe(pd.DataFrame(users_data), use_container_width=True)
            else:
                st.info("لا يوجد مستخدمين بعد")
        
        with admin_tabs[1]:
            st.subheader("البيانات المرفوعة")
            datasets = get_all_datasets(db)
            if datasets:
                datasets_data = []
                for d in datasets:
                    datasets_data.append({
                        'ID': d.id,
                        'اسم الملف': d.filename,
                        'اسم المجموعة': d.dataset_name,
                        'الصفوف': d.row_count,
                        'الأعمدة': d.column_count,
                        'الفترة': f"{d.period_month}/{d.period_year}" if d.period_month else '-',
                        'تاريخ الرفع': d.upload_date.strftime('%Y-%m-%d %H:%M') if d.upload_date else '-'
                    })
                st.dataframe(pd.DataFrame(datasets_data), use_container_width=True)
                
                st.subheader("📈 إحصائيات البيانات")
                if datasets:
                    total_rows = sum(d.row_count for d in datasets)
                    avg_rows = total_rows / len(datasets)
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("إجمالي الصفوف", f"{total_rows:,}")
                    with col2:
                        st.metric("متوسط الصفوف", f"{avg_rows:,.0f}")
                    with col3:
                        st.metric("أكبر ملف", f"{max(d.row_count for d in datasets):,} صف")
            else:
                st.info("لا توجد بيانات مرفوعة بعد")
        
        with admin_tabs[2]:
            st.subheader("سجل المحادثات")
            chats = get_chat_history(db, limit=100)
            if chats:
                for chat in chats[:20]:
                    with st.expander(f"💬 {chat.user_message[:50]}..." if len(chat.user_message) > 50 else f"💬 {chat.user_message}"):
                        st.write(f"**السؤال:** {chat.user_message}")
                        st.write(f"**الإجابة:** {chat.ai_response}")
                        st.caption(f"التاريخ: {chat.timestamp.strftime('%Y-%m-%d %H:%M') if chat.timestamp else '-'}")
            else:
                st.info("لا توجد محادثات بعد")
    
    finally:
        db.close()


def show_dashboard():
    limits = get_user_limits()
    
    with st.sidebar:
        st.markdown('<div class="sidebar-header">🔮 DataVision Pro</div>', unsafe_allow_html=True)
        
        if st.session_state.user:
            user = st.session_state.user
            badge_class = "badge-premium" if user.subscription_type == "premium" else "badge-free"
            badge_text = "💎 احترافي" if user.subscription_type == "premium" else "🆓 مجاني"
            
            st.markdown(f"""
            <div class="user-badge">
                <div style="font-size: 1.2rem; font-weight: 600; color: #fff;">👤 {user.full_name or user.username}</div>
                <div style="margin-top: 0.5rem;"><span class="{badge_class}">{badge_text}</span></div>
            </div>
            """, unsafe_allow_html=True)
            
            if user.is_admin:
                if st.button("⚙️ لوحة الأدمن", use_container_width=True):
                    st.session_state.page = 'admin'
                    st.rerun()
            
            if user.subscription_type != "premium":
                if st.button("💎 ترقية الحساب", use_container_width=True):
                    st.session_state.page = 'pricing'
                    st.rerun()
            
            if st.button("🚪 تسجيل الخروج", use_container_width=True):
                st.session_state.user = None
                st.session_state.page = 'home'
                st.session_state.df = None
                st.session_state.df_cleaned = None
                st.rerun()
        
        st.markdown("---")
        st.header("📤 رفع البيانات")
        
        uploaded_file = st.file_uploader(
            "اختر ملف CSV أو Excel",
            type=['csv', 'xlsx', 'xls'],
            help="قم برفع ملف البيانات الخاص بك"
        )
        
        if uploaded_file:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            
            if file_size_mb > limits['max_file_size_mb']:
                st.error(f"حجم الملف ({file_size_mb:.1f} MB) يتجاوز الحد المسموح ({limits['max_file_size_mb']} MB)")
            else:
                st.success(f"تم رفع: {uploaded_file.name}")
                
                st.subheader("📅 معلومات الفترة")
                col1, col2 = st.columns(2)
                with col1:
                    period_month = st.selectbox("الشهر", range(1, 13), index=datetime.now().month - 1)
                with col2:
                    period_year = st.selectbox("السنة", range(2020, 2030), index=datetime.now().year - 2020)
                
                dataset_name = st.text_input("اسم المجموعة", value=uploaded_file.name.split('.')[0])
                
                if st.button("🚀 بدء التحليل", type="primary", use_container_width=True):
                    with st.spinner("جاري تحميل وتحليل البيانات..."):
                        df = load_file(uploaded_file)
                        
                        if df is not None:
                            if len(df) > limits['max_rows']:
                                st.error(f"عدد الصفوف ({len(df):,}) يتجاوز الحد المسموح ({limits['max_rows']:,})")
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
                                        summary_stats=analysis_results.get('numeric_summary', {})
                                    )
                                    st.session_state.current_dataset_id = record.id
                                    
                                    similar = find_similar_datasets(db, columns_info)
                                    similar = [s for s in similar if s['record'].id != record.id]
                                    st.session_state.similar_datasets = similar
                                    
                                    if st.session_state.user:
                                        increment_analysis_count(db, st.session_state.user.id)
                                finally:
                                    db.close()
                                
                                st.success("تم التحليل بنجاح!")
                                st.rerun()
        
        if st.session_state.df is not None:
            st.markdown("---")
            st.subheader("📊 معلومات البيانات")
            st.write(f"**الصفوف:** {len(st.session_state.df):,}")
            st.write(f"**الأعمدة:** {len(st.session_state.df.columns)}")
            
            if st.session_state.df_cleaned is not None:
                quality = get_data_quality_score(st.session_state.df_cleaned)
                st.metric("جودة البيانات", f"{quality['overall_score']}%")
    
    st.markdown('<h1 class="glow-text">🔮 DataVision Pro</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">نظام تحليل البيانات الذكي - تحليل احترافي بقوة الذكاء الاصطناعي</p>', unsafe_allow_html=True)
    
    if st.session_state.df is not None:
        tabs = st.tabs([
            "📋 نظرة عامة",
            "🧹 التنظيف", 
            "📈 التحليل",
            "📊 الرسومات",
            "🔄 التنبؤات",
            "💬 المحادثة",
            "📝 التقرير"
        ])
        
        with tabs[0]:
            st.header("📋 نظرة عامة على البيانات")
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("عدد الصفوف", f"{len(st.session_state.df):,}")
            with col2:
                st.metric("عدد الأعمدة", len(st.session_state.df.columns))
            with col3:
                if st.session_state.df_cleaned is not None:
                    quality = get_data_quality_score(st.session_state.df_cleaned)
                    st.metric("جودة البيانات", f"{quality['overall_score']}%")
            with col4:
                missing_pct = (st.session_state.df.isnull().sum().sum() / st.session_state.df.size) * 100
                st.metric("القيم المفقودة", f"{missing_pct:.1f}%")
            
            st.subheader("عينة من البيانات")
            st.dataframe(st.session_state.df.head(10), use_container_width=True)
            
            st.subheader("أنواع الأعمدة")
            col_types = detect_column_types(st.session_state.df)
            col_types_df = pd.DataFrame({
                'العمود': list(col_types.keys()),
                'النوع': list(col_types.values())
            })
            st.dataframe(col_types_df, use_container_width=True)
        
        with tabs[1]:
            st.header("🧹 تنظيف البيانات")
            
            if st.session_state.cleaning_report:
                report = st.session_state.cleaning_report
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("الصفوف الأصلية", f"{report['original_rows']:,}")
                with col2:
                    st.metric("الصفوف بعد التنظيف", f"{report['final_rows']:,}")
                with col3:
                    st.metric("الصفوف المحذوفة", report['rows_removed'])
                
                if report['changes']:
                    st.subheader("التغييرات التي تمت")
                    for change in report['changes']:
                        st.markdown(f'<div class="success-box">✅ {change}</div>', unsafe_allow_html=True)
                else:
                    st.success("البيانات نظيفة!")
                
                st.subheader("جودة البيانات")
                if st.session_state.df_cleaned is not None:
                    quality = get_data_quality_score(st.session_state.df_cleaned)
                    
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("الاكتمال", f"{quality['completeness']}%")
                    with col2:
                        st.metric("التفرد", f"{quality['uniqueness']}%")
                    with col3:
                        st.metric("الجودة الإجمالية", f"{quality['overall_score']}%")
                
                missing_chart = create_missing_values_chart(st.session_state.df)
                if missing_chart:
                    st.plotly_chart(missing_chart, use_container_width=True)
        
        with tabs[2]:
            st.header("📈 التحليل الإحصائي")
            
            df_analysis = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
            
            st.subheader("الإحصاءات الوصفية")
            numeric_stats = get_numeric_stats(df_analysis)
            if not numeric_stats.empty:
                st.dataframe(numeric_stats, use_container_width=True)
            else:
                st.info("لا توجد أعمدة رقمية")
            
            st.subheader("إحصاءات الأعمدة الفئوية")
            cat_stats = get_categorical_stats(df_analysis)
            if cat_stats:
                for col, stats in cat_stats.items():
                    with st.expander(f"📁 {col}"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**القيم الفريدة:** {stats['unique_count']}")
                            st.write(f"**الأكثر تكراراً:** {stats['most_common']}")
                        with col2:
                            st.write(f"**الأقل تكراراً:** {stats['least_common']}")
                            st.write(f"**القيم المفقودة:** {stats['missing']}")
            
            st.subheader("الارتباطات القوية")
            correlations = find_strong_correlations(df_analysis)
            if correlations:
                for corr in correlations[:5]:
                    emoji = "🟢" if corr['correlation'] > 0 else "🔴"
                    st.markdown(f"{emoji} **{corr['column1']}** و **{corr['column2']}**: {corr['correlation']:.3f}")
            else:
                st.info("لا توجد ارتباطات قوية")
            
            st.subheader("القيم الشاذة")
            outliers = detect_outliers(df_analysis)
            if outliers:
                for col, info in outliers.items():
                    st.markdown(f'<div class="warning-box">⚠️ **{col}**: {info["count"]} قيمة شاذة ({info["percentage"]}%)</div>', unsafe_allow_html=True)
            else:
                st.success("لا توجد قيم شاذة")
        
        with tabs[3]:
            st.header("📊 الرسومات البيانية")
            
            df_viz = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
            numeric_cols = df_viz.select_dtypes(include=[np.number]).columns.tolist()
            categorical_cols = df_viz.select_dtypes(include=['object']).columns.tolist()
            
            st.subheader("نظرة عامة على التوزيعات")
            dist_overview = create_distribution_overview(df_viz)
            if dist_overview:
                st.plotly_chart(dist_overview, use_container_width=True)
            
            corr_heatmap = create_correlation_heatmap(df_viz)
            if corr_heatmap:
                st.plotly_chart(corr_heatmap, use_container_width=True)
            
            st.subheader("رسومات مخصصة")
            chart_type = st.selectbox(
                "نوع الرسم",
                ["أعمدة", "مبعثر", "صندوقي", "دائري", "خطي", "توزيع"]
            )
            
            col1, col2 = st.columns(2)
            
            if chart_type == "أعمدة" and categorical_cols:
                with col1:
                    x_col = st.selectbox("العمود", categorical_cols, key="bar_x")
                with col2:
                    y_col = st.selectbox("القيمة", numeric_cols if numeric_cols else [None], key="bar_y")
                if x_col:
                    fig = create_bar_chart(df_viz, x_col, y_col)
                    if fig:
                        st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "مبعثر" and len(numeric_cols) >= 2:
                with col1:
                    x_col = st.selectbox("المحور X", numeric_cols, key="scatter_x")
                with col2:
                    y_col = st.selectbox("المحور Y", numeric_cols, key="scatter_y", index=1 if len(numeric_cols) > 1 else 0)
                fig = create_scatter_plot(df_viz, x_col, y_col)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "صندوقي" and numeric_cols:
                with col1:
                    y_col = st.selectbox("العمود الرقمي", numeric_cols, key="box_y")
                with col2:
                    x_col = st.selectbox("التجميع حسب", [None] + categorical_cols, key="box_x")
                fig = create_box_plot(df_viz, y_col, x_col)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "دائري" and categorical_cols:
                with col1:
                    col_select = st.selectbox("العمود", categorical_cols, key="pie_col")
                fig = create_pie_chart(df_viz, col_select)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "خطي" and numeric_cols:
                with col1:
                    x_col = st.selectbox("المحور X", df_viz.columns.tolist(), key="line_x")
                with col2:
                    y_col = st.selectbox("المحور Y", numeric_cols, key="line_y")
                fig = create_line_chart(df_viz, x_col, y_col)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "توزيع" and numeric_cols:
                with col1:
                    col_select = st.selectbox("العمود", numeric_cols, key="hist_col")
                fig = create_histogram(df_viz, col_select)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
        
        with tabs[4]:
            st.header("🔄 المقارنة والتنبؤات")
            
            if not limits['predictions_enabled']:
                st.markdown("""
                <div class="neon-card">
                    <h3 style="text-align: center;">💎 ميزة احترافية</h3>
                    <p style="text-align: center; color: #a0a0b0;">
                        التنبؤات والمقارنات المتقدمة متاحة فقط للمشتركين في الباقة الاحترافية
                    </p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("💎 ترقية الآن", use_container_width=True, key="upgrade_pred"):
                    st.session_state.page = 'pricing'
                    st.rerun()
            else:
                df_pred = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
                numeric_cols = df_pred.select_dtypes(include=[np.number]).columns.tolist()
                
                if st.session_state.similar_datasets:
                    st.subheader("📊 مقارنة مع البيانات السابقة")
                    st.info(f"تم اكتشاف {len(st.session_state.similar_datasets)} مجموعة بيانات مشابهة")
                    
                    for similar in st.session_state.similar_datasets[:3]:
                        record = similar['record']
                        with st.expander(f"📁 {record.dataset_name} ({record.period_month}/{record.period_year})"):
                            st.write(f"**التشابه:** {similar['similarity']*100:.1f}%")
                            st.write(f"**الصفوف:** {record.row_count:,}")
                            if record.summary_stats:
                                st.json(record.summary_stats)
                
                st.subheader("📈 التنبؤات")
                if numeric_cols:
                    col1, col2 = st.columns(2)
                    with col1:
                        target_col = st.selectbox("العمود المستهدف", numeric_cols, key="pred_target")
                    with col2:
                        periods = st.slider("عدد الفترات", 1, 12, 6)
                    
                    if st.button("🔮 توليد التنبؤات", use_container_width=True):
                        with st.spinner("جاري التنبؤ..."):
                            forecast = simple_forecast(df_pred, target_col, periods)
                            if forecast is not None:
                                trend_chart = create_trend_chart(df_pred, target_col, forecast)
                                if trend_chart:
                                    st.plotly_chart(trend_chart, use_container_width=True)
                                
                                trend_analysis = analyze_trend(df_pred, target_col)
                                if trend_analysis:
                                    st.markdown(f'<div class="insight-box">📈 **تحليل الاتجاه:** {trend_analysis}</div>', unsafe_allow_html=True)
        
        with tabs[5]:
            st.header("💬 المحادثة الذكية")
            
            if not limits['ai_chat_enabled']:
                st.markdown("""
                <div class="neon-card">
                    <h3 style="text-align: center;">💎 ميزة احترافية</h3>
                    <p style="text-align: center; color: #a0a0b0;">
                        المحادثة مع الذكاء الاصطناعي متاحة فقط للمشتركين في الباقة الاحترافية
                    </p>
                </div>
                """, unsafe_allow_html=True)
                if st.button("💎 ترقية الآن", use_container_width=True, key="upgrade_chat"):
                    st.session_state.page = 'pricing'
                    st.rerun()
            else:
                st.markdown("اسأل أي سؤال عن بياناتك وسيجيبك الذكاء الاصطناعي")
                
                for msg in st.session_state.chat_messages:
                    with st.chat_message(msg["role"]):
                        st.write(msg["content"])
                
                if prompt := st.chat_input("اكتب سؤالك هنا..."):
                    st.session_state.chat_messages.append({"role": "user", "content": prompt})
                    
                    with st.chat_message("user"):
                        st.write(prompt)
                    
                    with st.chat_message("assistant"):
                        with st.spinner("جاري التفكير..."):
                            df_chat = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
                            response = chat_about_data(df_chat, prompt)
                            st.write(response)
                            st.session_state.chat_messages.append({"role": "assistant", "content": response})
                            
                            db = get_db()
                            try:
                                save_chat_message(db, st.session_state.current_dataset_id, prompt, response)
                            finally:
                                db.close()
        
        with tabs[6]:
            st.header("📝 التقرير الشامل")
            
            df_report = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
            
            st.subheader("ملخص البيانات")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("الصفوف", f"{len(df_report):,}")
            with col2:
                st.metric("الأعمدة", len(df_report.columns))
            with col3:
                quality = get_data_quality_score(df_report)
                st.metric("الجودة", f"{quality['overall_score']}%")
            with col4:
                st.metric("الأعمدة الرقمية", len(df_report.select_dtypes(include=[np.number]).columns))
            
            if st.session_state.analysis_results:
                st.subheader("نتائج التحليل")
                results = st.session_state.analysis_results
                
                if 'numeric_summary' in results and results['numeric_summary']:
                    st.markdown("**الإحصاءات الرقمية:**")
                    st.json(results['numeric_summary'])
            
            if limits['ai_chat_enabled']:
                st.subheader("🤖 رؤى الذكاء الاصطناعي")
                if st.button("توليد الرؤى والتوصيات", use_container_width=True):
                    with st.spinner("جاري تحليل البيانات بالذكاء الاصطناعي..."):
                        insights = generate_data_insights(df_report)
                        st.session_state.ai_insights = insights
                        st.markdown(f'<div class="insight-box">{insights}</div>', unsafe_allow_html=True)
                
                if st.session_state.ai_insights:
                    st.markdown(f'<div class="insight-box">{st.session_state.ai_insights}</div>', unsafe_allow_html=True)
    
    else:
        st.markdown("""
        <div class="neon-card" style="text-align: center; padding: 3rem;">
            <h2 style="margin-bottom: 1rem;">🚀 ابدأ الآن</h2>
            <p style="color: #a0a0b0; font-size: 1.1rem;">
                ارفع ملف بياناتك من القائمة الجانبية للبدء في التحليل الذكي
            </p>
            <p style="color: #a0a0b0;">
                ندعم ملفات CSV و Excel
            </p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class="neon-card">
                <h3>🧹 تنظيف ذكي</h3>
                <p style="color: #a0a0b0;">
                    تنظيف تلقائي للبيانات مع إزالة التكرارات ومعالجة القيم المفقودة
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class="neon-card">
                <h3>📊 تحليل شامل</h3>
                <p style="color: #a0a0b0;">
                    تحليل إحصائي متكامل مع رسومات بيانية تفاعلية
                </p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class="neon-card">
                <h3>🤖 ذكاء اصطناعي</h3>
                <p style="color: #a0a0b0;">
                    تحدث مع بياناتك واحصل على رؤى وتوصيات ذكية
                </p>
            </div>
            """, unsafe_allow_html=True)


def show_home_page():
    st.markdown('<h1 class="glow-text">🔮 DataVision Pro</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-title">نظام تحليل البيانات الذكي - حلل بياناتك بقوة الذكاء الاصطناعي</p>', unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        bcol1, bcol2 = st.columns(2)
        with bcol1:
            if st.button("🔐 تسجيل الدخول", use_container_width=True):
                st.session_state.page = 'login'
                st.rerun()
        with bcol2:
            if st.button("📝 إنشاء حساب", use_container_width=True):
                st.session_state.page = 'register'
                st.rerun()
        
        if st.button("🚀 جرب بدون حساب", use_container_width=True, type="primary"):
            st.session_state.page = 'dashboard'
            st.rerun()
    
    st.markdown("---")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">🧹</div>
            <div class="metric-label">تنظيف تلقائي</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">📊</div>
            <div class="metric-label">تحليل شامل</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">🤖</div>
            <div class="metric-label">ذكاء اصطناعي</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-value">🔮</div>
            <div class="metric-label">تنبؤات ذكية</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    show_pricing_page()


with st.sidebar:
    if st.session_state.page not in ['home', 'login', 'register', 'pricing']:
        pass
    else:
        st.markdown('<div class="sidebar-header">🔮 DataVision Pro</div>', unsafe_allow_html=True)
        
        if st.button("🏠 الرئيسية", use_container_width=True):
            st.session_state.page = 'home'
            st.rerun()
        
        if st.button("🔐 دخول", use_container_width=True):
            st.session_state.page = 'login'
            st.rerun()
        
        if st.button("📝 تسجيل", use_container_width=True):
            st.session_state.page = 'register'
            st.rerun()
        
        if st.button("💎 الأسعار", use_container_width=True):
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
    if st.session_state.user and st.session_state.user.is_admin:
        show_admin_panel()
    else:
        st.error("ليس لديك صلاحية الوصول")
        st.session_state.page = 'dashboard'
        st.rerun()
elif st.session_state.page == 'dashboard':
    show_dashboard()
else:
    show_home_page()
