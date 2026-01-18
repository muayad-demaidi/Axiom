import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error, accuracy_score, classification_report
from sklearn.cluster import KMeans
from sklearn.ensemble import RandomForestClassifier
import warnings
warnings.filterwarnings('ignore')


def compare_datasets(df1: pd.DataFrame, df2: pd.DataFrame, 
                    label1: str = "الفترة الأولى", 
                    label2: str = "الفترة الثانية") -> Dict[str, Any]:
    """Compare two datasets and return comparison statistics"""
    comparison = {
        'row_count_change': len(df2) - len(df1),
        'row_count_change_pct': ((len(df2) - len(df1)) / len(df1)) * 100 if len(df1) > 0 else 0,
        'column_differences': [],
        'numeric_comparisons': {},
        'categorical_comparisons': {}
    }
    
    cols1 = set(df1.columns)
    cols2 = set(df2.columns)
    
    if cols1 != cols2:
        comparison['new_columns'] = list(cols2 - cols1)
        comparison['removed_columns'] = list(cols1 - cols2)
    
    common_cols = cols1.intersection(cols2)
    
    for col in common_cols:
        if df1[col].dtype in ['int64', 'float64'] and df2[col].dtype in ['int64', 'float64']:
            mean1 = df1[col].mean()
            mean2 = df2[col].mean()
            std1 = df1[col].std()
            std2 = df2[col].std()
            
            comparison['numeric_comparisons'][col] = {
                f'{label1}_mean': round(mean1, 2),
                f'{label2}_mean': round(mean2, 2),
                'mean_change': round(mean2 - mean1, 2),
                'mean_change_pct': round(((mean2 - mean1) / mean1) * 100, 2) if mean1 != 0 else 0,
                f'{label1}_std': round(std1, 2),
                f'{label2}_std': round(std2, 2),
                f'{label1}_min': round(df1[col].min(), 2),
                f'{label2}_min': round(df2[col].min(), 2),
                f'{label1}_max': round(df1[col].max(), 2),
                f'{label2}_max': round(df2[col].max(), 2),
            }
        
        elif df1[col].dtype == 'object':
            vc1 = df1[col].value_counts()
            vc2 = df2[col].value_counts()
            
            top1 = vc1.index[0] if len(vc1) > 0 else None
            top2 = vc2.index[0] if len(vc2) > 0 else None
            
            comparison['categorical_comparisons'][col] = {
                f'{label1}_unique': df1[col].nunique(),
                f'{label2}_unique': df2[col].nunique(),
                f'{label1}_top': top1,
                f'{label2}_top': top2,
                'top_changed': top1 != top2
            }
    
    return comparison


def simple_forecast(values: List[float], periods: int = 3) -> Dict[str, Any]:
    """Simple linear forecast based on historical values"""
    if len(values) < 2:
        return {'error': 'لا توجد بيانات كافية للتنبؤ'}
    
    X = np.arange(len(values)).reshape(-1, 1)
    y = np.array(values)
    
    model = LinearRegression()
    model.fit(X, y)
    
    future_X = np.arange(len(values), len(values) + periods).reshape(-1, 1)
    predictions = model.predict(future_X)
    
    fitted_values = model.predict(X)
    mse = mean_squared_error(y, fitted_values)
    r2 = r2_score(y, fitted_values)
    
    trend = 'صاعد' if model.coef_[0] > 0.01 else ('هابط' if model.coef_[0] < -0.01 else 'مستقر')
    
    return {
        'predictions': predictions.tolist(),
        'trend': trend,
        'slope': round(model.coef_[0], 4),
        'r2_score': round(r2, 4),
        'mse': round(mse, 4),
        'confidence': 'عالية' if r2 > 0.7 else ('متوسطة' if r2 > 0.4 else 'منخفضة')
    }


def analyze_trend(df: pd.DataFrame, date_col: str, value_col: str) -> Dict[str, Any]:
    """Analyze trend in time series data"""
    if date_col not in df.columns or value_col not in df.columns:
        return {'error': 'الأعمدة المحددة غير موجودة'}
    
    df_sorted = df.sort_values(date_col)
    values = df_sorted[value_col].dropna().tolist()
    
    if len(values) < 3:
        return {'error': 'لا توجد بيانات كافية لتحليل الاتجاه'}
    
    forecast_result = simple_forecast(values, periods=3)
    
    moving_avg_3 = pd.Series(values).rolling(window=3, min_periods=1).mean().tolist()
    
    changes = []
    for i in range(1, len(values)):
        change = ((values[i] - values[i-1]) / values[i-1]) * 100 if values[i-1] != 0 else 0
        changes.append(round(change, 2))
    
    return {
        'forecast': forecast_result,
        'moving_average': moving_avg_3,
        'period_changes': changes,
        'avg_change': round(np.mean(changes), 2) if changes else 0,
        'volatility': round(np.std(changes), 2) if changes else 0,
        'total_growth': round(((values[-1] - values[0]) / values[0]) * 100, 2) if values[0] != 0 else 0
    }


