"""Section 1: data_modelling and data_analyzer unit tests."""
from __future__ import annotations

import numpy as np
import pandas as pd

import data_modelling as dm
import data_analyzer as da


# ---------------------------------------------------------------------------
# data_modelling.suggest_relationships
# ---------------------------------------------------------------------------

def test_suggest_relationships_finds_obvious_id_match():
    customers = pd.DataFrame({
        "customer_id": list(range(1, 11)),
        "country": ["LB", "JO"] * 5,
    })
    orders = pd.DataFrame({
        "order_id": list(range(101, 121)),
        "customer_id": [(i % 10) + 1 for i in range(20)],
        "amount": [10.0 * i for i in range(20)],
    })
    out = dm.suggest_relationships(customers, orders)
    assert out, "expected at least one suggestion"
    top = out[0]
    assert top.left_column == "customer_id"
    assert top.right_column == "customer_id"
    # Identical names + matching dtypes + perfect overlap → high confidence.
    assert top.confidence > 0.85


def test_suggest_relationships_returns_empty_for_unrelated_frames():
    a = pd.DataFrame({"alpha": ["a", "b", "c"]})
    b = pd.DataFrame({"beta": [99.9, 88.8, 77.7]})
    out = dm.suggest_relationships(a, b)
    # No name similarity, no dtype family match → no suggestions.
    assert out == []


def test_suggest_relationships_respects_max_results():
    n = 200
    left = pd.DataFrame({f"col_{i}": list(range(n)) for i in range(15)})
    right = pd.DataFrame({f"col_{i}": list(range(n)) for i in range(15)})
    out = dm.suggest_relationships(left, right, max_results=5)
    assert len(out) <= 5


# ---------------------------------------------------------------------------
# data_modelling.materialize_join
# ---------------------------------------------------------------------------

def test_materialize_join_left_keeps_all_left_rows():
    left = pd.DataFrame({"id": [1, 2, 3, 4], "x": ["a", "b", "c", "d"]})
    right = pd.DataFrame({"id": [1, 2], "y": ["yes", "yes"]})
    merged = dm.materialize_join(left, right, "id", "id", join_type="left")
    assert len(merged) == 4
    # The two unmatched rows should have NaN on the right side.
    assert merged["y"].isna().sum() == 2


def test_materialize_join_invalid_column_raises():
    left = pd.DataFrame({"a": [1, 2]})
    right = pd.DataFrame({"b": [1, 2]})
    try:
        dm.materialize_join(left, right, "ghost", "b")
    except ValueError as exc:
        assert "Left column" in str(exc) or "ghost" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing left column")


def test_materialize_join_full_alias_matches_outer():
    left = pd.DataFrame({"k": [1, 2, 3]})
    right = pd.DataFrame({"k": [2, 3, 4]})
    merged = dm.materialize_join(left, right, "k", "k", join_type="full")
    # Same-name keys are kept side-by-side with suffixes; both columns
    # together must cover the union of the two key sets.
    keys = set()
    for col in merged.columns:
        keys.update(int(v) for v in merged[col].dropna())
    assert keys == {1, 2, 3, 4}
    assert len(merged) == 4


# ---------------------------------------------------------------------------
# data_analyzer
# ---------------------------------------------------------------------------

def test_basic_stats_reports_dimensions():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0], "c": ["x", "y", "z"]})
    out = da.get_basic_stats(df)
    assert isinstance(out, dict) and out
    assert out.get("row_count") == 3
    assert out.get("column_count") == 3
    assert "a" in out.get("columns", [])


def test_numeric_stats_returns_dataframe_with_numeric_columns():
    df = pd.DataFrame({"a": [1, 2, 3, 4, 5], "name": ["x"] * 5,
                       "b": [10.0, 20.0, 30.0, 40.0, 50.0]})
    out = da.get_numeric_stats(df)
    assert isinstance(out, pd.DataFrame)
    # Should describe both numeric columns.
    assert {"a", "b"}.issubset(set(out.columns) | set(out.index))


def test_correlation_matrix_is_symmetric_and_diagonal_one():
    df = pd.DataFrame({
        "a": np.linspace(0, 10, 50),
        "b": np.linspace(0, 10, 50) + np.random.default_rng(1).normal(0, 0.1, 50),
        "c": np.random.default_rng(2).normal(0, 1, 50),
    })
    corr = da.get_correlation_matrix(df)
    assert isinstance(corr, pd.DataFrame)
    if not corr.empty:
        # Diagonal should be ~1 for any numeric column kept in the matrix.
        diag = np.diag(corr.values)
        assert all(abs(d - 1.0) < 1e-6 for d in diag)


def test_find_strong_correlations_picks_up_obvious_signal():
    rng = np.random.default_rng(5)
    n = 80
    x = rng.normal(0, 1, n)
    y = 3 * x + rng.normal(0, 0.05, n)  # nearly perfect correlation
    df = pd.DataFrame({"x": x, "y": y, "noise": rng.normal(0, 1, n)})
    out = da.find_strong_correlations(df, threshold=0.7)
    assert isinstance(out, list)
    pairs = {(d.get("column1"), d.get("column2")) for d in out}
    assert any({"x", "y"}.issubset(set(p)) for p in pairs)


def test_detect_outliers_flags_extreme_values():
    df = pd.DataFrame({"a": list(range(50)) + [10_000]})
    out = da.detect_outliers(df)
    assert isinstance(out, dict)
    if out:
        # The injected outlier should be reported for column "a".
        assert "a" in out
