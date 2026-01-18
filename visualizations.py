import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from typing import List, Optional


def create_histogram(df: pd.DataFrame, column: str, title: str = None) -> go.Figure:
    """Create a histogram for a numeric column"""
    fig = px.histogram(
        df, 
        x=column, 
        title=title or f"توزيع {column}",
        labels={column: column, 'count': 'التكرار'},
        color_discrete_sequence=['#3498db']
    )
    fig.update_layout(
        xaxis_title=column,
        yaxis_title="التكرار",
        template="plotly_white",
        font=dict(size=12)
    )
    return fig


def create_bar_chart(df: pd.DataFrame, column: str, title: str = None, top_n: int = 10) -> go.Figure:
    """Create a bar chart for categorical data"""
    value_counts = df[column].value_counts().head(top_n)
    
    fig = px.bar(
        x=value_counts.index,
        y=value_counts.values,
        title=title or f"توزيع {column}",
        labels={'x': column, 'y': 'التكرار'},
        color_discrete_sequence=['#2ecc71']
    )
    fig.update_layout(
        xaxis_title=column,
        yaxis_title="التكرار",
        template="plotly_white",
        font=dict(size=12)
    )
    return fig


def create_box_plot(df: pd.DataFrame, columns: List[str] = None, title: str = None) -> go.Figure:
    """Create box plots for numeric columns"""
    if columns is None:
        columns = df.select_dtypes(include=[np.number]).columns.tolist()[:5]
    
    fig = go.Figure()
    colors = ['#3498db', '#e74c3c', '#2ecc71', '#9b59b6', '#f39c12']
    
    for i, col in enumerate(columns):
        fig.add_trace(go.Box(
            y=df[col],
            name=col,
            marker_color=colors[i % len(colors)]
        ))
    
    fig.update_layout(
        title=title or "الرسم الصندوقي للأعمدة الرقمية",
        template="plotly_white",
        font=dict(size=12),
        showlegend=True
    )
    return fig


def create_scatter_plot(df: pd.DataFrame, x_col: str, y_col: str, 
                        color_col: str = None, title: str = None) -> go.Figure:
    """Create a scatter plot"""
    fig = px.scatter(
        df,
        x=x_col,
        y=y_col,
        color=color_col,
        title=title or f"العلاقة بين {x_col} و {y_col}",
        labels={x_col: x_col, y_col: y_col},
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig.update_layout(
        template="plotly_white",
        font=dict(size=12)
    )
    return fig


def create_correlation_heatmap(df: pd.DataFrame, title: str = None) -> go.Figure:
    """Create a correlation heatmap"""
    numeric_df = df.select_dtypes(include=[np.number])
    
    if numeric_df.empty or len(numeric_df.columns) < 2:
        return None
    
    corr_matrix = numeric_df.corr()
    
    fig = px.imshow(
        corr_matrix,
        title=title or "خريطة الارتباط الحرارية",
        color_continuous_scale='RdBu_r',
        aspect='auto',
        text_auto='.2f'
    )
    fig.update_layout(
        template="plotly_white",
        font=dict(size=12)
    )
    return fig


def create_line_chart(df: pd.DataFrame, x_col: str, y_col: str, 
                      title: str = None) -> go.Figure:
    """Create a line chart"""
    fig = px.line(
        df,
        x=x_col,
        y=y_col,
        title=title or f"تغير {y_col} عبر {x_col}",
        markers=True
    )
    fig.update_layout(
        template="plotly_white",
        font=dict(size=12)
    )
    return fig


def create_pie_chart(df: pd.DataFrame, column: str, title: str = None, 
                     top_n: int = 8) -> go.Figure:
    """Create a pie chart for categorical data"""
    value_counts = df[column].value_counts().head(top_n)
    
    fig = px.pie(
        values=value_counts.values,
        names=value_counts.index,
        title=title or f"نسب توزيع {column}",
        color_discrete_sequence=px.colors.qualitative.Set3
    )
    fig.update_layout(
        template="plotly_white",
        font=dict(size=12)
    )
    return fig


def create_missing_values_chart(df: pd.DataFrame, title: str = None) -> go.Figure:
    """Create a chart showing missing values per column"""
    missing = df.isnull().sum()
    missing = missing[missing > 0].sort_values(ascending=True)
    
    if missing.empty:
        return None
    
    missing_pct = (missing / len(df)) * 100
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=missing.values,
        y=missing.index,
        orientation='h',
        marker_color='#e74c3c',
        text=[f"{pct:.1f}%" for pct in missing_pct],
        textposition='outside'
    ))
    
    fig.update_layout(
        title=title or "القيم المفقودة في كل عمود",
        xaxis_title="عدد القيم المفقودة",
        yaxis_title="العمود",
        template="plotly_white",
        font=dict(size=12),
        height=max(400, len(missing) * 30)
    )
    return fig


