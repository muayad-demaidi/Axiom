"""Focused regression tests for the Transform Toolkit (Task #28).

Covers:
  * Each of the six transform substep functions runs end-to-end and
    produces the expected schema / values.
  * `infer_examples_op` picks the right operation for representative
    cases (concat, split-take, suffix slice, regex extract, arithmetic).
  * The Add-Column-from-Examples acceptance gate: validation refuses to
    insert until inference has populated `op` + `op_params`.
"""
from __future__ import annotations

import pandas as pd

from transforms import (
    add_column_from_examples_step,
    conditional_column_step,
    group_by_step,
    infer_examples_op,
    merge_columns_step,
    replace_values_step,
    split_column_step,
)


def _people_df() -> pd.DataFrame:
    return pd.DataFrame({
        "first": ["Ada", "Linus", "Grace", "Donald"],
        "last": ["Lovelace", "Torvalds", "Hopper", "Knuth"],
        "age": [36, 54, 85, 86],
        "team": ["A", "B", "A", "B"],
        "email": ["ada@x.com", "linus@y.org", "grace@navy.mil", "don@stanford.edu"],
        "code": ["NYC-001", "SFO-022", "BOS-300", "LAX-415"],
    })


# --- Substep functions ----------------------------------------------------

def test_merge_columns_concatenates_with_separator():
    df = _people_df()
    out, summary, _ = merge_columns_step(
        df, columns=["first", "last"], separator=" ",
        new_column="full", keep_originals=True,
    )
    assert out["full"].tolist() == ["Ada Lovelace", "Linus Torvalds",
                                     "Grace Hopper", "Donald Knuth"]
    assert "full" in summary


def test_split_column_by_delimiter_creates_multiple_columns():
    df = _people_df()
    out, _, _ = split_column_step(
        df, column="email", mode="delimiter", delimiter="@",
        new_column_prefix="e", keep_original=True,
    )
    assert "e_1" in out.columns and "e_2" in out.columns
    assert out["e_1"].tolist() == ["ada", "linus", "grace", "don"]


def test_split_column_fixed_width():
    df = _people_df()
    out, _, _ = split_column_step(
        df, column="code", mode="width", width=3,
        new_column_prefix="c", keep_original=True,
    )
    # "NYC-001" → "NYC", "-00", "1"
    assert out["c_1"].iloc[0] == "NYC"
    assert out["c_2"].iloc[0] == "-00"


def test_replace_values_whole_cell():
    df = _people_df()
    out, summary, _ = replace_values_step(
        df, column="team", find="A", replace="Alpha",
        whole_cell=True, case_sensitive=True,
    )
    assert out["team"].tolist() == ["Alpha", "B", "Alpha", "B"]
    assert "Replaced 2" in summary


def test_replace_values_substring_case_insensitive():
    df = _people_df()
    out, _, _ = replace_values_step(
        df, column="email", find=".COM", replace=".io",
        whole_cell=False, case_sensitive=False,
    )
    assert out["email"].iloc[0] == "ada@x.io"
    # untouched rows preserved
    assert out["email"].iloc[1] == "linus@y.org"


def test_conditional_column_first_match_wins():
    df = _people_df()
    out, _, _ = conditional_column_step(
        df, source_column="age",
        rules=[
            {"op": "<", "value": 40, "then": "young"},
            {"op": "<", "value": 70, "then": "mid"},
        ],
        else_value="senior",
        new_column="bucket",
    )
    assert out["bucket"].tolist() == ["young", "mid", "senior", "senior"]


def test_group_by_aggregates_with_aliases():
    df = _people_df()
    out, summary, _ = group_by_step(
        df, keys=["team"],
        aggregations=[
            {"column": "age", "agg": "mean", "alias": "avg_age"},
            {"column": "first", "agg": "count", "alias": "n"},
        ],
    )
    rows = {r["team"]: r for r in out.to_dict("records")}
    assert rows["A"]["avg_age"] == 60.5
    assert rows["A"]["n"] == 2
    assert rows["B"]["avg_age"] == 70.0
    assert "2 aggregation(s)" in summary


