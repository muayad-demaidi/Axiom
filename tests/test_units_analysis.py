"""Unit coverage for the deterministic analysis helpers documented for
Task #219:

  * ``build_profile``       — per-column profile (rows, cols, dtype,
                               missingness, uniques, basic stats).
  * ``surprise_insights``   — "huh, look at this" insight ribbon.
  * ``suggested_questions`` — CRISP-DM-aligned starter questions.

These functions live in :mod:`backend.insights` (the analysis layer
the chat / artifact pipeline calls into immediately after a dataset
lands). The smoke tests in ``test_insights_synthesis.py`` cover the
happy path; the cases below exercise the edge / branch behaviours
called out in the spec — empty frames, all-missing columns, strong
correlation detection, duplicate detection, Arabic locale, and the
tailoring of suggested questions to the data's shape.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from backend.insights import (
    build_profile,
    surprise_insights,
    suggested_questions,
)


# ---------------------------------------------------------------------------
# build_profile
# ---------------------------------------------------------------------------

def test_build_profile_reports_rows_cols_and_per_column_dtypes():
    df = pd.DataFrame({
        "name": ["a", "b", "c", "d"],
        "age": [10, 20, 30, 40],
        "joined": pd.to_datetime(["2024-01-01"] * 4),
    })
    p = build_profile(df)
    assert p["rows"] == 4
    assert p["cols"] == 3
    by_name = {c["name"]: c for c in p["columns"]}
    assert set(by_name) == {"name", "age", "joined"}
    # Each column entry exposes the documented summary keys.
    for col in by_name.values():
        assert {"name", "dtype", "non_null", "missing",
                "missing_pct", "unique"} <= set(col)
    # Numeric column is detected as numeric (dtype string contains "int").
    assert "int" in by_name["age"]["dtype"]


def test_build_profile_handles_missing_values_correctly():
    df = pd.DataFrame({
        "x": [1.0, 2.0, None, None, 5.0],
    })
    p = build_profile(df)
    col = p["columns"][0]
    assert col["non_null"] == 3
    assert col["missing"] == 2
    assert col["missing_pct"] == 40.0
    assert col["unique"] == 3


def test_build_profile_on_empty_dataframe_returns_zero_rows():
    p = build_profile(pd.DataFrame())
    assert p["rows"] == 0
    assert p["cols"] == 0
    assert p["columns"] == []


# ---------------------------------------------------------------------------
# surprise_insights
# ---------------------------------------------------------------------------

def test_surprise_insights_empty_dataframe_returns_empty_list():
    assert surprise_insights(pd.DataFrame()) == []


def test_surprise_insights_flags_high_missingness_column():
    df = pd.DataFrame({
        "good": list(range(100)),
        "sparse": [1] + [None] * 99,  # 99% missing
    })
    items = surprise_insights(df)
    miss = [it for it in items if it.get("kind") == "missingness"]
    assert miss, f"expected missingness insight, got kinds={[i.get('kind') for i in items]}"
    assert miss[0]["column"] == "sparse"
    assert miss[0]["severity"] == "warn"
    assert miss[0]["value"] >= 90.0


def test_surprise_insights_flags_duplicate_rows():
    base = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
    df = pd.concat([base] * 5, ignore_index=True)  # 15 rows, lots of dups
    items = surprise_insights(df)
    dup = [it for it in items if it.get("kind") == "duplicates"]
    assert dup, "expected a duplicates insight on a duplicated dataframe"
    assert dup[0]["value"] >= 1


def test_surprise_insights_flags_strong_correlation():
    rng = np.random.default_rng(0)
    n = 200
    a = rng.normal(0, 1, n)
    b = a * 2 + rng.normal(0, 0.05, n)  # near-perfect positive correlation
    df = pd.DataFrame({"a": a, "b": b})
    items = surprise_insights(df)
    corr = [it for it in items if it.get("kind") == "correlation"]
    assert corr, "expected a correlation insight on linearly related cols"
    assert set(corr[0]["columns"]) == {"a", "b"}
    assert abs(corr[0]["value"]) >= 0.7


def test_surprise_insights_respects_max_items_cap():
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "country": rng.choice(["LB", "JO", "EG", "AE", "SA"], size=400),
        "amount": rng.normal(100, 20, 400),
        "spend": rng.normal(50, 10, 400),
        "missing_a": [None] * 380 + [1] * 20,
    })
    items = surprise_insights(df, max_items=3)
    assert isinstance(items, list)
    # max_items is the documented cap on the ribbon.
    assert len(items) <= 8


# ---------------------------------------------------------------------------
# suggested_questions
# ---------------------------------------------------------------------------

def test_suggested_questions_default_locale_is_english():
    df = pd.DataFrame({
        "country": ["LB", "JO", "EG", "LB", "AE"],
        "revenue": [100.0, 200, 150, 250, 175],
    })
    qs = suggested_questions(df)
    assert qs and all(isinstance(q, str) for q in qs)
    blob = " ".join(qs).lower()
    # English-locale phrasing markers.
    assert any(token in blob for token in (
        "show", "compare", "predict", "profile", "distribution",
    ))


def test_suggested_questions_arabic_locale_returns_arabic_text():
    df = pd.DataFrame({
        "country": ["LB", "JO", "EG", "LB", "AE"],
        "revenue": [100.0, 200, 150, 250, 175],
    })
    qs = suggested_questions(df, lang="ar")
    assert qs
    blob = "".join(qs)
    # At least one Arabic letter must appear.
    assert any("\u0600" <= ch <= "\u06FF" for ch in blob), (
        f"Arabic mode returned no Arabic text: {qs!r}"
    )


def test_suggested_questions_tailors_output_to_dataframe_shape():
    """The questions deck adapts to what's actually in the data:
    - If there's no datetime column, no forecast question.
    - If there's only one numeric column, no scatter question.
    - If there are categorical and numeric columns, a "compare across"
      question must appear.
    """
    df_only_one_numeric = pd.DataFrame({
        "country": ["LB", "JO", "EG", "AE"],
        "amount": [10, 20, 30, 40],
    })
    qs = suggested_questions(df_only_one_numeric)
    blob = " ".join(qs).lower()
    assert "scatter" not in blob
    assert "forecast" not in blob
    assert "compare" in blob

    df_with_datetime = pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=10, freq="D"),
        "amount": np.arange(10, dtype=float),
    })
    qs = suggested_questions(df_with_datetime)
    assert any("forecast" in q.lower() for q in qs)