def create_distribution_overview(df: pd.DataFrame) -> go.Figure:
    """Create distribution overview for all numeric columns"""
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    
    if not numeric_cols:
        return None
    
    n_cols = min(len(numeric_cols), 6)
    n_rows = (n_cols + 2) // 3
    
    fig = make_subplots(
        rows=n_rows, 
        cols=3,
        subplot_titles=numeric_cols[:6]
    )
    
    for i, col in enumerate(numeric_cols[:6]):
        row = i // 3 + 1
        col_idx = i % 3 + 1
        
        fig.add_trace(
            go.Histogram(x=df[col], name=col, showlegend=False),
            row=row, col=col_idx
        )
    
    fig.update_layout(
        title="نظرة عامة على توزيعات الأعمدة الرقمية",
        template="plotly_white",
        height=300 * n_rows,
        font=dict(size=10)
    )
    return fig


def create_comparison_chart(df1: pd.DataFrame, df2: pd.DataFrame, 
                           column: str, labels: tuple = ("الفترة الأولى", "الفترة الثانية")) -> go.Figure:
    """Create comparison chart between two periods"""
    fig = go.Figure()
    
    fig.add_trace(go.Box(
        y=df1[column],
        name=labels[0],
        marker_color='#3498db'
    ))
    
    fig.add_trace(go.Box(
        y=df2[column],
        name=labels[1],
        marker_color='#e74c3c'
    ))
    
    fig.update_layout(
        title=f"مقارنة {column} بين الفترتين",
        template="plotly_white",
        font=dict(size=12)
    )
    return fig


def create_trend_chart(values: List[float], labels: List[str], 
                       title: str, predictions: List[float] = None) -> go.Figure:
    """Create trend chart with optional predictions"""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=labels,
        y=values,
        mode='lines+markers',
        name='القيم الفعلية',
        line=dict(color='#3498db', width=2),
        marker=dict(size=8)
    ))
    
    if predictions:
        pred_labels = [f"توقع {i+1}" for i in range(len(predictions))]
        all_labels = labels + pred_labels
        
        fig.add_trace(go.Scatter(
            x=pred_labels,
            y=predictions,
            mode='lines+markers',
            name='التنبؤات',
            line=dict(color='#e74c3c', width=2, dash='dash'),
            marker=dict(size=8)
        ))
    
    fig.update_layout(
        title=title,
        template="plotly_white",
        font=dict(size=12),
        xaxis_title="الفترة",
        yaxis_title="القيمة"
    )
    return fig


def create_categorical_distribution(df: pd.DataFrame, column: str, title: str = None) -> go.Figure:
    """Create a pie chart for categorical distribution"""
    value_counts = df[column].value_counts()
    
    colors = ['#a855f7', '#ec4899', '#3b82f6', '#06b6d4', '#22c55e', '#f59e0b', '#ef4444', '#8b5cf6']
    
    fig = go.Figure(data=[go.Pie(
        labels=value_counts.index.tolist(),
        values=value_counts.values.tolist(),
        hole=0.4,
        marker_colors=colors[:len(value_counts)],
        textinfo='label+percent',
        textposition='outside'
    )])
    
    fig.update_layout(
        title=title or f"Distribution of {column}",
        template="plotly_white",
        font=dict(size=12),
        showlegend=True
    )
    return fig