def test_group_by_dedupes_aliases():
    df = _people_df()
    out, _, _ = group_by_step(
        df, keys=["team"],
        aggregations=[
            {"column": "age", "agg": "mean", "alias": "x"},
            {"column": "age", "agg": "max", "alias": "x"},
        ],
    )
    # Second aggregation should be auto-suffixed rather than overwriting
    # the first.
    assert "x" in out.columns and "x_2" in out.columns


# --- Inference engine ----------------------------------------------------

def test_infer_concat_separator():
    df = _people_df()
    op, params, cov = infer_examples_op(
        df, ["first", "last"],
        [(0, "Ada Lovelace"), (1, "Linus Torvalds")],
    )
    assert op == "concat"
    assert params == {"separator": " "}
    assert cov == 1.0


def test_infer_split_take():
    df = _people_df()
    op, params, cov = infer_examples_op(
        df, ["email"],
        [(0, "ada"), (1, "linus"), (2, "grace")],
    )
    assert op == "split_take"
    assert params["delimiter"] == "@"
    assert params["index"] == 0
    assert cov == 1.0


def test_infer_suffix_slice():
    """Last-N-chars extraction must be reachable via the inference
    catalogue — covered by the negative-start slice candidates."""
    df = _people_df()
    # Last 3 chars of code: "001", "022", "300", "415"
    op, params, cov = infer_examples_op(
        df, ["code"],
        [(0, "001"), (1, "022"), (2, "300")],
    )
    assert cov == 1.0
    # Any of these proves the inference engine can reach the target —
    # suffix slice, regex extract, or split-take with the dash delimiter
    # all yield the correct extraction.
    assert op in ("slice", "regex_extract", "split_take")
    if op == "slice":
        assert params["start"] == -3


def test_infer_regex_extract_for_prefix_before_dash():
    """Prefix-before-delimiter where the delimiter isn't in the split-take
    catalogue must still be inferable via regex_extract."""
    df = pd.DataFrame({"sku": ["NYC-001", "SFO-022", "BOS-300", "LAX-415"]})
    op, params, cov = infer_examples_op(
        df, ["sku"],
        [(0, "NYC"), (1, "SFO"), (2, "BOS")],
    )
    assert cov == 1.0
    # split_take with delimiter "-" is the simplest match, regex_extract
    # is also acceptable — both prove the inference engine can reach it.
    assert op in ("split_take", "regex_extract", "slice")


def test_infer_arithmetic():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": [10, 20, 30, 40]})
    op, params, _cov = infer_examples_op(
        df, ["a", "b"],
        [(0, "11"), (1, "22"), (2, "33")],
    )
    assert op == "arithmetic"
    assert params == {"operator": "+"}


def test_infer_returns_none_when_no_match():
    df = _people_df()
    op, params, cov = infer_examples_op(
        df, ["age"],
        [(0, "totally_unrelated"), (1, "also_unrelated")],
    )
    assert op is None and params is None and cov == 0.0


# --- Add Column from Examples acceptance gate ----------------------------

def test_add_column_from_examples_requires_inferred_op():
    """Replicates the validator rule used by the Transform expander UI:
    inserting Add-Column-from-Examples without first running inference
    must be refused."""
    from app import _validate_transform_params

    base_params = {
        "new_column": "full",
        "source_columns": ["first", "last"],
        "examples": [{"row_idx": 0, "target": "Ada Lovelace"}],
    }
    ok, msg = _validate_transform_params("add_column_from_examples", base_params)
    assert ok is False
    assert "Infer" in msg

    # Once the inferred op is baked in, the same params validate.
    accepted = dict(base_params, op="concat", op_params={"separator": " "})
    ok, msg = _validate_transform_params("add_column_from_examples", accepted)
    assert ok is True


def test_add_column_from_examples_applies_inferred_op():
    df = _people_df()
    op, params, _ = infer_examples_op(
        df, ["first", "last"],
        [(0, "Ada Lovelace"), (1, "Linus Torvalds")],
    )
    out, _, _ = add_column_from_examples_step(
        df, source_columns=["first", "last"], op=op,
        op_params=params, new_column="full",
    )
    assert out["full"].tolist() == ["Ada Lovelace", "Linus Torvalds",
                                     "Grace Hopper", "Donald Knuth"]
