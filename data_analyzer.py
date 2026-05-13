import pandas as pd
import numpy as np
from typing import Dict, Any, List
from scipy import stats


def get_basic_stats(df: pd.DataFrame) -> Dict[str, Any]:
    """Get basic statistics for the dataframe"""
    stats_dict = {
        'row_count': len(df),
        'column_count': len(df.columns),
        'memory_usage': f"{df.memory_usage(deep=True).sum() / 1024:.2f} KB",
        'columns': list(df.columns),
        'dtypes': df.dtypes.astype(str).to_dict()
    }
    return stats_dict


def get_numeric_stats(df: pd.DataFrame) -> pd.DataFrame:
    """Get detailed statistics for numeric columns"""
    numeric_df = df.select_dtypes(include=[np.number])
    
    if numeric_df.empty:
        return pd.DataFrame()
    
    stats_df = numeric_df.describe().T
    stats_df['median'] = numeric_df.median()
    stats_df['mode'] = numeric_df.mode().iloc[0] if not numeric_df.mode().empty else np.nan
    stats_df['variance'] = numeric_df.var()
    stats_df['skewness'] = numeric_df.skew()
    stats_df['kurtosis'] = numeric_df.kurtosis()
    stats_df['missing'] = numeric_df.isnull().sum()
    stats_df['missing_pct'] = (numeric_df.isnull().sum() / len(df)) * 100
    
    return stats_df.round(2)


def get_categorical_stats(df: pd.DataFrame) -> Dict[str, Dict]:
    """Get statistics for categorical columns"""
    categorical_df = df.select_dtypes(include=['object', 'category'])
    
    cat_stats = {}
    for col in categorical_df.columns:
        value_counts = df[col].value_counts()
        cat_stats[col] = {
            'unique_count': df[col].nunique(),
            'most_common': value_counts.index[0] if len(value_counts) > 0 else None,
            'most_common_count': int(value_counts.iloc[0]) if len(value_counts) > 0 else 0,
            'least_common': value_counts.index[-1] if len(value_counts) > 0 else None,
            'least_common_count': int(value_counts.iloc[-1]) if len(value_counts) > 0 else 0,
            'missing': int(df[col].isnull().sum()),
            'top_values': value_counts.head(5).to_dict()
        }
    
    return cat_stats


def get_correlation_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate correlation matrix for numeric columns"""
    numeric_df = df.select_dtypes(include=[np.number])
    
    if numeric_df.empty or len(numeric_df.columns) < 2:
        return pd.DataFrame()
    
    return numeric_df.corr().round(3)


def find_strong_correlations(df: pd.DataFrame, threshold: float = 0.7) -> List[Dict]:
    """Find pairs of columns with strong correlations"""
    corr_matrix = get_correlation_matrix(df)
    
    if corr_matrix.empty:
        return []
    
    strong_correlations = []
    for i in range(len(corr_matrix.columns)):
        for j in range(i + 1, len(corr_matrix.columns)):
            corr_value = corr_matrix.iloc[i, j]
            if abs(corr_value) >= threshold:
                strong_correlations.append({
                    'column1': corr_matrix.columns[i],
                    'column2': corr_matrix.columns[j],
                    'correlation': corr_value,
                    'type': 'إيجابية قوية' if corr_value > 0 else 'سلبية قوية'
                })
    
    return sorted(strong_correlations, key=lambda x: abs(x['correlation']), reverse=True)


def detect_outliers(df: pd.DataFrame) -> Dict[str, Dict]:
    """Detect outliers using IQR method"""
    numeric_df = df.select_dtypes(include=[np.number])
    outliers_info = {}
    
    for col in numeric_df.columns:
        Q1 = df[col].quantile(0.25)
        Q3 = df[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        outliers_mask = (df[col] < lower_bound) | (df[col] > upper_bound)
        outliers_count = outliers_mask.sum()
        
        if outliers_count > 0:
            outliers_info[col] = {
                'count': int(outliers_count),
                'percentage': round((outliers_count / len(df)) * 100, 2),
                'lower_bound': round(lower_bound, 2),
                'upper_bound': round(upper_bound, 2),
                'min_outlier': round(df[col][outliers_mask].min(), 2) if outliers_count > 0 else None,
                'max_outlier': round(df[col][outliers_mask].max(), 2) if outliers_count > 0 else None
            }
    
    return outliers_info


def get_distribution_info(df: pd.DataFrame) -> Dict[str, Dict]:
    """Get distribution information for numeric columns"""
    numeric_df = df.select_dtypes(include=[np.number])
    distribution_info = {}
    
    for col in numeric_df.columns:
        data = df[col].dropna()
        if len(data) < 8:
            continue
            
        _, p_value = stats.normaltest(data)
        
        skewness = data.skew()
        if abs(skewness) < 0.5:
            dist_type = 'توزيع متماثل'
        elif skewness > 0:
            dist_type = 'انحراف إيجابي (ذيل يميني)'
        else:
            dist_type = 'انحراف سلبي (ذيل يساري)'
        
        distribution_info[col] = {
            'skewness': round(skewness, 3),
            'kurtosis': round(data.kurtosis(), 3),
            'is_normal': p_value > 0.05,
            'normality_p_value': round(p_value, 4),
            'distribution_type': dist_type
        }
    
    return distribution_info


def generate_summary_report(df: pd.DataFrame) -> Dict[str, Any]:
    """Generate a comprehensive summary report"""
    basic_stats = get_basic_stats(df)
    numeric_stats = get_numeric_stats(df)
    categorical_stats = get_categorical_stats(df)
    correlations = find_strong_correlations(df)
    outliers = detect_outliers(df)
    distributions = get_distribution_info(df)
    
    summary = {
        'basic_info': basic_stats,
        'numeric_summary': numeric_stats.to_dict() if not numeric_stats.empty else {},
        'categorical_summary': categorical_stats,
        'strong_correlations': correlations,
        'outliers_detected': outliers,
        'distributions': distributions,
        'key_insights': []
    }
    
    if correlations:
        summary['key_insights'].append(f"تم اكتشاف {len(correlations)} علاقة ارتباط قوية بين الأعمدة")
    
    if outliers:
        total_outliers = sum(info['count'] for info in outliers.values())
        summary['key_insights'].append(f"تم اكتشاف {total_outliers} قيمة شاذة في {len(outliers)} عمود")
    
    return summary
