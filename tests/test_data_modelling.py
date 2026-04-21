"""Focused tests for the Data Modelling helpers (Task #29)."""
from __future__ import annotations

import pandas as pd

from data_modelling import (
    _cardinality, _dtype_score, _name_similarity, _overlap_score,
    materialize_join, suggest_relationships, validate_relationship,
)


def _orders():
    return pd.DataFrame({
        "order_id": [1, 2, 3, 4, 5],
        "customer_id": [10, 20, 10, 30, 20],
        "amount": [99.0, 49.0, 25.0, 199.0, 12.0],
    })


def _customers():
    return pd.DataFrame({
        "id": [10, 20, 30, 40],
        "name": ["Ada", "Linus", "Grace", "Donald"],
        "country": ["US", "FI", "US", "US"],
    })


# --- name similarity -----------------------------------------------------

def test_name_similarity_exact_and_normalised():
    assert _name_similarity("id", "id") == 1.0
    assert _name_similarity("Customer_ID", "customer_id") == 1.0
    # "id" is a suffix of "customerid" → partial credit, not full.
    s = _name_similarity("id", "customer_id")
    assert 0.5 <= s < 1.0


def test_name_similarity_far_apart():
    assert _name_similarity("amount", "country") < 0.5


# --- dtype score ---------------------------------------------------------

def test_dtype_score_same_family_is_one():
    s = pd.Series([1, 2, 3])
    assert _dtype_score(s, s) == 1.0


def test_dtype_score_numeric_vs_text_partial():
    a = pd.Series([1, 2, 3])
    b = pd.Series(["1", "2", "3"])
    assert 0.0 < _dtype_score(a, b) < 1.0


# --- overlap & cardinality ----------------------------------------------

def test_overlap_score_full_containment():
    a = pd.Series([1, 2, 3])
    b = pd.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    score = _overlap_score(a, b, sample_size=100)
    # Containment lifts the score above plain Jaccard (3/10 = 0.3).
    assert score > 0.5


def test_cardinality_one_to_many():
    left = pd.Series([1, 2, 3])           # all unique
    right = pd.Series([1, 1, 2, 3, 3])    # repeats
    assert _cardinality(left, right) == "1:N"


# --- suggest_relationships end-to-end -----------------------------------

def test_suggest_relationships_picks_obvious_fk():
    o, c = _orders(), _customers()
    suggestions = suggest_relationships(o, c)
    assert suggestions, "expected at least one suggestion"
    top = suggestions[0]
    assert top.left_column == "customer_id"
    assert top.right_column == "id"
    assert top.confidence > 0.6
    assert top.cardinality in ("N:1", "N:N")


def test_suggest_relationships_filters_unrelated_columns():
    o, c = _orders(), _customers()
    suggestions = suggest_relationships(o, c)
    # `amount` ↔ `country` should never make the cut.
    assert all(
        not (s.left_column == "amount" and s.right_column == "country")
        for s in suggestions
    )


def test_suggest_relationships_handles_empty_frames():
    assert suggest_relationships(pd.DataFrame(), _customers()) == []
    assert suggest_relationships(_orders(), pd.DataFrame()) == []


# --- materialize_join ----------------------------------------------------

def test_materialize_join_left_join_preserves_left_rows():
    o, c = _orders(), _customers()
    out = materialize_join(o, c, "customer_id", "id", join_type="left",
                           left_label="orders", right_label="customers")
    assert len(out) == len(o)
    assert "name" in out.columns
    assert "country" in out.columns


def test_materialize_join_inner_drops_unmatched():
    o, c = _orders(), _customers()
    # Customer 40 has no orders; an inner join should drop them.
    out = materialize_join(o, c, "customer_id", "id", join_type="inner")
    assert 40 not in out["id"].tolist()


def test_materialize_join_string_vs_int_keys():
    """Numeric ID on one side, same value as text on the other — the
    coerce-to-string trick inside materialize_join should still match."""
    o = pd.DataFrame({"k": [1, 2, 3], "v": ["a", "b", "c"]})
    c = pd.DataFrame({"k": ["1", "2", "3"], "label": ["x", "y", "z"]})
    out = materialize_join(o, c, "k", "k", join_type="inner",
                           left_label="o", right_label="c")
    assert len(out) == 3
    assert set(out["label"]) == {"x", "y", "z"}


def test_materialize_join_invalid_columns_raises():
    o, c = _orders(), _customers()
    try:
        materialize_join(o, c, "missing", "id")
    except ValueError as e:
        assert "missing" in str(e)
    else:
        raise AssertionError("expected ValueError for missing left column")


# --- validate_relationship ----------------------------------------------

def test_validate_relationship_reports_overlap_and_cardinality():
    o, c = _orders(), _customers()
    diag = validate_relationship(o, c, "customer_id", "id")
    assert diag["matching_keys"] == 3
    assert diag["cardinality"] in ("N:1", "N:N")
    assert "warning" not in diag


def test_validate_relationship_warns_on_no_overlap():
    a = pd.DataFrame({"x": [1, 2, 3]})
    b = pd.DataFrame({"y": [99, 100, 101]})
    diag = validate_relationship(a, b, "x", "y")
    assert diag["matching_keys"] == 0
    assert "warning" in diag


def test_validate_relationship_missing_column_returns_error():
    o, c = _orders(), _customers()
    diag = validate_relationship(o, c, "nope", "id")
    assert "error" in diag
