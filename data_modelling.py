"""Power BI-style data modelling: relationship suggestion + joined view.

This module is intentionally pure-Python (no Streamlit imports) so the
suggestion engine and join materialisation can be unit-tested directly
and reused outside the dashboard.

Two surfaces:

  * ``suggest_relationships(left, right, ...)`` — score every pair of
    columns across two dataframes on three independent signals:

        - name similarity (case-folded exact + Levenshtein ratio)
        - dtype compatibility (numeric ↔ numeric, date ↔ date, etc.)
        - value overlap (Jaccard on a 1k-row sample from each side)

    Returns a ranked list of ``RelationshipSuggestion`` records.

  * ``materialize_join(left, right, left_col, right_col, join_type,
    suffixes=...)`` — produce the joined dataframe. Cardinality is
    inferred (1:1 / 1:N / N:N) from how unique the join keys are on each
    side; this is exposed because the UI shows it next to the suggestion
    and it doubles as a safety check ("you picked an N:N join, expect
    explosion").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# Data containers
# --------------------------------------------------------------------------

@dataclass
class RelationshipSuggestion:
    left_column: str
    right_column: str
    name_score: float       # 0..1
    dtype_score: float      # 0..1
    overlap_score: float    # 0..1 Jaccard on sampled values
    cardinality: str        # "1:1" / "1:N" / "N:1" / "N:N"
    confidence: float       # weighted combination

    def to_dict(self) -> dict:
        return {
            "left_column": self.left_column,
            "right_column": self.right_column,
            "name_score": round(self.name_score, 3),
            "dtype_score": round(self.dtype_score, 3),
            "overlap_score": round(self.overlap_score, 3),
            "cardinality": self.cardinality,
            "confidence": round(self.confidence, 3),
        }


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _levenshtein(a: str, b: str) -> int:
    """Plain dynamic-programming edit distance — no dependency."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            curr[j] = min(curr[j - 1] + 1,
                          prev[j] + 1,
                          prev[j - 1] + cost)
        prev = curr
    return prev[-1]


def _name_similarity(a: str, b: str) -> float:
    """Case-folded exact match → 1.0; otherwise normalised edit distance."""
    a = (a or "").strip().lower()
    b = (b or "").strip().lower()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # Common identifier patterns: "id" matches "customer_id", "userId"
    # matches "user_id". Strip non-alphanumerics and compare.
    norm_a = "".join(ch for ch in a if ch.isalnum())
    norm_b = "".join(ch for ch in b if ch.isalnum())
    if norm_a and norm_a == norm_b:
        return 1.0
    if norm_a and norm_b and (norm_a.endswith(norm_b) or norm_b.endswith(norm_a)):
        # e.g. "customerid" endswith "id" — partial match worth 0.65
        shorter = min(len(norm_a), len(norm_b))
        longer = max(len(norm_a), len(norm_b))
        return 0.5 + 0.4 * (shorter / longer)
    dist = _levenshtein(a, b)
    longest = max(len(a), len(b))
    return max(0.0, 1.0 - dist / longest)


_NUMERIC_KINDS = {"i", "u", "f"}


