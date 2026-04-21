"""Power Query-style column-shaping transforms.

Each function below is registered as a substep in `data_cleaner.SUBSTEP_REGISTRY`
and reused by the Applied Steps replay engine: it takes the current dataframe
plus a JSON-friendly params dict and returns ``(new_df, summary, details)``.
That keeps the universal reorder / toggle / remove plumbing from Task #27 and
the per-prefix replay cache from Task #31 working with no special cases.

The six transforms exposed here are: Add Column from Examples, Merge Columns,
Split Column, Replace Values, Conditional Column, and Group By. They are
declared as ``insertable=False`` in the registry so the legacy "Insert step"
picker keeps showing only cleaning substeps; transforms are inserted via the
dedicated "Transform" expander on the Overview tab.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Add Column from Examples
# --------------------------------------------------------------------------

# Inferable operations. Each (op, op_params) is deterministic — once the
# inference picks one we bake it into the substep params so replay is a
# pure function of (op, op_params) and can be cached safely.

_CONCAT_SEPARATORS = ["", " ", "-", "_", "/", ", ", " - "]
_SPLIT_DELIMITERS = [" ", "-", "_", "/", ".", "@", ",", ":"]
_ARITH_OPS = ["+", "-", "*", "/"]
_CASE_KINDS = ["upper", "lower", "title"]

# Catalogue of regex extraction patterns inference will try in addition to
# the structural ops. Covers the common Power Query "extract before /
# after delimiter" and "first / last numeric or alphabetic run" cases.
_REGEX_PATTERNS = [
    r"^([^@]+)", r"^([^\.]+)", r"^([^/]+)", r"^([^_]+)",
    r"^([^\- ]+)", r"^(\w+)", r"^(\d+)", r"^([A-Za-z]+)",
    r"([^@]+)$", r"([^\.]+)$", r"([^/]+)$", r"([^_]+)$",
    r"(\w+)$", r"(\d+)$", r"([A-Za-z]+)$",
    r"(\d+)", r"([A-Z][a-z]+)", r"([A-Za-z]+)",
]


def _safe_str(series: pd.Series) -> pd.Series:
    return series.astype(object).where(series.notna(), other="").astype(str)


def _apply_examples_op(df: pd.DataFrame, source_columns: List[str], op: str,
                       op_params: Dict[str, Any]) -> pd.Series:
    """Run a baked Add-Column-from-Examples op against ``df`` and return the
    resulting series. Caller is responsible for assignment + missing-column
    short-circuits."""
    op_params = op_params or {}
    cols = [c for c in source_columns if c in df.columns]
    if not cols:
        return pd.Series([None] * len(df), index=df.index)

    if op == "concat":
        sep = str(op_params.get("separator", ""))
        result = _safe_str(df[cols[0]])
        for c in cols[1:]:
            result = result + sep + _safe_str(df[c])
        return result

    if op == "case":
        kind = op_params.get("kind", "upper")
        s = _safe_str(df[cols[0]])
        if kind == "upper":
            return s.str.upper()
        if kind == "lower":
            return s.str.lower()
        if kind == "title":
            return s.str.title()
        return s

    if op == "slice":
        start = int(op_params.get("start", 0))
        end_raw = op_params.get("end", None)
        end = int(end_raw) if end_raw is not None else None
        return _safe_str(df[cols[0]]).str.slice(start, end)

    if op == "split_take":
        delim = str(op_params.get("delimiter", " "))
        idx = int(op_params.get("index", 0))
        return _safe_str(df[cols[0]]).str.split(delim).str[idx]

    if op == "regex_extract":
        pattern = str(op_params.get("pattern", ""))
        if not pattern:
            return pd.Series([None] * len(df), index=df.index)
        try:
            return _safe_str(df[cols[0]]).str.extract(pattern, expand=False)
        except Exception:
            return pd.Series([None] * len(df), index=df.index)

    if op == "arithmetic":
        operator = op_params.get("operator", "+")
        a = pd.to_numeric(df[cols[0]], errors="coerce")
        b = pd.to_numeric(df[cols[1]], errors="coerce") if len(cols) > 1 else None
        if b is None:
            return a
        if operator == "+":
            return a + b
        if operator == "-":
            return a - b
        if operator == "*":
            return a * b
        if operator == "/":
            return a / b
        return a

    return pd.Series([None] * len(df), index=df.index)


def add_column_from_examples_step(
    df: pd.DataFrame,
    source_columns: Optional[List[str]] = None,
    op: Optional[str] = None,
    op_params: Optional[Dict[str, Any]] = None,
    new_column: Optional[str] = None,
    **_params,
) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    if not source_columns or not op or not new_column:
        return df.copy(), "Skipped — incomplete params", {"changes": []}
    out = df.copy()
    out[new_column] = _apply_examples_op(out, list(source_columns), op, op_params or {})
    summary = f"Added column `{new_column}` ({op})"
    return out, summary, {"changes": [summary]}


def infer_examples_op(
    df: pd.DataFrame,
    source_columns: List[str],
    examples: List[Tuple[int, str]],
) -> Tuple[Optional[str], Optional[Dict[str, Any]], float]:
    """Try the catalogue of operations against the user-typed examples and
    return the best match as (op, op_params, coverage). Coverage is the
    fraction of examples the op produced exactly.

    Inference runs against a small head sample so it stays cheap on million-
    row frames; row indices in ``examples`` must point inside that sample.
    """
    if not source_columns or not examples:
        return None, None, 0.0
    src_cols = [c for c in source_columns if c in df.columns]
    if not src_cols:
        return None, None, 0.0

    # Bound the inference workload — examples reference small row indices
    # by construction (the form only shows the first few rows).
    max_row = max((idx for idx, _ in examples), default=0)
    sample = df.head(max(50, max_row + 1)).copy().reset_index(drop=True)

    candidates: List[Tuple[str, Dict[str, Any], float]] = []

    def _score(op: str, op_params: Dict[str, Any]) -> float:
        try:
            produced = _apply_examples_op(sample, src_cols, op, op_params)
        except Exception:
            return 0.0
        hits = 0
        for row_idx, target in examples:
            if 0 <= row_idx < len(sample):
                val = produced.iloc[row_idx]
                if pd.notna(val) and str(val) == str(target):
                    hits += 1
        return hits / len(examples)

    if len(src_cols) >= 2:
        for sep in _CONCAT_SEPARATORS:
            candidates.append(("concat", {"separator": sep},
                               _score("concat", {"separator": sep})))
        for opx in _ARITH_OPS:
            candidates.append(("arithmetic", {"operator": opx},
                               _score("arithmetic", {"operator": opx})))

    for kind in _CASE_KINDS:
        candidates.append(("case", {"kind": kind}, _score("case", {"kind": kind})))

    for delim in _SPLIT_DELIMITERS:
        for idx in range(3):
            params = {"delimiter": delim, "index": idx}
            candidates.append(("split_take", params, _score("split_take", params)))

    # Prefix slice (start ≥ 0) and suffix slice (start < 0) — covers both
    # "first N chars" and "last N chars" extraction patterns. Pandas /
    # Python slicing handles negative starts natively.
    for start in range(0, 6):
        for length in (1, 2, 3, 4, 5):
            params = {"start": start, "end": start + length}
            candidates.append(("slice", params, _score("slice", params)))
    for length in (1, 2, 3, 4, 5, 6, 7):
        params = {"start": -length, "end": None}
        candidates.append(("slice", params, _score("slice", params)))

    # Regex extract — try the catalogue plus literal-target patterns
    # derived from the user's typed examples (so e.g. typing "ada" from
    # "ada@x.com" can match a literal extraction even outside the preset
    # delimiters).
    derived_patterns: List[str] = []
    for _, target in examples:
        t = str(target or "").strip()
        if t and len(t) <= 64:
            derived_patterns.append(rf"({re.escape(t)})")
    seen_patterns = set()
    for pat in list(_REGEX_PATTERNS) + derived_patterns:
        if pat in seen_patterns:
            continue
        seen_patterns.add(pat)
        candidates.append(("regex_extract", {"pattern": pat},
                           _score("regex_extract", {"pattern": pat})))

    candidates.sort(key=lambda x: x[2], reverse=True)
    if candidates and candidates[0][2] > 0.0:
        op, op_params, cov = candidates[0]
        return op, op_params, cov
    return None, None, 0.0


# --------------------------------------------------------------------------
# Merge Columns
# --------------------------------------------------------------------------

def merge_columns_step(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    separator: str = " ",
    new_column: Optional[str] = None,
    keep_originals: bool = True,
    **_params,
) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    if not columns or not new_column:
        return df.copy(), "Skipped — incomplete params", {"changes": []}
    cols = [c for c in columns if c in df.columns]
    if not cols:
        return df.copy(), "Skipped — no source columns present", {"changes": []}
    out = df.copy()
    sep = "" if separator is None else str(separator)
    result = _safe_str(out[cols[0]])
    for c in cols[1:]:
        result = result + sep + _safe_str(out[c])
    out[new_column] = result
    if not keep_originals:
        out = out.drop(columns=cols)
    summary = f"Merged {len(cols)} columns → `{new_column}`"
    return out, summary, {"changes": [summary]}


# --------------------------------------------------------------------------
# Split Column
# --------------------------------------------------------------------------

def split_column_step(
    df: pd.DataFrame,
    column: Optional[str] = None,
    mode: str = "delimiter",
    delimiter: str = ",",
    width: int = 1,
    new_column_prefix: Optional[str] = None,
    keep_original: bool = True,
    **_params,
) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    if not column or column not in df.columns:
        return df.copy(), f"Skipped — column `{column}` missing", {"changes": []}
    out = df.copy()
    prefix = new_column_prefix or f"{column}_part"
    s = _safe_str(out[column])
    if mode == "width":
        w = max(1, int(width or 1))
        max_len = int(s.str.len().max() or 0)
        n_parts = max(1, (max_len + w - 1) // w)
        parts = pd.DataFrame(
            {i: s.str.slice(i * w, (i + 1) * w) for i in range(n_parts)},
            index=out.index,
        )
    else:
        parts = s.str.split(delimiter or ",", expand=True)
    parts.columns = [f"{prefix}_{i + 1}" for i in range(parts.shape[1])]
    out = pd.concat([out, parts], axis=1)
    if not keep_original:
        out = out.drop(columns=[column])
    summary = f"Split `{column}` into {parts.shape[1]} columns"
    return out, summary, {"changes": [summary]}


# --------------------------------------------------------------------------
# Replace Values
# --------------------------------------------------------------------------

def replace_values_step(
    df: pd.DataFrame,
    column: Optional[str] = None,
    find: str = "",
    replace: str = "",
    whole_cell: bool = False,
    case_sensitive: bool = True,
    **_params,
) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    if not column or column not in df.columns:
        return df.copy(), f"Skipped — column `{column}` missing", {"changes": []}
    if find == "":
        return df.copy(), "Skipped — empty find pattern", {"changes": []}
    out = df.copy()
    src = out[column]
    find_s = str(find)
    repl_s = "" if replace is None else str(replace)
    if whole_cell:
        if case_sensitive:
            mask = src.astype(str) == find_s
        else:
            mask = src.astype(str).str.lower() == find_s.lower()
        n = int(mask.sum())
        if n:
            out.loc[mask, column] = repl_s
    else:
        s_str = src.astype(str)
        flags = 0 if case_sensitive else re.IGNORECASE
        new = s_str.str.replace(re.escape(find_s), repl_s, regex=True, flags=flags)
        n = int((new != s_str).sum())
        out[column] = new
    summary = f"Replaced {n} value(s) in `{column}`: `{find_s}` → `{repl_s}`"
    return out, summary, {"changes": [summary]}


# --------------------------------------------------------------------------
# Conditional Column
# --------------------------------------------------------------------------

_COND_OPS = ["==", "!=", "<", "<=", ">", ">=",
             "contains", "starts_with", "ends_with", "is_null"]


def _eval_condition(series: pd.Series, op: str, value: Any) -> pd.Series:
    try:
        if op == "is_null":
            return series.isna()
        s = series.astype(str)
        v = "" if value is None else str(value)
        if op == "==":
            return s == v
        if op == "!=":
            return s != v
        if op == "contains":
            return s.str.contains(v, na=False, regex=False)
        if op == "starts_with":
            return s.str.startswith(v, na=False)
        if op == "ends_with":
            return s.str.endswith(v, na=False)
        # Numeric comparators
        num = pd.to_numeric(series, errors="coerce")
        try:
            target = float(value)
        except (TypeError, ValueError):
            return pd.Series([False] * len(series), index=series.index)
        if op == "<":
            return num < target
        if op == "<=":
            return num <= target
        if op == ">":
            return num > target
        if op == ">=":
            return num >= target
    except Exception:
        return pd.Series([False] * len(series), index=series.index)
    return pd.Series([False] * len(series), index=series.index)


def conditional_column_step(
    df: pd.DataFrame,
    source_column: Optional[str] = None,
    rules: Optional[List[Dict[str, Any]]] = None,
    else_value: Any = None,
    new_column: Optional[str] = None,
    **_params,
) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    if not new_column or not rules:
        return df.copy(), "Skipped — incomplete params", {"changes": []}
    if source_column and source_column not in df.columns:
        return df.copy(), f"Skipped — column `{source_column}` missing", {"changes": []}
    out = df.copy()
    src = out[source_column] if source_column else pd.Series([None] * len(out), index=out.index)
    result = pd.Series([else_value] * len(out), index=out.index, dtype=object)
    matched = pd.Series([False] * len(out), index=out.index)
    for rule in rules:
        op = rule.get("op", "==")
        cond = _eval_condition(src, op, rule.get("value")).fillna(False)
        apply_mask = cond & ~matched
        result.loc[apply_mask] = rule.get("then")
        matched = matched | cond
    out[new_column] = result
    summary = f"Conditional column `{new_column}` ({len(rules)} rule(s))"
    return out, summary, {"changes": [summary]}


# --------------------------------------------------------------------------
# Group By
# --------------------------------------------------------------------------

VALID_AGGS = ["sum", "mean", "count", "min", "max", "first", "nunique"]


def group_by_step(
    df: pd.DataFrame,
    keys: Optional[List[str]] = None,
    aggregations: Optional[List[Dict[str, Any]]] = None,
    **_params,
) -> Tuple[pd.DataFrame, str, Dict[str, Any]]:
    if not keys or not aggregations:
        return df.copy(), "Skipped — incomplete params", {"changes": []}
    keys_present = [k for k in keys if k in df.columns]
    if not keys_present:
        return df.copy(), "Skipped — no group keys present", {"changes": []}

    grouped = df.groupby(keys_present, dropna=False)
    parts: List[pd.Series] = []
    used_aliases: set = set()
    for a in aggregations:
        col = a.get("column")
        agg = (a.get("agg") or "sum").lower()
        if agg not in VALID_AGGS or not col or col not in df.columns:
            continue
        alias = a.get("alias") or f"{col}_{agg}"
        # Deduplicate aliases so two aggregations can target the same column.
        base = alias
        suffix = 2
        while alias in used_aliases or alias in keys_present:
            alias = f"{base}_{suffix}"
            suffix += 1
        used_aliases.add(alias)
        try:
            if agg == "count":
                s = grouped[col].count()
            elif agg == "first":
                s = grouped[col].first()
            elif agg == "nunique":
                s = grouped[col].nunique()
            else:
                s = grouped[col].agg(agg)
            s.name = alias
            parts.append(s)
        except Exception:
            continue
    if not parts:
        return df.copy(), "Skipped — no valid aggregations", {"changes": []}
    out = pd.concat(parts, axis=1).reset_index()
    summary = (f"Grouped by {', '.join(keys_present)} "
               f"({len(parts)} aggregation(s), {len(out):,} groups)")
    return out, summary, {"changes": [summary]}


# --------------------------------------------------------------------------
# Registry payload — imported by data_cleaner.py to extend SUBSTEP_REGISTRY
# without creating an import cycle. Each entry is structurally identical to
# the cleaning substeps so the unified plan / replay cache work unchanged.
# --------------------------------------------------------------------------

TRANSFORM_REGISTRY: Dict[str, Dict[str, Any]] = {
    "add_column_from_examples": {
        "label": "Add Column from Examples",
        "fn": add_column_from_examples_step,
        "params": [],
        "insertable": False,
        "transform": True,
    },
    "merge_columns": {
        "label": "Merge Columns",
        "fn": merge_columns_step,
        "params": [],
        "insertable": False,
        "transform": True,
    },
    "split_column": {
        "label": "Split Column",
        "fn": split_column_step,
        "params": [],
        "insertable": False,
        "transform": True,
    },
    "replace_values": {
        "label": "Replace Values",
        "fn": replace_values_step,
        "params": [],
        "insertable": False,
        "transform": True,
    },
    "conditional_column": {
        "label": "Conditional Column",
        "fn": conditional_column_step,
        "params": [],
        "insertable": False,
        "transform": True,
    },
    "group_by": {
        "label": "Group By",
        "fn": group_by_step,
        "params": [],
        "insertable": False,
        "transform": True,
    },
}


def transform_step_label(key: str, params: Dict[str, Any] | None = None) -> Optional[str]:
    """Return a Power Query-style scannable label, or None if the key isn't
    a transform (so callers can fall back to the cleaning labeller)."""
    if key not in TRANSFORM_REGISTRY:
        return None
    p = params or {}
    if key == "add_column_from_examples":
        return f"Add Column · {p.get('new_column', '?')}"
    if key == "merge_columns":
        cols = list(p.get("columns") or [])
        head = " + ".join(cols[:2]) + (f" + … (+{len(cols) - 2})" if len(cols) > 2 else "")
        return f"Merge Columns · {head} → {p.get('new_column', '?')}"
    if key == "split_column":
        mode = p.get("mode", "delimiter")
        if mode == "width":
            return f"Split Column · {p.get('column', '?')} (every {p.get('width', 1)} chars)"
        return f"Split Column · {p.get('column', '?')} by `{p.get('delimiter', ',')}`"
    if key == "replace_values":
        return (f"Replace · {p.get('column', '?')} `"
                f"{p.get('find', '')} → {p.get('replace', '')}`")
    if key == "conditional_column":
        n = len(p.get("rules") or [])
        return f"Conditional · {p.get('new_column', '?')} ({n} rule{'s' if n != 1 else ''})"
    if key == "group_by":
        keys = list(p.get("keys") or [])
        return f"Group By · {', '.join(keys) if keys else '?'}"
    return TRANSFORM_REGISTRY[key]["label"]