def create_categorical_bar_chart(df: pd.DataFrame, column: str, title: str = None) -> go.Figure:
    """Create a horizontal bar chart for categorical data"""
    value_counts = df[column].value_counts().sort_values(ascending=True)
    
    fig = go.Figure(go.Bar(
        x=value_counts.values,
        y=value_counts.index,
        orientation='h',
        marker=dict(
            color=value_counts.values,
            colorscale='Viridis',
            showscale=True
        ),
        text=value_counts.values,
        textposition='outside'
    ))
    
    fig.update_layout(
        title=title or f"Distribution of {column}",
        template="plotly_white",
        font=dict(size=12),
        xaxis_title="Count",
        yaxis_title=column,
        height=max(400, len(value_counts) * 30)
    )
    return fig


def create_cluster_scatter(df: pd.DataFrame, x_col: str, y_col: str, 
                          cluster_labels: list, title: str = None) -> go.Figure:
    """Create scatter plot colored by cluster"""
    df_plot = df[[x_col, y_col]].copy()
    df_plot['Cluster'] = cluster_labels
    
    colors = ['#a855f7', '#ec4899', '#3b82f6', '#22c55e', '#f59e0b', '#ef4444']
    
    fig = go.Figure()
    
    for i, cluster in enumerate(sorted(df_plot['Cluster'].unique())):
        mask = df_plot['Cluster'] == cluster
        fig.add_trace(go.Scatter(
            x=df_plot.loc[mask, x_col],
            y=df_plot.loc[mask, y_col],
            mode='markers',
            name=f'Cluster {cluster + 1}',
            marker=dict(
                color=colors[i % len(colors)],
                size=8,
                opacity=0.7
            )
        ))
    
    fig.update_layout(
        title=title or f"Customer Clusters: {x_col} vs {y_col}",
        template="plotly_white",
        font=dict(size=12),
        xaxis_title=x_col,
        yaxis_title=y_col
    )
    return fig


def create_feature_importance_chart(feature_importance: dict, title: str = None) -> go.Figure:
    """Create horizontal bar chart for feature importance"""
    sorted_features = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))
    
    fig = go.Figure(go.Bar(
        x=list(sorted_features.values()),
        y=list(sorted_features.keys()),
        orientation='h',
        marker=dict(
            color=list(sorted_features.values()),
            colorscale='Purples',
            showscale=False
        ),
        text=[f"{v:.1f}%" for v in sorted_features.values()],
        textposition='outside'
    ))
    
    fig.update_layout(
        title=title or "Feature Importance",
        template="plotly_white",
        font=dict(size=12),
        xaxis_title="Importance (%)",
        yaxis_title="Feature",
        height=max(400, len(sorted_features) * 35)
    )
    return fig


def create_outlier_visualization(df: pd.DataFrame, column: str, 
                                 outliers_info: dict) -> go.Figure:
    """Create box plot with outliers highlighted"""
    fig = go.Figure()
    
    fig.add_trace(go.Box(
        y=df[column],
        name=column,
        marker_color='#a855f7',
        boxpoints='outliers',
        jitter=0.3,
        pointpos=-1.8
    ))
    
    if outliers_info:
        lower = outliers_info.get('lower_bound', df[column].min())
        upper = outliers_info.get('upper_bound', df[column].max())
        
        fig.add_hline(y=lower, line_dash="dash", line_color="red", 
                     annotation_text=f"Lower Bound: {lower:.2f}")
        fig.add_hline(y=upper, line_dash="dash", line_color="red",
                     annotation_text=f"Upper Bound: {upper:.2f}")
    
    fig.update_layout(
        title=f"Outlier Analysis: {column}",
        template="plotly_white",
        font=dict(size=12),
        yaxis_title=column
    )
    return fig