def predict_column(df: pd.DataFrame, target_col: str, 
                   feature_cols: List[str] = None) -> Dict[str, Any]:
    """Build a simple prediction model for a target column"""
    if target_col not in df.columns:
        return {'error': 'العمود المستهدف غير موجود'}
    
    numeric_df = df.select_dtypes(include=[np.number])
    
    if feature_cols is None:
        feature_cols = [col for col in numeric_df.columns if col != target_col]
    
    if not feature_cols:
        return {'error': 'لا توجد أعمدة رقمية للتنبؤ'}
    
    X = df[feature_cols].dropna()
    y = df.loc[X.index, target_col]
    
    valid_idx = ~y.isna()
    X = X[valid_idx]
    y = y[valid_idx]
    
    if len(X) < 10:
        return {'error': 'البيانات غير كافية للتنبؤ (أقل من 10 صفوف)'}
    
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=42
    )
    
    model = LinearRegression()
    model.fit(X_train, y_train)
    
    y_pred = model.predict(X_test)
    
    mse = mean_squared_error(y_test, y_pred)
    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    
    feature_importance = dict(zip(feature_cols, 
                                  [round(abs(c), 4) for c in model.coef_]))
    sorted_importance = dict(sorted(feature_importance.items(), 
                                    key=lambda x: x[1], reverse=True))
    
    return {
        'model_type': 'الانحدار الخطي',
        'target_column': target_col,
        'features_used': feature_cols,
        'metrics': {
            'r2_score': round(r2, 4),
            'mse': round(mse, 4),
            'mae': round(mae, 4),
            'rmse': round(np.sqrt(mse), 4)
        },
        'feature_importance': sorted_importance,
        'model_quality': 'ممتاز' if r2 > 0.8 else ('جيد' if r2 > 0.6 else ('متوسط' if r2 > 0.4 else 'ضعيف'))
    }


def detect_anomalies_zscore(df: pd.DataFrame, threshold: float = 3.0) -> Dict[str, List]:
    """Detect anomalies using Z-score method"""
    anomalies = {}
    numeric_df = df.select_dtypes(include=[np.number])
    
    for col in numeric_df.columns:
        mean = df[col].mean()
        std = df[col].std()
        
        if std == 0:
            continue
            
        z_scores = np.abs((df[col] - mean) / std)
        anomaly_indices = df.index[z_scores > threshold].tolist()
        
        if anomaly_indices:
            anomalies[col] = {
                'count': len(anomaly_indices),
                'indices': anomaly_indices[:10],
                'values': df.loc[anomaly_indices[:10], col].tolist()
            }
    
    return anomalies


def calculate_growth_metrics(values: List[float]) -> Dict[str, float]:
    """Calculate various growth metrics"""
    if len(values) < 2:
        return {}
    
    total_growth = ((values[-1] - values[0]) / values[0]) * 100 if values[0] != 0 else 0
    
    period_growths = []
    for i in range(1, len(values)):
        if values[i-1] != 0:
            growth = ((values[i] - values[i-1]) / values[i-1]) * 100
            period_growths.append(growth)
    
    cagr = 0
    if values[0] != 0 and len(values) > 1:
        cagr = ((values[-1] / values[0]) ** (1 / (len(values) - 1)) - 1) * 100
    
    return {
        'total_growth_pct': round(total_growth, 2),
        'avg_period_growth_pct': round(np.mean(period_growths), 2) if period_growths else 0,
        'max_growth_pct': round(max(period_growths), 2) if period_growths else 0,
        'min_growth_pct': round(min(period_growths), 2) if period_growths else 0,
        'cagr_pct': round(cagr, 2)
    }


