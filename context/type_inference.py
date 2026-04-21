"""Power Query-style automatic data type inference.

For each column we score it against a set of candidate types and pick the
most likely one. The output is consumable by the cleaner (to actually
cast values) and by the UI (to show the user the inferred schema with a
confidence score, just like Power Query's "Detected Types" step).

Detected types:
    integer, decimal, currency, percentage,
    date, datetime, time,
    boolean, text, id, categorical, empty
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Any, Optional

import numpy as np
import pandas as pd

# --------------------------------------------------------------------------
# Regexes & lookup tables
# --------------------------------------------------------------------------

_BOOL_TRUE = {"true", "false", "yes", "no", "y", "n", "0", "1",
              "نعم", "لا", "صح", "خطأ"}
_CURRENCY_SYMBOLS = "$€£¥₪₺₩₽﷼"
_CURRENCY_CODES = {"USD", "EUR", "GBP", "SAR", "AED", "JPY", "CNY",
                   "KWD", "QAR", "BHD", "OMR", "JOD", "EGP", "ILS", "TRY"}

_RE_INT = re.compile(r"^[+-]?\d{1,3}(?:[,\s]?\d{3})*$|^[+-]?\d+$")
_RE_DEC = re.compile(r"^[+-]?\d{1,3}(?:[,\s]?\d{3})*(?:\.\d+)?$|^[+-]?\d+\.\d+$|^[+-]?\.\d+$")
_RE_PCT = re.compile(r"^[+-]?\d+(?:\.\d+)?\s*%$")
_RE_CURR = re.compile(
    rf"^\s*(?:[{re.escape(_CURRENCY_SYMBOLS)}]|[A-Z]{{3}})?\s*"
    rf"[+-]?\d{{1,3}}(?:[,\s]?\d{{3}})*(?:\.\d+)?"
    rf"\s*(?:[{re.escape(_CURRENCY_SYMBOLS)}]|[A-Z]{{3}})?\s*$"
)
_RE_TIME = re.compile(r"^\d{1,2}:\d{2}(?::\d{2})?(?:\s?[APap][Mm])?$")
_RE_DATETIME_HINT = re.compile(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}[ T]\d{1,2}:\d{2}")
_RE_DATE_HINT = re.compile(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|^\d{8}$")

_NAME_HINTS_DATE = ("date", "dob", "birth", "created", "updated",
                    "تاريخ", "ميلاد", "إنشاء")
_NAME_HINTS_TIME = ("time", "hour", "وقت")
_NAME_HINTS_PCT = ("rate", "ratio", "pct", "percent", "نسبة", "معدل")
_NAME_HINTS_CURR = ("price", "cost", "amount", "salary", "revenue",
                    "balance", "total", "سعر", "تكلفة", "مبلغ", "راتب")
_NAME_HINTS_ID = ("id", "code", "sku", "ref", "رقم", "كود")


# --------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------

@dataclass
class ColumnType:
    column: str
    inferred_type: str
    confidence: float
    sample_values: list
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["confidence"] = round(float(self.confidence), 3)
        return d


# --------------------------------------------------------------------------
# Scorers
# --------------------------------------------------------------------------

def _strip(v: str) -> str:
    return str(v).strip()


def _score_against(values: pd.Series, predicate) -> float:
    if values.empty:
        return 0.0
    hits = sum(1 for v in values if predicate(v))
    return hits / len(values)


def _is_int(v: str) -> bool:
    return bool(_RE_INT.match(_strip(v)))


def _is_dec(v: str) -> bool:
    s = _strip(v)
    return bool(_RE_DEC.match(s)) and not _RE_INT.match(s)


def _is_pct(v: str) -> bool:
    return bool(_RE_PCT.match(_strip(v)))


def _is_curr(v: str) -> bool:
    s = _strip(v)
    if not s:
        return False
    has_symbol = any(sym in s for sym in _CURRENCY_SYMBOLS)
    has_code = any(code in s.upper().split() for code in _CURRENCY_CODES)
    if not (has_symbol or has_code):
        return False
    return bool(_RE_CURR.match(s))


def _is_time(v: str) -> bool:
    return bool(_RE_TIME.match(_strip(v)))


def _is_bool(v: str) -> bool:
    return _strip(v).lower() in _BOOL_TRUE


def _is_datetime_str(v: str) -> bool:
    return bool(_RE_DATETIME_HINT.search(_strip(v)))


def _is_date_str(v: str) -> bool:
    s = _strip(v)
    if _RE_DATETIME_HINT.search(s):
        return False
    return bool(_RE_DATE_HINT.search(s))


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def infer_column_type(series: pd.Series, name_hint: str = "") -> ColumnType:
    """Infer the most likely Power Query-style type for a single column."""
    name_l = (name_hint or series.name or "").lower() if hasattr(series, "name") else ""
    raw = series.dropna()
    sample_values = [str(x) for x in raw.head(5).tolist()]

    if raw.empty:
        return ColumnType(str(series.name), "empty", 1.0, [], "Column is empty")

    # Already-typed pandas dtypes win immediately
    if pd.api.types.is_datetime64_any_dtype(series):
        kind = "datetime" if (raw.dt.time != pd.Timestamp("00:00:00").time()).any() else "date"
        return ColumnType(str(series.name), kind, 1.0, sample_values, "Native datetime dtype")
    if pd.api.types.is_bool_dtype(series):
        return ColumnType(str(series.name), "boolean", 1.0, sample_values, "Native bool dtype")
    if pd.api.types.is_integer_dtype(series):
        nunique = series.nunique(dropna=True)
        if any(h in name_l for h in _NAME_HINTS_ID) and nunique == series.dropna().shape[0]:
            return ColumnType(str(series.name), "id", 1.0, sample_values, "Unique integer ID")
        return ColumnType(str(series.name), "integer", 1.0, sample_values, "Native int dtype")
    if pd.api.types.is_float_dtype(series):
        if any(h in name_l for h in _NAME_HINTS_PCT):
            return ColumnType(str(series.name), "percentage", 0.95, sample_values, "Float + name hint")
        if any(h in name_l for h in _NAME_HINTS_CURR):
            return ColumnType(str(series.name), "currency", 0.9, sample_values, "Float + name hint")
        return ColumnType(str(series.name), "decimal", 1.0, sample_values, "Native float dtype")

    # Object / string columns — score against each candidate
    str_vals = raw.astype(str).head(200)

    scores = {
        "boolean":    _score_against(str_vals, _is_bool),
        "percentage": _score_against(str_vals, _is_pct),
        "currency":   _score_against(str_vals, _is_curr),
        "integer":    _score_against(str_vals, _is_int),
        "decimal":    _score_against(str_vals, _is_dec),
        "datetime":   _score_against(str_vals, _is_datetime_str),
        "date":       _score_against(str_vals, _is_date_str),
        "time":       _score_against(str_vals, _is_time),
    }

    # Apply name-hint boosts (small, never override a strong signal)
    if any(h in name_l for h in _NAME_HINTS_DATE):
        scores["date"] = min(1.0, scores["date"] + 0.15)
        scores["datetime"] = min(1.0, scores["datetime"] + 0.10)
    if any(h in name_l for h in _NAME_HINTS_TIME):
        scores["time"] = min(1.0, scores["time"] + 0.15)
    if any(h in name_l for h in _NAME_HINTS_PCT):
        scores["percentage"] = min(1.0, scores["percentage"] + 0.15)
    if any(h in name_l for h in _NAME_HINTS_CURR):
        scores["currency"] = min(1.0, scores["currency"] + 0.15)

    best = max(scores, key=scores.get)
    best_score = scores[best]

    # Numeric tie-break: integer beats decimal only if (almost) all values fit int
    if best == "decimal" and scores["integer"] >= 0.95:
        best = "integer"
        best_score = scores["integer"]

    if best_score < 0.70:
        # Categorical vs free text
        nunique = raw.nunique()
        ratio = nunique / len(raw)
        if nunique <= 25 and ratio < 0.5:
            return ColumnType(str(series.name), "categorical",
                              round(1.0 - ratio, 3), sample_values,
                              f"{nunique} unique values")
        if any(h in name_l for h in _NAME_HINTS_ID) and ratio > 0.95:
            return ColumnType(str(series.name), "id", 0.9, sample_values, "High-cardinality identifier")
        return ColumnType(str(series.name), "text", 1.0, sample_values, "Free-form text")

    return ColumnType(str(series.name), best, best_score, sample_values, "Pattern match")


def infer_schema(df: pd.DataFrame) -> list[ColumnType]:
    """Run inference on every column. Returns a list of ColumnType."""
    return [infer_column_type(df[c], name_hint=str(c)) for c in df.columns]


def schema_to_dataframe(schema: list[ColumnType]) -> pd.DataFrame:
    """For showing the inferred schema in the UI as a table."""
    if not schema:
        return pd.DataFrame(columns=["column", "inferred_type", "confidence", "sample_values", "notes"])
    rows = [s.to_dict() for s in schema]
    out = pd.DataFrame(rows)
    out["sample_values"] = out["sample_values"].apply(lambda xs: ", ".join(map(str, xs[:3])))
    return out[["column", "inferred_type", "confidence", "sample_values", "notes"]]


# --------------------------------------------------------------------------
# Casting
# --------------------------------------------------------------------------

def _clean_numeric(s: pd.Series) -> pd.Series:
    return (s.astype(str)
              .str.replace(",", "", regex=False)
              .str.replace(r"\s+", "", regex=True))


def cast_column(series: pd.Series, target_type: str) -> pd.Series:
    """Coerce a single column to its inferred type. Uncoercible cells become NaN/NaT."""
    t = (target_type or "text").lower()
    try:
        if t == "integer":
            return pd.to_numeric(_clean_numeric(series), errors="coerce").astype("Int64")
        if t == "decimal":
            return pd.to_numeric(_clean_numeric(series), errors="coerce")
        if t == "percentage":
            cleaned = (series.astype(str).str.replace("%", "", regex=False))
            return pd.to_numeric(_clean_numeric(cleaned), errors="coerce") / 100.0
        if t == "currency":
            cleaned = series.astype(str)
            for sym in _CURRENCY_SYMBOLS:
                cleaned = cleaned.str.replace(sym, "", regex=False)
            for code in _CURRENCY_CODES:
                cleaned = cleaned.str.replace(rf"\b{code}\b", "", regex=True)
            return pd.to_numeric(_clean_numeric(cleaned), errors="coerce")
        if t in ("date", "datetime"):
            return pd.to_datetime(series, errors="coerce", dayfirst=True)
        if t == "time":
            return pd.to_datetime(series, errors="coerce", format=None).dt.time
        if t == "boolean":
            mapping = {"true": True, "yes": True, "y": True, "1": True, "نعم": True, "صح": True,
                       "false": False, "no": False, "n": False, "0": False, "لا": False, "خطأ": False}
            return series.astype(str).str.strip().str.lower().map(mapping)
        return series.astype(str)
    except Exception:
        return series


def apply_schema(df: pd.DataFrame, schema: list[ColumnType]) -> pd.DataFrame:
    """Return a copy of df with every column cast to its inferred type."""
    out = df.copy()
    for s in schema:
        if s.column in out.columns and s.inferred_type not in ("text", "empty", "id", "categorical"):
            out[s.column] = cast_column(out[s.column], s.inferred_type)
    return out
