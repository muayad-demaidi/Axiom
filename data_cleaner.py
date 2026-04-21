import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, List, Callable


# ── Power Query-style cleaning substeps ──────────────────────────────────────
# Each substep is a small, named, reversible transformation. They appear as
# their own entries in the Applied Steps panel and can be toggled on/off.

def remove_duplicates_step(df: pd.DataFrame, **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    n = int(out.duplicated().sum())
    if n > 0:
        out = out.drop_duplicates().reset_index(drop=True)
        summary = f"Removed {n:,} duplicate rows"
    else:
        summary = "No duplicate rows found"
    return out, summary, {"duplicates_removed": n, "changes": ([summary] if n > 0 else [])}


def fill_missing_numeric_step(df: pd.DataFrame, **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    changes: List[str] = []
    numeric_cols = out.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        missing = int(out[col].isnull().sum())
        if missing == 0:
            continue
        pct = (missing / len(out)) * 100 if len(out) else 0
        if pct > 50:
            changes.append(f"Skipped `{col}` — {pct:.1f}% missing (too sparse to impute)")
            continue
        median_val = out[col].median()
        if pd.isna(median_val):
            continue
        out[col] = out[col].fillna(median_val)
        changes.append(f"Filled {missing} missing in `{col}` with median ({median_val:.2f})")
    summary = (f"Filled missing in {len(changes)} numeric column(s)"
               if changes else "No numeric missing values to fill")
    return out, summary, {"changes": changes}


def fill_missing_categorical_step(df: pd.DataFrame, **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    changes: List[str] = []
    numeric_cols = set(out.select_dtypes(include=[np.number]).columns)
    for col in out.columns:
        if col in numeric_cols:
            continue
        missing = int(out[col].isnull().sum())
        if missing == 0:
            continue
        pct = (missing / len(out)) * 100 if len(out) else 0
        if pct > 50:
            changes.append(f"Skipped `{col}` — {pct:.1f}% missing (too sparse to impute)")
            continue
        mode_val = out[col].mode()
        if len(mode_val) > 0:
            out[col] = out[col].fillna(mode_val[0])
            changes.append(f"Filled {missing} missing in `{col}` with mode (`{mode_val[0]}`)")
    summary = (f"Filled missing in {len(changes)} categorical column(s)"
               if changes else "No categorical missing values to fill")
    return out, summary, {"changes": changes}


def clip_outliers_step(df: pd.DataFrame, **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    changes: List[str] = []
    clipped_cols = 0
    for col in out.select_dtypes(include=[np.number]).columns:
        Q1 = out[col].quantile(0.25)
        Q3 = out[col].quantile(0.75)
        IQR = Q3 - Q1
        if pd.isna(IQR) or IQR == 0:
            continue
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        mask = (out[col] < lower) | (out[col] > upper)
        n = int(mask.sum())
        if n == 0:
            continue
        pct = (n / len(out)) * 100 if len(out) else 0
        if pct < 5:
            out.loc[out[col] < lower, col] = lower
            out.loc[out[col] > upper, col] = upper
            changes.append(f"Clipped {n} outlier(s) in `{col}` to [{lower:.2f}, {upper:.2f}]")
            clipped_cols += 1
        else:
            changes.append(f"Detected {n} outlier(s) in `{col}` ({pct:.1f}%) — left as-is")
    summary = (f"Clipped outliers in {clipped_cols} numeric column(s)"
               if clipped_cols else
               ("Outliers reported but not clipped" if changes else "No outliers detected"))
    return out, summary, {"changes": changes}


def trim_whitespace_step(df: pd.DataFrame, **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    changes: List[str] = []
    for col in out.select_dtypes(include=['object']).columns:
        before = out[col]
        trimmed = out[col].apply(lambda v: v.strip() if isinstance(v, str) else v)
        n = int((before.fillna('__nan__') != trimmed.fillna('__nan__')).sum())
        if n > 0:
            out[col] = trimmed
            changes.append(f"Trimmed whitespace in {n} value(s) of `{col}`")
    summary = (f"Trimmed whitespace in {len(changes)} text column(s)"
               if changes else "No whitespace to trim")
    return out, summary, {"changes": changes}


def drop_column_step(df: pd.DataFrame, column: str | None = None,
                     **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    if column and column in out.columns:
        out = out.drop(columns=[column])
        summary = f"Dropped column `{column}`"
        return out, summary, {"changes": [summary]}
    return out, f"Skipped — column `{column}` not present", {"changes": []}


def rename_column_step(df: pd.DataFrame, column: str | None = None,
                       new_name: str | None = None,
                       **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    if column and new_name and column in out.columns:
        out = out.rename(columns={column: new_name})
        summary = f"Renamed `{column}` → `{new_name}`"
        return out, summary, {"changes": [summary]}
    return out, "Skipped — invalid rename parameters", {"changes": []}


# Unified registry. `params` describes user-editable parameters for substeps
# inserted via the UI. `kind` is one of: "column" (pick from current columns),
# "text" (free text input).
SUBSTEP_REGISTRY: Dict[str, Dict[str, Any]] = {
    "remove_duplicates": {
        "label": "Remove Duplicates",
        "fn": remove_duplicates_step,
        "params": [],
        "insertable": True,
    },
    "fill_missing_numeric": {
        "label": "Fill Missing — Numeric",
        "fn": fill_missing_numeric_step,
        "params": [],
        "insertable": True,
    },
    "fill_missing_categorical": {
        "label": "Fill Missing — Categorical",
        "fn": fill_missing_categorical_step,
        "params": [],
        "insertable": True,
    },
    "clip_outliers": {
        "label": "Clip Outliers",
        "fn": clip_outliers_step,
        "params": [],
        "insertable": True,
    },
    "trim_whitespace": {
        "label": "Trim Whitespace",
        "fn": trim_whitespace_step,
        "params": [],
        "insertable": True,
    },
    "drop_column": {
        "label": "Drop Column",
        "fn": drop_column_step,
        "params": [{"name": "column", "kind": "column", "label": "Column"}],
        "insertable": True,
    },
    "rename_column": {
        "label": "Rename Column",
        "fn": rename_column_step,
        "params": [
            {"name": "column", "kind": "column", "label": "Column"},
            {"name": "new_name", "kind": "text", "label": "New name"},
        ],
        "insertable": True,
    },
}

# Default ordered cleaning plan applied to fresh datasets.
DEFAULT_CLEANING_PLAN: List[str] = [
    "remove_duplicates",
    "fill_missing_numeric",
    "fill_missing_categorical",
    "clip_outliers",
]

# Back-compat alias kept for any external readers (label tuples).
CLEANING_SUBSTEPS: List[Tuple[str, str]] = [
    (k, SUBSTEP_REGISTRY[k]["label"]) for k in DEFAULT_CLEANING_PLAN
]

SUBSTEP_FUNCS: Dict[str, Callable[..., Tuple[pd.DataFrame, str, Dict[str, Any]]]] = {
    k: v["fn"] for k, v in SUBSTEP_REGISTRY.items()
}


def substep_label(key: str, params: Dict[str, Any] | None = None) -> str:
    """Human-readable label for a (possibly parameterized) substep."""
    base = SUBSTEP_REGISTRY.get(key, {}).get("label", key)
    params = params or {}
    if key == "drop_column" and params.get("column"):
        return f"Drop Column · {params['column']}"
    if key == "rename_column" and params.get("column"):
        return f"Rename · {params['column']} → {params.get('new_name', '?')}"
    return base


def run_substep(key: str, df: pd.DataFrame,
                params: Dict[str, Any] | None = None
                ) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    fn = SUBSTEP_REGISTRY[key]["fn"]
    return fn(df, **(params or {}))


def clean_data(df: pd.DataFrame,
               enabled: Dict[str, bool] | None = None
               ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Run the default cleaning pipeline as a sequence of named substeps.

    `enabled` optionally maps substep keys to bool toggles; missing keys
    default to True. Disabled substeps are pass-through.
    """
    enabled = enabled or {}
    report: Dict[str, Any] = {
        'original_rows': len(df),
        'original_columns': len(df.columns),
        'changes': [],
        'substeps': [],
    }
    current = df.copy()
    for key in DEFAULT_CLEANING_PLAN:
        label = SUBSTEP_REGISTRY[key]["label"]
        on = enabled.get(key, True)
        if on:
            current, summary, details = run_substep(key, current)
            report['changes'].extend(details.get('changes', []))
        else:
            summary, details = "Disabled — pass through", {}
        report['substeps'].append({
            'key': key, 'label': label, 'enabled': on,
            'summary': summary, 'details': details,
        })
    report['final_rows'] = len(current)
    report['final_columns'] = len(current.columns)
    report['rows_removed'] = report['original_rows'] - report['final_rows']
    return current, report


def detect_column_types(df: pd.DataFrame) -> Dict[str, str]:
    """Detect and categorize column types"""
    column_types = {}
    
    for col in df.columns:
        if df[col].dtype in ['int64', 'float64']:
            if df[col].nunique() < 10:
                column_types[col] = 'Numeric Categorical'
            else:
                column_types[col] = 'Numeric Continuous'
        elif df[col].dtype == 'object':
            try:
                pd.to_datetime(df[col], errors='raise')
                column_types[col] = 'DateTime'
            except:
                if df[col].nunique() < 20:
                    column_types[col] = 'Text Categorical'
                else:
                    column_types[col] = 'Text'
        elif df[col].dtype == 'datetime64[ns]':
            column_types[col] = 'DateTime'
        elif df[col].dtype == 'bool':
            column_types[col] = 'Boolean'
        else:
            column_types[col] = 'Unknown'
    
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