def build_ml_prediction_model(df: pd.DataFrame, target_col: str) -> Dict[str, Any]:
    """Build ML model to predict a target variable (classification or regression)"""
    try:
        df_clean = df.dropna(subset=[target_col])
        if len(df_clean) < 50:
            return {'error': 'Not enough data for ML model (need at least 50 rows)'}
        
        numeric_cols = df_clean.select_dtypes(include=[np.number]).columns.tolist()
        if target_col in numeric_cols:
            numeric_cols.remove(target_col)
        
        if len(numeric_cols) < 2:
            return {'error': 'Not enough numeric features for prediction'}
        
        X = df_clean[numeric_cols].fillna(0)
        y = df_clean[target_col]
        
        is_classification = y.nunique() <= 10
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        if is_classification:
            model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            feature_importance = dict(zip(numeric_cols, model.feature_importances_))
            feature_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:10])
            
            return {
                'model_type': 'classification',
                'accuracy': round(accuracy * 100, 2),
                'feature_importance': {k: round(v * 100, 2) for k, v in feature_importance.items()},
                'features_used': numeric_cols,
                'target': target_col,
                'train_size': len(X_train),
                'test_size': len(X_test),
                'classes': y.unique().tolist()
            }
        else:
            model = LinearRegression()
            model.fit(X_train_scaled, y_train)
            y_pred = model.predict(X_test_scaled)
            r2 = r2_score(y_test, y_pred)
            mae = mean_absolute_error(y_test, y_pred)
            
            return {
                'model_type': 'regression',
                'r2_score': round(r2 * 100, 2),
                'mae': round(mae, 2),
                'features_used': numeric_cols,
                'target': target_col,
                'train_size': len(X_train),
                'test_size': len(X_test)
            }
            
    except Exception as e:
        return {'error': str(e)}


def create_risk_clusters(df: pd.DataFrame, n_clusters: int = 4) -> Dict[str, Any]:
    """Create customer/data risk clusters using KMeans"""
    try:
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        if len(numeric_cols) < 2:
            return {'error': 'Not enough numeric columns for clustering'}
        
        df_cluster = df[numeric_cols].dropna()
        
        if len(df_cluster) < n_clusters * 10:
            return {'error': f'Not enough data for {n_clusters} clusters'}
        
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(df_cluster)
        
        kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        clusters = kmeans.fit_predict(X_scaled)
        
        df_cluster = df_cluster.copy()
        df_cluster['cluster'] = clusters
        
        cluster_stats = {}
        for i in range(n_clusters):
            cluster_data = df_cluster[df_cluster['cluster'] == i]
            cluster_stats[f'Cluster {i+1}'] = {
                'size': len(cluster_data),
                'percentage': round(len(cluster_data) / len(df_cluster) * 100, 2),
                'characteristics': {}
            }
            for col in numeric_cols[:5]:
                cluster_stats[f'Cluster {i+1}']['characteristics'][col] = {
                    'mean': round(cluster_data[col].mean(), 2),
                    'std': round(cluster_data[col].std(), 2)
                }
        
        risk_levels = ['Low Risk', 'Medium-Low Risk', 'Medium-High Risk', 'High Risk']
        cluster_means = []
        for i in range(n_clusters):
            cluster_data = df_cluster[df_cluster['cluster'] == i]
            cluster_means.append((i, cluster_data[numeric_cols].mean().mean()))
        cluster_means.sort(key=lambda x: x[1])
        
        risk_mapping = {}
        for idx, (cluster_id, _) in enumerate(cluster_means):
            risk_mapping[cluster_id] = risk_levels[idx] if idx < len(risk_levels) else f'Level {idx+1}'
        
        return {
            'n_clusters': n_clusters,
            'cluster_stats': cluster_stats,
            'cluster_labels': clusters.tolist(),
            'risk_mapping': risk_mapping,
            'inertia': round(kmeans.inertia_, 2),
            'features_used': numeric_cols
        }
        
    except Exception as e:
        return {'error': str(e)}


def analyze_categorical_insights(df: pd.DataFrame) -> Dict[str, Any]:
    """Deep analysis of categorical columns"""
    cat_cols = df.select_dtypes(include=['object', 'category']).columns.tolist()
    
    if not cat_cols:
        return {'error': 'No categorical columns found'}
    
    insights = {}
    for col in cat_cols:
        value_counts = df[col].value_counts()
        total = len(df[col].dropna())
        
        balance_ratio = value_counts.min() / value_counts.max() if value_counts.max() > 0 else 0
        
        insights[col] = {
            'unique_values': df[col].nunique(),
            'missing': df[col].isnull().sum(),
            'missing_pct': round(df[col].isnull().sum() / len(df) * 100, 2),
            'distribution': {k: {'count': v, 'pct': round(v/total*100, 2)} for k, v in value_counts.head(10).items()},
            'is_balanced': balance_ratio > 0.3,
            'balance_ratio': round(balance_ratio, 2),
            'top_category': value_counts.index[0] if len(value_counts) > 0 else None,
            'bottom_category': value_counts.index[-1] if len(value_counts) > 0 else None
        }
    
    return insights
