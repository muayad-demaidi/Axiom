import streamlit as st
import pandas as pd
import numpy as np
import hashlib
from datetime import datetime
import io

from models import init_db, get_db, save_dataset_record, find_similar_datasets, get_datasets_by_name, save_chat_message, get_chat_history
from data_cleaner import clean_data, detect_column_types, get_data_quality_score
from data_analyzer import get_basic_stats, get_numeric_stats, get_categorical_stats, get_correlation_matrix, find_strong_correlations, detect_outliers, generate_summary_report
from visualizations import (create_histogram, create_bar_chart, create_box_plot, 
                           create_scatter_plot, create_correlation_heatmap, create_line_chart,
                           create_pie_chart, create_missing_values_chart,
                           create_distribution_overview, create_comparison_chart, create_trend_chart)
from predictions import compare_datasets, simple_forecast, analyze_trend, predict_column, calculate_growth_metrics
from ai_assistant import generate_data_insights, chat_about_data, generate_comparison_insights, generate_prediction_insights

st.set_page_config(
    page_title="نظام تحليل البيانات الذكي",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        color: #1e3a5f;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.2rem;
        text-align: center;
        color: #5a6c7d;
        margin-bottom: 2rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .insight-box {
        background-color: #f0f7ff;
        border-right: 4px solid #3498db;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
    .warning-box {
        background-color: #fff5f5;
        border-right: 4px solid #e74c3c;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
    .success-box {
        background-color: #f0fff4;
        border-right: 4px solid #2ecc71;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 5px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        padding: 10px 20px;
    }
</style>
""", unsafe_allow_html=True)

init_db()

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


def calculate_data_hash(df):
    """Calculate hash of dataframe for identifying similar data"""
    columns_str = '_'.join(sorted(df.columns.tolist()))
    return hashlib.md5(columns_str.encode()).hexdigest()


def load_file(uploaded_file):
    """Load CSV or Excel file"""
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


st.markdown('<h1 class="main-header">نظام تحليل البيانات الذكي</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">تحليل شامل لبياناتك بضغطة زر واحدة مع توصيات مدعومة بالذكاء الاصطناعي</p>', unsafe_allow_html=True)

with st.sidebar:
    st.header("📤 رفع البيانات")
    
    uploaded_file = st.file_uploader(
        "اختر ملف CSV أو Excel",
        type=['csv', 'xlsx', 'xls'],
        help="قم برفع ملف البيانات الخاص بك"
    )
    
    if uploaded_file:
        st.success(f"تم رفع: {uploaded_file.name}")
        
        st.subheader("📅 معلومات الفترة الزمنية")
        col1, col2 = st.columns(2)
        with col1:
            period_month = st.selectbox("الشهر", range(1, 13), index=datetime.now().month - 1)
        with col2:
            period_year = st.selectbox("السنة", range(2020, 2030), index=datetime.now().year - 2020)
        
        dataset_name = st.text_input("اسم مجموعة البيانات", value=uploaded_file.name.split('.')[0])
        
        if st.button("🚀 بدء التحليل", type="primary", use_container_width=True):
            with st.spinner("جاري تحميل وتحليل البيانات..."):
                df = load_file(uploaded_file)
                
                if df is not None:
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
                    finally:
                        db.close()
                    
                    st.success("تم التحليل بنجاح!")
                    st.rerun()

    if st.session_state.df is not None:
        st.divider()
        st.subheader("📊 معلومات البيانات")
        st.write(f"**الصفوف:** {len(st.session_state.df)}")
        st.write(f"**الأعمدة:** {len(st.session_state.df.columns)}")
        
        quality = get_data_quality_score(st.session_state.df)
        st.metric("جودة البيانات", f"{quality['overall_score']}%")

if st.session_state.df is not None:
    tabs = st.tabs([
        "📋 نظرة عامة",
        "🧹 تنظيف البيانات", 
        "📈 التحليل الإحصائي",
        "📊 الرسومات البيانية",
        "🔄 المقارنة والتنبؤات",
        "💬 المحادثة الذكية",
        "📝 التقرير الشامل"
    ])
    
    with tabs[0]:
        st.header("📋 نظرة عامة على البيانات")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("عدد الصفوف", len(st.session_state.df))
        with col2:
            st.metric("عدد الأعمدة", len(st.session_state.df.columns))
        with col3:
            quality = get_data_quality_score(st.session_state.df)
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
                st.metric("الصفوف الأصلية", report['original_rows'])
            with col2:
                st.metric("الصفوف بعد التنظيف", report['final_rows'])
            with col3:
                st.metric("الصفوف المحذوفة", report['rows_removed'])
            
            if report['changes']:
                st.subheader("التغييرات التي تمت")
                for change in report['changes']:
                    st.markdown(f'<div class="success-box">✅ {change}</div>', unsafe_allow_html=True)
            else:
                st.success("البيانات نظيفة ولا تحتاج إلى تعديلات!")
            
            st.subheader("جودة البيانات")
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
        
        st.subheader("الإحصاءات الوصفية للأعمدة الرقمية")
        numeric_stats = get_numeric_stats(df_analysis)
        if not numeric_stats.empty:
            st.dataframe(numeric_stats, use_container_width=True)
        else:
            st.info("لا توجد أعمدة رقمية في البيانات")
        
        st.subheader("إحصاءات الأعمدة الفئوية")
        cat_stats = get_categorical_stats(df_analysis)
        if cat_stats:
            for col, stats in cat_stats.items():
                with st.expander(f"📁 {col}"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.write(f"**القيم الفريدة:** {stats['unique_count']}")
                        st.write(f"**الأكثر تكراراً:** {stats['most_common']} ({stats['most_common_count']} مرة)")
                    with col2:
                        st.write(f"**الأقل تكراراً:** {stats['least_common']} ({stats['least_common_count']} مرة)")
                        st.write(f"**القيم المفقودة:** {stats['missing']}")
        
        st.subheader("الارتباطات القوية")
        correlations = find_strong_correlations(df_analysis)
        if correlations:
            for corr in correlations[:5]:
                corr_type = "🟢" if corr['correlation'] > 0 else "🔴"
                st.markdown(f"{corr_type} **{corr['column1']}** و **{corr['column2']}**: {corr['correlation']:.3f} ({corr['type']})")
        else:
            st.info("لا توجد ارتباطات قوية بين الأعمدة")
        
        st.subheader("القيم الشاذة")
        outliers = detect_outliers(df_analysis)
        if outliers:
            for col, info in outliers.items():
                st.markdown(f'<div class="warning-box">⚠️ العمود **{col}**: {info["count"]} قيمة شاذة ({info["percentage"]}%)</div>', unsafe_allow_html=True)
        else:
            st.success("لم يتم اكتشاف قيم شاذة")
    
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
            st.subheader("خريطة الارتباط الحرارية")
            st.plotly_chart(corr_heatmap, use_container_width=True)
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("رسم بياني مخصص")
            chart_type = st.selectbox("نوع الرسم", ["الأعمدة", "المبعثر", "الصندوقي", "الدائري", "الخطي"])
            
            if chart_type == "الأعمدة" and categorical_cols:
                selected_col = st.selectbox("اختر العمود", categorical_cols, key="bar_col")
                fig = create_bar_chart(df_viz, selected_col)
                st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "المبعثر" and len(numeric_cols) >= 2:
                x_col = st.selectbox("المحور الأفقي", numeric_cols, key="scatter_x")
                y_col = st.selectbox("المحور العمودي", [c for c in numeric_cols if c != x_col], key="scatter_y")
                fig = create_scatter_plot(df_viz, x_col, y_col)
                st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "الصندوقي" and numeric_cols:
                selected_cols = st.multiselect("اختر الأعمدة", numeric_cols, default=numeric_cols[:3], key="box_cols")
                if selected_cols:
                    fig = create_box_plot(df_viz, selected_cols)
                    st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "الدائري" and categorical_cols:
                selected_col = st.selectbox("اختر العمود", categorical_cols, key="pie_col")
                fig = create_pie_chart(df_viz, selected_col)
                st.plotly_chart(fig, use_container_width=True)
            
            elif chart_type == "الخطي" and numeric_cols:
                if len(df_viz.columns) >= 2:
                    x_col = st.selectbox("المحور الأفقي", df_viz.columns.tolist(), key="line_x")
                    y_col = st.selectbox("المحور العمودي", numeric_cols, key="line_y")
                    fig = create_line_chart(df_viz, x_col, y_col)
                    st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("توزيع عمود محدد")
            if numeric_cols:
                hist_col = st.selectbox("اختر عمود رقمي", numeric_cols, key="hist_col")
                fig = create_histogram(df_viz, hist_col)
                st.plotly_chart(fig, use_container_width=True)
    
    with tabs[4]:
        st.header("🔄 المقارنة والتنبؤات")
        
        if st.session_state.similar_datasets:
            st.subheader("📅 مقارنة مع الفترات السابقة")
            st.info(f"تم العثور على {len(st.session_state.similar_datasets)} مجموعة بيانات مشابهة من فترات سابقة")
            
            similar_options = [
                f"{s['record'].dataset_name} - {s['record'].period_month}/{s['record'].period_year} (تشابه: {s['similarity']*100:.0f}%)"
                for s in st.session_state.similar_datasets
            ]
            
            selected_similar = st.selectbox("اختر فترة للمقارنة", similar_options)
            
            if selected_similar:
                selected_idx = similar_options.index(selected_similar)
                selected_record = st.session_state.similar_datasets[selected_idx]['record']
                
                if st.button("🔄 إجراء المقارنة", type="primary"):
                    with st.spinner("جاري المقارنة..."):
                        current_df = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
                        
                        comparison = compare_datasets(
                            pd.DataFrame(selected_record.summary_stats) if selected_record.summary_stats else pd.DataFrame(),
                            current_df,
                            f"{selected_record.period_month}/{selected_record.period_year}",
                            "الفترة الحالية"
                        )
                        
                        st.session_state.comparison_data = comparison
                        
                        if comparison.get('numeric_comparisons'):
                            st.subheader("المقارنة الرقمية")
                            for col, comp in comparison['numeric_comparisons'].items():
                                change_color = "green" if comp.get('mean_change_pct', 0) >= 0 else "red"
                                st.markdown(f"**{col}**: تغير بنسبة :{change_color}[{comp.get('mean_change_pct', 0):.1f}%]")
                        
                        ai_comparison = generate_comparison_insights(comparison)
                        st.markdown("### رؤى الذكاء الاصطناعي")
                        st.markdown(ai_comparison)
        
        st.divider()
        st.subheader("🔮 التنبؤات")
        
        df_pred = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
        numeric_cols = df_pred.select_dtypes(include=[np.number]).columns.tolist()
        
        if numeric_cols:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("#### تنبؤ بسيط")
                pred_col = st.selectbox("اختر عموداً للتنبؤ", numeric_cols, key="simple_pred")
                periods = st.slider("عدد الفترات للتنبؤ", 1, 10, 3)
                
                if st.button("توليد التنبؤ"):
                    values = df_pred[pred_col].dropna().tolist()
                    if len(values) >= 3:
                        forecast = simple_forecast(values[-12:], periods)
                        
                        if 'error' not in forecast:
                            st.success(f"الاتجاه: {forecast['trend']}")
                            st.write(f"**دقة النموذج:** {forecast['confidence']}")
                            st.write(f"**R² Score:** {forecast['r2_score']}")
                            
                            labels = [f"نقطة {i+1}" for i in range(len(values[-6:]))]
                            fig = create_trend_chart(
                                values[-6:], 
                                labels, 
                                f"تنبؤ {pred_col}",
                                forecast['predictions']
                            )
                            st.plotly_chart(fig, use_container_width=True)
                            
                            pred_insights = generate_prediction_insights(forecast)
                            st.markdown("**رؤى التنبؤ:**")
                            st.markdown(pred_insights)
                        else:
                            st.error(forecast['error'])
                    else:
                        st.warning("لا توجد بيانات كافية للتنبؤ")
            
            with col2:
                st.markdown("#### نموذج تنبؤي متقدم")
                target_col = st.selectbox("العمود المستهدف", numeric_cols, key="target_pred")
                feature_cols = st.multiselect(
                    "أعمدة الميزات",
                    [c for c in numeric_cols if c != target_col],
                    default=[c for c in numeric_cols if c != target_col][:3]
                )
                
                if st.button("بناء النموذج"):
                    if feature_cols:
                        result = predict_column(df_pred, target_col, feature_cols)
                        
                        if 'error' not in result:
                            st.success(f"جودة النموذج: {result['model_quality']}")
                            
                            metrics = result['metrics']
                            mcol1, mcol2 = st.columns(2)
                            with mcol1:
                                st.metric("R² Score", f"{metrics['r2_score']:.3f}")
                                st.metric("MAE", f"{metrics['mae']:.3f}")
                            with mcol2:
                                st.metric("RMSE", f"{metrics['rmse']:.3f}")
                            
                            st.markdown("**أهمية الميزات:**")
                            for feat, imp in list(result['feature_importance'].items())[:5]:
                                st.progress(min(imp, 1.0), text=f"{feat}: {imp:.3f}")
                        else:
                            st.error(result['error'])
                    else:
                        st.warning("يرجى اختيار ميزات على الأقل")
    
    with tabs[5]:
        st.header("💬 المحادثة الذكية")
        st.markdown("اسأل أي سؤال عن بياناتك واحصل على إجابات فورية مدعومة بالذكاء الاصطناعي")
        
        df_chat = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
        
        df_info = {
            'row_count': len(df_chat),
            'column_count': len(df_chat.columns),
            'columns': df_chat.columns.tolist(),
            'dtypes': df_chat.dtypes.astype(str).to_dict(),
            'numeric_summary': get_numeric_stats(df_chat).to_dict() if not get_numeric_stats(df_chat).empty else {}
        }
        
        for msg in st.session_state.chat_messages:
            with st.chat_message("user"):
                st.write(msg['user'])
            with st.chat_message("assistant"):
                st.write(msg['assistant'])
        
        user_question = st.chat_input("اكتب سؤالك هنا...")
        
        if user_question:
            with st.chat_message("user"):
                st.write(user_question)
            
            with st.chat_message("assistant"):
                with st.spinner("جاري التفكير..."):
                    response = chat_about_data(
                        user_question, 
                        df_info, 
                        st.session_state.chat_messages
                    )
                    st.write(response)
            
            st.session_state.chat_messages.append({
                'user': user_question,
                'assistant': response
            })
            
            db = get_db()
            try:
                save_chat_message(db, st.session_state.current_dataset_id, user_question, response)
            finally:
                db.close()
        
        st.divider()
        st.subheader("أسئلة مقترحة")
        suggestions = [
            "ما هي أهم الملاحظات في هذه البيانات؟",
            "هل هناك أنماط غير عادية؟",
            "ما هي توقعاتك للفترة القادمة؟",
            "ما هي التوصيات لتحسين الأداء؟"
        ]
        
        cols = st.columns(2)
        for i, suggestion in enumerate(suggestions):
            with cols[i % 2]:
                if st.button(suggestion, key=f"sugg_{i}"):
                    st.session_state.chat_messages.append({
                        'user': suggestion,
                        'assistant': chat_about_data(suggestion, df_info, st.session_state.chat_messages)
                    })
                    st.rerun()
    
    with tabs[6]:
        st.header("📝 التقرير الشامل")
        
        df_report = st.session_state.df_cleaned if st.session_state.df_cleaned is not None else st.session_state.df
        
        if st.button("🤖 توليد تقرير ذكي", type="primary", use_container_width=True):
            with st.spinner("جاري توليد التقرير..."):
                df_summary = get_basic_stats(df_report)
                analysis = st.session_state.analysis_results or generate_summary_report(df_report)
                
                insights = generate_data_insights(df_summary, analysis)
                st.session_state.ai_insights = insights
        
        if st.session_state.ai_insights:
            st.markdown("### 🎯 رؤى وتوصيات الذكاء الاصطناعي")
            st.markdown(st.session_state.ai_insights)
        
        st.divider()
        
        st.markdown("### 📊 ملخص البيانات")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("الصفوف", len(df_report))
        with col2:
            st.metric("الأعمدة", len(df_report.columns))
        with col3:
            quality = get_data_quality_score(df_report)
            st.metric("الجودة", f"{quality['overall_score']}%")
        with col4:
            numeric_count = len(df_report.select_dtypes(include=[np.number]).columns)
            st.metric("أعمدة رقمية", numeric_count)
        
        st.markdown("### 📈 الإحصاءات الرئيسية")
        numeric_stats = get_numeric_stats(df_report)
        if not numeric_stats.empty:
            st.dataframe(numeric_stats[['mean', 'std', 'min', 'max']], use_container_width=True)
        
        st.markdown("### 🔗 الارتباطات المهمة")
        correlations = find_strong_correlations(df_report)
        if correlations:
            for corr in correlations[:3]:
                st.write(f"• {corr['column1']} ↔ {corr['column2']}: {corr['correlation']:.2f}")
        else:
            st.info("لا توجد ارتباطات قوية")
        
        st.markdown("### ⚠️ تنبيهات")
        outliers = detect_outliers(df_report)
        if outliers:
            for col, info in list(outliers.items())[:3]:
                st.warning(f"{col}: {info['count']} قيمة شاذة")
        else:
            st.success("لا توجد تنبيهات")

else:
    st.markdown("""
    <div style="text-align: center; padding: 3rem;">
        <h2>👋 مرحباً بك في نظام تحليل البيانات الذكي</h2>
        <p style="font-size: 1.2rem; color: #666;">
            ابدأ برفع ملف البيانات الخاص بك من القائمة الجانبية
        </p>
        <br>
        <h3>✨ ما يمكنك فعله:</h3>
        <ul style="text-align: right; max-width: 400px; margin: 0 auto;">
            <li>تحليل شامل للبيانات بضغطة زر</li>
            <li>تنظيف البيانات تلقائياً</li>
            <li>رسومات بيانية تفاعلية</li>
            <li>مقارنة بين فترات زمنية مختلفة</li>
            <li>تنبؤات مستقبلية</li>
            <li>محادثة ذكية عن بياناتك</li>
            <li>تقارير احترافية مع توصيات</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
