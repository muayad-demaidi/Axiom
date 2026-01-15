import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, List


def clean_data(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Clean the dataframe by handling missing values, duplicates, and outliers.
    Returns cleaned dataframe and a report of changes made.
    """
    report = {
        'original_rows': len(df),
        'original_columns': len(df.columns),
        'changes': []
    }
    
    df_cleaned = df.copy()
    
    duplicates_count = df_cleaned.duplicated().sum()
    if duplicates_count > 0:
        df_cleaned = df_cleaned.drop_duplicates()
        report['changes'].append(f"تم إزالة {duplicates_count} صف مكرر")
    
    missing_report = []
    for col in df_cleaned.columns:
        missing_count = df_cleaned[col].isnull().sum()
        if missing_count > 0:
            missing_pct = (missing_count / len(df_cleaned)) * 100
            
            if missing_pct > 50:
                missing_report.append(f"العمود '{col}' يحتوي على {missing_pct:.1f}% قيم مفقودة")
            else:
                if df_cleaned[col].dtype in ['int64', 'float64']:
                    median_val = df_cleaned[col].median()
                    df_cleaned[col].fillna(median_val, inplace=True)
                    missing_report.append(f"تم ملء {missing_count} قيمة مفقودة في '{col}' بالقيمة الوسطى ({median_val:.2f})")
                else:
                    mode_val = df_cleaned[col].mode()
                    if len(mode_val) > 0:
                        df_cleaned[col].fillna(mode_val[0], inplace=True)
                        missing_report.append(f"تم ملء {missing_count} قيمة مفقودة في '{col}' بالقيمة الأكثر تكراراً")
    
    if missing_report:
        report['changes'].extend(missing_report)
    
    outliers_report = []
    numeric_cols = df_cleaned.select_dtypes(include=[np.number]).columns
    
    for col in numeric_cols:
        Q1 = df_cleaned[col].quantile(0.25)
        Q3 = df_cleaned[col].quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - 1.5 * IQR
        upper_bound = Q3 + 1.5 * IQR
        
        outliers_mask = (df_cleaned[col] < lower_bound) | (df_cleaned[col] > upper_bound)
        outliers_count = outliers_mask.sum()
        
        if outliers_count > 0:
            outliers_pct = (outliers_count / len(df_cleaned)) * 100
            if outliers_pct < 5:
                df_cleaned.loc[df_cleaned[col] < lower_bound, col] = lower_bound
                df_cleaned.loc[df_cleaned[col] > upper_bound, col] = upper_bound
                outliers_report.append(f"تم معالجة {outliers_count} قيمة شاذة في '{col}' (تم تقريبها للحدود)")
            else:
                outliers_report.append(f"تم اكتشاف {outliers_count} قيمة شاذة في '{col}' ({outliers_pct:.1f}%)")
    
    if outliers_report:
        report['changes'].extend(outliers_report)
    
    report['final_rows'] = len(df_cleaned)
    report['final_columns'] = len(df_cleaned.columns)
    report['rows_removed'] = report['original_rows'] - report['final_rows']
    
    return df_cleaned, report


def detect_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """Detect and categorize column types"""
    column_types = {}
    
    for col in df.columns:
        if df[col].dtype in ['int64', 'float64']:
            if df[col].nunique() < 10:
                column_types[col] = 'فئوي رقمي'
            else:
                column_types[col] = 'رقمي مستمر'
        elif df[col].dtype == 'object':
            try:
                pd.to_datetime(df[col], errors='raise')
                column_types[col] = 'تاريخ'
            except:
                if df[col].nunique() < 20:
                    column_types[col] = 'فئوي نصي'
                else:
                    column_types[col] = 'نصي'
        elif df[col].dtype == 'datetime64[ns]':
            column_types[col] = 'تاريخ'
        elif df[col].dtype == 'bool':
            column_types[col] = 'منطقي'
        else:
            column_types[col] = 'غير محدد'
    
    return column_types


def get_data_quality_score(df: pd.DataFrame) -> Dict[str, Any]:
    """Calculate data quality score"""
    total_cells = df.size
    missing_cells = df.isnull().sum().sum()
    duplicates = df.duplicated().sum()
    
    completeness = ((total_cells - missing_cells) / total_cells) * 100
    uniqueness = ((len(df) - duplicates) / len(df)) * 100 if len(df) > 0 else 100
    
    overall_score = (completeness * 0.6 + uniqueness * 0.4)
    
    return {
        'overall_score': round(overall_score, 1),
        'completeness': round(completeness, 1),
        'uniqueness': round(uniqueness, 1),
        'total_cells': total_cells,
        'missing_cells': int(missing_cells),
        'duplicate_rows': int(duplicates)
    }


def standardize_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """Standardize column names by removing special characters and spaces"""
    df_copy = df.copy()
    new_columns = {}
    
    for col in df_copy.columns:
        new_col = str(col).strip()
        new_col = new_col.replace(' ', '_')
        new_columns[col] = new_col
    
    df_copy.rename(columns=new_columns, inplace=True)
    return df_copy


def convert_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Try to convert string columns to datetime"""
    df_copy = df.copy()
    
    for col in df_copy.columns:
        if df_copy[col].dtype == 'object':
            try:
                df_copy[col] = pd.to_datetime(df_copy[col], errors='raise')
            except:
                pass
    
    return df_copy
