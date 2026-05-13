import pandas as pd
import numpy as np
from typing import Dict, Any, List
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_squared_error, r2_score

def compare_datasets(df1: pd.DataFrame, df2: pd.DataFrame, 
                    label1: str = "الفترة الأولى", 
                    label2: str = "الفترة الثانية") -> Dict[str, Any]:
    """Compare two datasets and return comparison statistics.
    
    Used for period-over-period analysis in the Artifact Drawer and Reports.
    """
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
        if pd.api.types.is_numeric_dtype(df1[col]) and pd.api.types.is_numeric_dtype(df2[col]):
            mean1 = float(df1[col].mean())
            mean2 = float(df2[col].mean())
            std1 = float(df1[col].std())
            std2 = float(df2[col].std())
            
            comparison['numeric_comparisons'][col] = {
                f'{label1}_mean': round(mean1, 2),
                f'{label2}_mean': round(mean2, 2),
                'mean_change': round(mean2 - mean1, 2),
                'mean_change_pct': round(((mean2 - mean1) / mean1) * 100, 2) if mean1 != 0 else 0,
                f'{label1}_std': round(std1, 2),
                f'{label2}_std': round(std2, 2),
                f'{label1}_min': round(float(df1[col].min()), 2),
                f'{label2}_min': round(float(df2[col].min()), 2),
                f'{label1}_max': round(float(df1[col].max()), 2),
                f'{label2}_max': round(float(df2[col].max()), 2),
            }
        
        elif df1[col].dtype == 'object':
            vc1 = df1[col].value_counts()
            vc2 = df2[col].value_counts()
            
            top1 = str(vc1.index[0]) if len(vc1) > 0 else None
            top2 = str(vc2.index[0]) if len(vc2) > 0 else None
            
            comparison['categorical_comparisons'][col] = {
                f'{label1}_unique': int(df1[col].nunique()),
                f'{label2}_unique': int(df2[col].nunique()),
                f'{label1}_top': top1,
                f'{label2}_top': top2,
                'top_changed': top1 != top2
            }
    
    return comparison

def simple_forecast(values: List[float], periods: int = 3) -> Dict[str, Any]:
    """Simple linear forecast based on historical values.
    
    Legacy helper for backward compatibility with older UI components.
    """
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
