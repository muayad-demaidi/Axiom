import pandas as pd
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score, mean_absolute_error
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
