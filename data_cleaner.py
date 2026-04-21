import pandas as pd
import numpy as np
from typing import Tuple, Dict, Any, List, Callable, Optional

from transforms import TRANSFORM_REGISTRY, transform_step_label


# ── Power Query-style cleaning substeps ──────────────────────────────────────
# Each substep is a small, named, reversible transformation. They appear as
# their own entries in the Applied Steps panel and can be toggled on/off,
# and each accepts keyword params so users can tune thresholds without
# editing code. Default values live in `SUBSTEP_PARAM_SCHEMA` below.


def _params_for(key: str, params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge user-supplied params on top of the substep's declared defaults."""
    merged = {p["key"]: p["default"] for p in SUBSTEP_PARAM_SCHEMA.get(key, [])}
    if params:
        for k, v in params.items():
            if k in merged and v is not None:
                merged[k] = v
    return merged


def remove_duplicates_step(df: pd.DataFrame, **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    out = df.copy()
    n = int(out.duplicated().sum())
    if n > 0:
        out = out.drop_duplicates().reset_index(drop=True)
        summary = f"Removed {n:,} duplicate rows"
    else:
        summary = "No duplicate rows found"
    return out, summary, {"duplicates_removed": n, "changes": ([summary] if n > 0 else [])}


def fill_missing_numeric_step(df: pd.DataFrame, **params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    p = _params_for("fill_missing_numeric", params)
    cap = float(p["missing_cap_pct"])
    out = df.copy()
    changes: List[str] = []
    filled_cols = 0
    numeric_cols = out.select_dtypes(include=[np.number]).columns
    for col in numeric_cols:
        missing = int(out[col].isnull().sum())
        if missing == 0:
            continue
        pct = (missing / len(out)) * 100 if len(out) else 0
        if pct > cap:
            changes.append(f"Skipped `{col}` — {pct:.1f}% missing (> {cap:.0f}% cap)")
            continue
        median_val = out[col].median()
        if pd.isna(median_val):
            continue
        out[col] = out[col].fillna(median_val)
        filled_cols += 1
        changes.append(f"Filled {missing} missing in `{col}` with median ({median_val:.2f})")
    summary = (f"Filled missing in {filled_cols} numeric column(s) (cap {cap:.0f}%)"
               if filled_cols else f"No numeric missing values to fill (cap {cap:.0f}%)")
    return out, summary, {"changes": changes}


def fill_missing_categorical_step(df: pd.DataFrame, **params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    p = _params_for("fill_missing_categorical", params)
    cap = float(p["missing_cap_pct"])
    out = df.copy()
    changes: List[str] = []
    filled_cols = 0
    numeric_cols = set(out.select_dtypes(include=[np.number]).columns)
    for col in out.columns:
        if col in numeric_cols:
            continue
        missing = int(out[col].isnull().sum())
        if missing == 0:
            continue
        pct = (missing / len(out)) * 100 if len(out) else 0
        if pct > cap:
            changes.append(f"Skipped `{col}` — {pct:.1f}% missing (> {cap:.0f}% cap)")
            continue
        mode_val = out[col].mode()
        if len(mode_val) > 0:
            out[col] = out[col].fillna(mode_val[0])
            filled_cols += 1
            changes.append(f"Filled {missing} missing in `{col}` with mode (`{mode_val[0]}`)")
    summary = (f"Filled missing in {filled_cols} categorical column(s) (cap {cap:.0f}%)"
               if filled_cols else f"No categorical missing values to fill (cap {cap:.0f}%)")
    return out, summary, {"changes": changes}


def clip_outliers_step(df: pd.DataFrame, **params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    p = _params_for("clip_outliers", params)
    iqr_mult = float(p["iqr_multiplier"])
    clip_cap = float(p["clip_threshold_pct"])
    out = df.copy()
    changes: List[str] = []
    clipped_cols = 0
    for col in out.select_dtypes(include=[np.number]).columns:
        Q1 = out[col].quantile(0.25)
        Q3 = out[col].quantile(0.75)
        IQR = Q3 - Q1
        if pd.isna(IQR) or IQR == 0:
            continue
        lower = Q1 - iqr_mult * IQR
        upper = Q3 + iqr_mult * IQR
        mask = (out[col] < lower) | (out[col] > upper)
        n = int(mask.sum())
        if n == 0:
            continue
        pct = (n / len(out)) * 100 if len(out) else 0
        if pct < clip_cap:
            out.loc[out[col] < lower, col] = lower
            out.loc[out[col] > upper, col] = upper
            changes.append(f"Clipped {n} outlier(s) in `{col}` to [{lower:.2f}, {upper:.2f}]")
            clipped_cols += 1
        else:
            changes.append(
                f"Detected {n} outlier(s) in `{col}` ({pct:.1f}%) — left as-is "
                f"(above {clip_cap:.0f}% clip cap)"
            )
    summary = (f"Clipped outliers in {clipped_cols} numeric column(s) "
               f"(IQR×{iqr_mult:g}, cap {clip_cap:.0f}%)"
               if clipped_cols else
               (f"Outliers reported but not clipped (above {clip_cap:.0f}% cap)"
                if changes else f"No outliers detected (IQR×{iqr_mult:g})"))
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


def record_decision_step(df: pd.DataFrame,
                         column: str | None = None,
                         decision: str | None = None,
                         note: str | None = None,
                         **_params) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    """A pass-through step that records a user decision in the Applied
    Steps panel. Used by the Proactive Question Bar when the chosen
    answer has no concrete transform yet (e.g., 'keep as text', 'treat
    as primary currency') so the decision is still visible, reorderable,
    and reversible — matching Power Query-style auditability."""
    label_bits = []
    if column:
        label_bits.append(f"`{column}`")
    if decision:
        label_bits.append(decision)
    if note:
        label_bits.append(note)
    summary = "Decision recorded" + (": " + " · ".join(label_bits) if label_bits else "")
    return df, summary, {"changes": [summary]}


# Declarative parameter schema per substep. The UI uses this to render
# threshold-tuning controls in the Applied Steps panel; backend functions
# read defaults from here via `_params_for`. Add new entries here to expose
# more knobs.
SUBSTEP_PARAM_SCHEMA: Dict[str, List[Dict[str, Any]]] = {
    "remove_duplicates": [],
    "fill_missing_numeric": [
        {
            "key": "missing_cap_pct", "label": "Missing-value cap (%)",
            "default": 50.0, "min": 0.0, "max": 100.0, "step": 5.0,
            "help": "Skip imputing any column whose share of missing values "
                    "exceeds this cap.",
        },
    ],
    "fill_missing_categorical": [
        {
            "key": "missing_cap_pct", "label": "Missing-value cap (%)",
            "default": 50.0, "min": 0.0, "max": 100.0, "step": 5.0,
            "help": "Skip imputing any column whose share of missing values "
                    "exceeds this cap.",
        },
    ],
    "clip_outliers": [
        {
            "key": "iqr_multiplier", "label": "IQR multiplier",
            "default": 1.5, "min": 0.5, "max": 5.0, "step": 0.1,
            "help": "Outlier fence width: lower = more aggressive, "
                    "higher = more permissive (Tukey default is 1.5).",
        },
        {
            "key": "clip_threshold_pct", "label": "Clip-vs-report cutoff (%)",
            "default": 5.0, "min": 0.0, "max": 100.0, "step": 1.0,
            "help": "If outliers in a column exceed this share of rows, "
                    "report them but leave values untouched.",
        },
    ],
}


# Unified registry. `params` describes user-editable structural parameters
# for substeps inserted via the UI (e.g. choosing a column to drop or
# rename). `kind` is one of: "column" (pick from current columns),
# "text" (free text input). Threshold-style numeric parameters live
# separately in `SUBSTEP_PARAM_SCHEMA` above.
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
    "record_decision": {
        "label": "Record Decision",
        "fn": record_decision_step,
        # Inserted programmatically by the Proactive Question Bar — not
        # offered in the manual "Insert step" picker, which is for
        # actions that change the data.
        "params": [],
        "insertable": False,
    },
}

# Transforms (Add Column from Examples, Merge, Split, Replace, Conditional,
# Group By) plug into the same registry so the unified plan, replay cache,
# and Applied Steps editor handle them with no special cases. They are
# inserted via the dedicated "Transform" expander, not the legacy "Insert
# step" picker, so each entry sets ``insertable=False``.
SUBSTEP_REGISTRY.update(TRANSFORM_REGISTRY)

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
    transform_label = transform_step_label(key, params)
    if transform_label is not None:
        return transform_label
    base = SUBSTEP_REGISTRY.get(key, {}).get("label", key)
    params = params or {}
    if key == "drop_column" and params.get("column"):
        return f"Drop Column · {params['column']}"
    if key == "rename_column" and params.get("column"):
        return f"Rename · {params['column']} → {params.get('new_name', '?')}"
    if key == "record_decision":
        bits = []
        if params.get("column"):
            bits.append(str(params["column"]))
        if params.get("decision"):
            bits.append(str(params["decision"]))
        return "Decision · " + " · ".join(bits) if bits else "Decision"
    return base


def run_substep(key: str, df: pd.DataFrame,
                params: Dict[str, Any] | None = None
                ) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    fn = SUBSTEP_REGISTRY[key]["fn"]
    return fn(df, **(params or {}))


def default_substep_params() -> Dict[str, Dict[str, Any]]:
    """Return the canonical default threshold params for every substep
    in the default cleaning plan."""
    return {
        key: {p["key"]: p["default"] for p in SUBSTEP_PARAM_SCHEMA.get(key, [])}
        for key in DEFAULT_CLEANING_PLAN
    }


def clean_data(df: pd.DataFrame,
               enabled: Dict[str, bool] | None = None,
               params: Dict[str, Dict[str, Any]] | None = None,
               ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Run the default cleaning pipeline as a sequence of named substeps.

    `enabled` optionally maps substep keys to bool toggles; missing keys
    default to True. `params` optionally maps substep keys to a per-substep
    params dict (e.g. `{"clip_outliers": {"iqr_multiplier": 2.0}}`); missing
    entries fall back to `SUBSTEP_PARAM_SCHEMA` defaults. Disabled substeps
    are pass-through. Returns the final cleaned dataframe and a report
    aggregated across all enabled substeps.
    """
    enabled = enabled or {}
    params = params or {}
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
        sub_params = params.get(key) or {}
        if on:
            current, summary, details = run_substep(key, current, sub_params)
            report['changes'].extend(details.get('changes', []))
        else:
            summary, details = "Disabled — pass through", {}
        report['substeps'].append({
            'key': key, 'label': label, 'enabled': on,
            'params': _params_for(key, sub_params),
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