def _dtype_family(series: pd.Series) -> str:
    """Bucket the column's dtype into one of a handful of compatibility
    families so cross-dataset numeric/date/text matches all line up."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    if pd.api.types.is_bool_dtype(series):
        return "bool"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    return "text"


def _dtype_score(left: pd.Series, right: pd.Series) -> float:
    lf = _dtype_family(left)
    rf = _dtype_family(right)
    if lf == rf:
        return 1.0
    # Numeric ↔ text where the text is parseable as numeric is still
    # often a valid join (legacy IDs stored as strings on one side). We
    # don't run a full coerce pass here — that's expensive on big frames
    # — but a partial credit lets the suggestion surface so the user can
    # decide. The overlap score will downrank false matches anyway.
    if {lf, rf} == {"numeric", "text"}:
        return 0.45
    if {lf, rf} == {"datetime", "text"}:
        return 0.35
    return 0.0


def _sample_values(series: pd.Series, n: int) -> set:
    """Return up to *n* non-null distinct stringified values from a series.
    The string coercion lets us compare numeric ids against the same
    values stored as text on the other side."""
    s = series.dropna()
    if len(s) == 0:
        return set()
    if len(s) > n:
        # Deterministic head sample is faster than random for large frames
        # and works fine for Jaccard since we just need representative
        # values, not a true random sample.
        s = s.head(n)
    out: set[str] = set()
    for v in s:
        try:
            sv = str(v).strip()
        except Exception:
            continue
        if sv:
            out.add(sv)
    return out


def _overlap_score(left: pd.Series, right: pd.Series, sample_size: int) -> float:
    """Jaccard similarity between sampled value sets. We don't divide by
    the smaller side because a column where every value matches but the
    other side has 100x more values is still a valid 1:N join — Jaccard
    naturally captures that without overstating it."""
    a = _sample_values(left, sample_size)
    b = _sample_values(right, sample_size)
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    if union == 0:
        return 0.0
    # Bias slightly towards "all of one side is contained in the other"
    # (typical FK case): if every sampled left value appears in right we
    # should not penalise the join just because right has many extra
    # values. Use max(jaccard, containment_min) so containment lifts the
    # score for true FK relationships.
    containment = inter / min(len(a), len(b))
    jaccard = inter / union
    return max(jaccard, 0.7 * containment)


def _cardinality(left: pd.Series, right: pd.Series) -> str:
    """Approximate 1:1 / 1:N / N:1 / N:N from key uniqueness."""
    l_unique = (left.nunique(dropna=True) == len(left.dropna()))
    r_unique = (right.nunique(dropna=True) == len(right.dropna()))
    if l_unique and r_unique:
        return "1:1"
    if l_unique and not r_unique:
        return "1:N"
    if not l_unique and r_unique:
        return "N:1"
    return "N:N"


# --------------------------------------------------------------------------
# Public API: suggest_relationships
# --------------------------------------------------------------------------

# Weights tuned so that (a) a perfect-name + perfect-overlap + same-dtype
# pair clears 0.95 (will be auto-checked in the UI), and (b) any single
# weak signal alone never crosses the 0.55 "show as suggestion" cutoff.
_NAME_W = 0.30
_DTYPE_W = 0.20
_OVERLAP_W = 0.50

SUGGEST_THRESHOLD = 0.45


def suggest_relationships(
    left: pd.DataFrame,
    right: pd.DataFrame,
    sample_size: int = 1000,
    min_confidence: float = SUGGEST_THRESHOLD,
    max_results: int = 12,
) -> list[RelationshipSuggestion]:
    """Score every (left_col, right_col) pair and return the top
    candidates above ``min_confidence``, sorted descending.

    The function is deterministic given the input frames + ``sample_size``.
    """
    if left is None or right is None or left.empty or right.empty:
        return []

    suggestions: list[RelationshipSuggestion] = []
    for lc in left.columns:
        ls = left[lc]
        for rc in right.columns:
            rs = right[rc]
            n = _name_similarity(str(lc), str(rc))
            d = _dtype_score(ls, rs)
            # Skip the expensive overlap pass when neither name nor dtype
            # gave us anything — saves a big-O hit on wide frames.
            if n < 0.25 and d < 0.45:
                continue
            o = _overlap_score(ls, rs, sample_size)
            confidence = (_NAME_W * n + _DTYPE_W * d + _OVERLAP_W * o)
            if confidence < min_confidence:
                continue
            card = _cardinality(ls, rs)
            suggestions.append(RelationshipSuggestion(
                left_column=str(lc), right_column=str(rc),
                name_score=n, dtype_score=d, overlap_score=o,
                cardinality=card, confidence=confidence,
            ))
    suggestions.sort(key=lambda s: s.confidence, reverse=True)
    return suggestions[:max_results]


# --------------------------------------------------------------------------
# Public API: materialize_join
# --------------------------------------------------------------------------

VALID_JOINS = ("inner", "left", "right", "outer")


def materialize_join(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_col: str,
    right_col: str,
    join_type: str = "left",
    left_label: str = "left",
    right_label: str = "right",
) -> pd.DataFrame:
    """Run the join and return the merged dataframe.

    Both join columns are coerced to string just for the merge so a
    numeric ID stored as text on one side still matches the integer on
    the other. The original dtypes of every other column are preserved.
    Overlapping non-key column names get suffixed with the table labels
    so the user can tell sides apart.
    """
    if left_col not in left.columns:
        raise ValueError(f"Left column '{left_col}' not in left dataframe.")
    if right_col not in right.columns:
        raise ValueError(f"Right column '{right_col}' not in right dataframe.")
    jt = (join_type or "left").lower()
    if jt not in VALID_JOINS:
        raise ValueError(f"join_type must be one of {VALID_JOINS}.")

    left_work = left.copy()
    right_work = right.copy()
    # Coerce keys to stripped strings so a numeric ID stored as text on
    # one side still matches the integer on the other — but preserve
    # NaN so that null keys never join (standard SQL/BI semantics:
    # NULL ≠ NULL in equality joins). Without this guard, both sides'
    # missing values would collapse to the literal "nan" string and
    # match each other, exploding the result with bogus rows.
    def _key(series: pd.Series, side: str) -> pd.Series:
        # Whole-number floats need to render as ints ("1" not "1.0") so
        # they line up with int columns or "1"-style text on the other
        # side. This is the most common cross-source mismatch (a column
        # gets float dtype the moment it has any nulls in pandas).
        if pd.api.types.is_float_dtype(series):
            def _fmt(v):
                if pd.isna(v):
                    return ""
                if float(v).is_integer():
                    return str(int(v))
                return str(v).strip()
            coerced = series.map(_fmt)
        else:
            coerced = series.astype(str).str.strip()
        # Empty strings + null source values become per-row unique
        # sentinels (`__dv_null_<side>_<idx>__`) so they cannot collide
        # with any real value or with each other across the merge.
        null_mask = series.isna() | coerced.eq("") | coerced.eq("nan") | coerced.eq("None")
        if null_mask.any():
            sentinels = [f"__dv_null_{side}_{i}__" for i in series.index[null_mask]]
            coerced.loc[null_mask] = sentinels
        return coerced

    left_work["__dv_join_key__"] = _key(left_work[left_col], "L")
    right_work["__dv_join_key__"] = _key(right_work[right_col], "R")

    suffixes = (f"_{left_label}", f"_{right_label}")
    merged = pd.merge(
        left_work, right_work,
        on="__dv_join_key__",
        how=jt,
        suffixes=suffixes,
    )
    merged = merged.drop(columns=["__dv_join_key__"])
    return merged


# --------------------------------------------------------------------------
# Public API: validate_relationship
# --------------------------------------------------------------------------

def validate_relationship(
    left: pd.DataFrame,
    right: pd.DataFrame,
    left_col: str,
    right_col: str,
) -> dict:
    """Cheap diagnostics returned alongside a manual relationship so the
    UI can warn about empty joins or huge fan-out before materialising."""
    out = {"left_rows": int(len(left)), "right_rows": int(len(right))}
    if left_col not in left.columns or right_col not in right.columns:
        out["error"] = "One or both join columns no longer exist."
        return out
    ls = left[left_col].dropna().astype(str).str.strip()
    rs = right[right_col].dropna().astype(str).str.strip()
    left_set = set(ls.head(5000))
    right_set = set(rs.head(5000))
    inter = left_set & right_set
    out["matching_keys"] = len(inter)
    out["left_distinct_keys"] = len(left_set)
    out["right_distinct_keys"] = len(right_set)
    out["cardinality"] = _cardinality(left[left_col], right[right_col])
    if not inter:
        out["warning"] = "No matching values between the two key columns."
    return out
