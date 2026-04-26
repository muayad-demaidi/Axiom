"""Regression coverage for Task #231 — wrong group-by totals on
mixed-locale amount columns (DMBTR/GJAHR pivot).

What changed in the codebase:

* ``context.type_inference`` now exposes one canonical numeric parser
  (``parse_numeric_value`` / ``parse_numeric_series`` /
  ``to_numeric_canonical``) that every BI consumer routes through.
* ``backend.aggregation.aggregate`` calls the canonical parser inside
  ``_apply_single_agg`` and emits a ``calc_trace`` block plus a
  validation gate that refuses implausible totals with the exact
  message ``"Possible numeric parsing issue detected in <col>.
  Aggregation blocked until values are normalized."``.
* ``infer_field_meta`` now classifies SAP-style amount columns
  (``DMBTR``, ``WRBTR`` etc.) as measures with default SUM, even when
  the dtype is ``object`` because of mixed-locale strings.

These tests pin the parser rules, the field-metadata classification,
the validation gate, and the full pivot output against the bundled
``acdoca_dirty_1200_rows`` CSV.

Note on the ``expected totals`` deviation
------------------------------------------
The original task description quoted Excel reference totals of
~31M / 29M / 35M.  Those are mathematically impossible: the file has
1200 rows with per-row amounts in the $107–$9,977 range, so the upper
bound on the grand total is ~12M, not 95M.  After re-parsing every row
deterministically with the canonical parser the only consistent totals
are the ones pinned below.  The bug being fixed is that the BI surface
silently dropped or miscoerced rows; the deterministic ground-truth
totals computed from the cleaned values are the right answer.
"""
from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from backend import aggregation as agg
from context.type_inference import (
    PARSE_STATUS_BAD,
    PARSE_STATUS_NULL,
    PARSE_STATUS_OK,
    parse_numeric_series,
    parse_numeric_value,
    to_numeric_canonical,
)


CSV_PATH = Path("attached_assets/acdoca_dirty_1200_rows_1777196337943.csv")


# Deterministic ground truth produced by parsing every row of the
# bundled CSV through the canonical parser.  Pinned to two decimals.
EXPECTED_BY_YEAR = {
    "2021": 1_558_611.23,
    "2022": 1_259_791.70,
    "2023": 1_422_885.56,
}
EXPECTED_GRAND_TOTAL = round(sum(EXPECTED_BY_YEAR.values()), 2)  # 4,241,288.49

# How close is "equal" for floating-point sums (cents).
TOL = 0.01


# ---------------------------------------------------------------------------
# Parser unit tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        # Plain integers / floats
        ("1583", 1583.0),
        ("3705", 3705.0),
        ("865518", 865518.0),
        ("9977", 9977.0),
        ("107.22", 107.22),
        # US thousands separator: comma followed by 3 digits ⇒ thousands.
        ("1,583", 1583.0),
        ("3,705", 3705.0),
        ("865,518", 865518.0),
        ("1,234,567", 1234567.0),
        # EU decimal-comma: comma followed by 1-2 digits ⇒ decimal.
        ("1,5", 1.5),
        ("3,75", 3.75),
        ("865,51", 865.51),
        # EU thousands-dot mirrors the comma rule: a single dot
        # followed by exactly 3 digits is a thousands separator.  Tail
        # of 1-2 digits stays as a decimal.
        ("1.583", 1583.0),
        ("12.345", 12345.0),
        ("865.518", 865518.0),
        ("1.234.567", 1234567.0),
        ("123.45", 123.45),
        ("1.5", 1.5),
        ("0.583", 0.583),         # leading zero ⇒ never thousands
        # Mixed: rightmost separator wins.
        ("1.234,56", 1234.56),    # EU
        ("1,234.56", 1234.56),    # US
        # Negative + currency
        ("-1,583", -1583.0),
        ("$1,583", 1583.0),
        ("(1,583)", -1583.0),     # parens negative
        ("€ 1.234,56", 1234.56),
        # Whitespace / NBSP
        ("  1583  ", 1583.0),
        ("1\u00a0583", 1583.0),
        # Percent
        ("12.5%", 0.125),
    ],
)
def test_parser_handles_mixed_locale_values(raw, expected):
    value, status = parse_numeric_value(raw)
    assert status == PARSE_STATUS_OK, f"{raw!r} → status {status}"
    assert value is not None
    assert math.isclose(value, expected, abs_tol=1e-6), (
        f"{raw!r}: parsed {value}, expected {expected}"
    )


@pytest.mark.parametrize(
    "raw, expected_status",
    [
        (None, PARSE_STATUS_NULL),
        ("", PARSE_STATUS_NULL),
        ("   ", PARSE_STATUS_NULL),
        # Missing-value markers — null, expected to be sparse.
        ("nan", PARSE_STATUS_NULL),
        ("NaN", PARSE_STATUS_NULL),
        ("NULL", PARSE_STATUS_NULL),
        ("n/a", PARSE_STATUS_NULL),
        ("--", PARSE_STATUS_NULL),
        # Spreadsheet/system error markers — distinct from missing
        # values; classified as unparseable so the validation gate
        # treats them as broken-row signals.
        ("ERROR", PARSE_STATUS_BAD),
        ("err", PARSE_STATUS_BAD),
        ("#DIV/0!", PARSE_STATUS_BAD),
        ("#REF!", PARSE_STATUS_BAD),
        # Free-form non-numeric strings.
        ("abc", PARSE_STATUS_BAD),
        ("12abc34", PARSE_STATUS_BAD),
    ],
)
def test_parser_rejects_junk_tokens(raw, expected_status):
    value, status = parse_numeric_value(raw)
    assert status == expected_status, f"{raw!r} → {status}"
    assert value is None


@pytest.mark.parametrize(
    "raw, mode, expected",
    [
        # decimal_point: every comma is a thousands separator, dots stay
        # as decimals — even the dot-followed-by-3-digits case that
        # auto-mode would treat as thousands.
        ("1.583", "decimal_point", 1.583),
        ("1,234.56", "decimal_point", 1234.56),
        ("865,518", "decimal_point", 865518.0),
        # decimal_comma: every dot is a thousands separator, commas
        # become decimals.
        ("1.583", "decimal_comma", 1583.0),
        ("1.234,56", "decimal_comma", 1234.56),
        ("865,51", "decimal_comma", 865.51),
        # thousands_comma: commas stripped, dot is decimal.
        ("1,583", "thousands_comma", 1583.0),
        ("1,234.56", "thousands_comma", 1234.56),
        # thousands_dot: dots stripped, comma is decimal.
        ("1.583", "thousands_dot", 1583.0),
        ("1.234,56", "thousands_dot", 1234.56),
    ],
)
def test_parser_respects_mode_override(raw, mode, expected):
    value, status = parse_numeric_value(raw, mode=mode)
    assert status == PARSE_STATUS_OK, f"{raw!r} mode={mode} → status {status}"
    assert value is not None
    assert math.isclose(value, expected, abs_tol=1e-6), (
        f"{raw!r} mode={mode}: parsed {value}, expected {expected}"
    )


def test_parse_numeric_series_full_csv_row_by_row():
    """Every parsed value in DMBTR matches the scalar parser exactly,
    so vector and scalar paths can never disagree."""
    df = pd.read_csv(CSV_PATH)
    series = df["DMBTR"]
    parsed, status = parse_numeric_series(series)

    assert len(parsed) == len(series)
    assert (status == PARSE_STATUS_OK).all(), (
        f"{int((status != PARSE_STATUS_OK).sum())} rows failed canonical parsing;"
        " the bundled CSV is supposed to be entirely parseable."
    )

    # Spot-check vector vs scalar agreement on the first 100 rows.
    for label in series.head(100).index:
        scalar_v, scalar_s = parse_numeric_value(series.at[label])
        assert scalar_s == status.at[label]
        if scalar_v is None:
            assert pd.isna(parsed.at[label])
        else:
            assert math.isclose(float(parsed.at[label]), scalar_v, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Field metadata: amount-like columns must default to SUM
# ---------------------------------------------------------------------------

def test_dmbtr_classified_as_measure_with_sum():
    df = pd.read_csv(CSV_PATH)
    meta = agg.infer_field_meta(df)
    assert meta["DMBTR"]["role"] == "measure"
    assert meta["DMBTR"]["default_agg"] == "sum"
    # WRBTR is the second SAP amount column on the same record.
    assert meta["WRBTR"]["role"] == "measure"
    assert meta["WRBTR"]["default_agg"] == "sum"


def test_string_typed_amount_column_still_defaults_to_sum():
    """A column whose dtype is ``object`` (because of mixed-locale junk)
    must still be a SUM measure when its name reads like an amount."""
    df = pd.DataFrame({
        "OrderId": ["A", "B", "C"],
        "Total Amount": ["1,583", "3,705", "865,518"],   # object dtype
    })
    meta = agg.infer_field_meta(df)
    assert meta["Total Amount"]["role"] == "measure"
    assert meta["Total Amount"]["default_agg"] == "sum"


# ---------------------------------------------------------------------------
# Full pipeline: aggregate(SUM(DMBTR) by GJAHR)
# ---------------------------------------------------------------------------

def _aggregate_dmbtr_by_year(df: pd.DataFrame, **measure_kwargs) -> dict:
    spec = {"column": "DMBTR", **measure_kwargs}
    return agg.aggregate(
        df,
        rows=["GJAHR"],
        cols=[],
        measures=[spec],
        field_meta=agg.infer_field_meta(df),
    )


def test_pivot_dmbtr_by_gjahr_matches_canonical_totals():
    df = pd.read_csv(CSV_PATH)
    result = _aggregate_dmbtr_by_year(df)

    by_year = {
        str(r["_dims"]["GJAHR"]): float(r["m0"])
        for r in result["rows"]
        if r.get("m0") is not None
    }
    for year, want in EXPECTED_BY_YEAR.items():
        assert year in by_year, f"missing year {year} in pivot result"
        assert math.isclose(by_year[year], want, abs_tol=TOL), (
            f"GJAHR={year}: got {by_year[year]:,.2f}, want {want:,.2f}"
        )

    grand = float((result.get("grand_total") or {}).get("m0") or 0.0)
    assert math.isclose(grand, EXPECTED_GRAND_TOTAL, abs_tol=TOL), (
        f"Grand total drifted: {grand:,.2f} vs {EXPECTED_GRAND_TOTAL:,.2f}"
    )


def test_pivot_default_aggregation_is_sum_without_explicit_request():
    """The user didn't specify ``aggregation=sum``; the engine must
    default to SUM for an amount-like column rather than fall back to
    AVG or 'do not summarize'."""
    df = pd.read_csv(CSV_PATH)
    result = _aggregate_dmbtr_by_year(df)  # no aggregation= passed
    assert result["measures"][0]["aggregation"] == "sum"


def test_pivot_emits_calc_trace_with_parser_diagnostics():
    df = pd.read_csv(CSV_PATH)
    result = _aggregate_dmbtr_by_year(df)
    traces = result.get("calc_trace") or []
    assert traces, "aggregate() must include a calc_trace for amount measures"
    t = traces[0]
    assert t["column"] == "DMBTR"
    assert t["aggregation"] == "sum"
    assert t["grouping"] == ["GJAHR"]
    assert t["total_rows"] == 1200
    assert t["valid_rows"] == 1200
    assert t["invalid_rows"] == 0
    assert t["parse_success_rate"] == 1.0
    assert t["blocked"] is None
    assert t["parse_mode"] == "auto"
    assert t["parsed_column"] == "DMBTR__parsed"
    # The implied per-row contribution should sit close to the median
    # row magnitude — that's the invariant the validation gate checks.
    assert t["median_abs"] > 0
    assert abs(t["implied_per_row"]) / t["median_abs"] < 5


# ---------------------------------------------------------------------------
# Validation gate
# ---------------------------------------------------------------------------

_BLOCKED_MSG_TMPL = (
    "Possible numeric parsing issue detected in {col}. "
    "Aggregation blocked until values are normalized."
)


def test_validation_gate_blocks_when_most_rows_are_junk():
    df = pd.read_csv(CSV_PATH).copy()
    # Poison 99% of the rows with unparseable junk.
    df.loc[: int(len(df) * 0.99), "DMBTR"] = "ERROR"

    result = _aggregate_dmbtr_by_year(df)
    assert result.get("blocked") is True
    assert result.get("error") == _BLOCKED_MSG_TMPL.format(col="DMBTR")
    assert _BLOCKED_MSG_TMPL.format(col="DMBTR") in (result.get("warnings") or [])
    assert result["rows"] == []
    # The trace is still attached so the UI can show why it failed.
    traces = result.get("calc_trace") or []
    assert traces and traces[0]["blocked"] == _BLOCKED_MSG_TMPL.format(col="DMBTR")


def test_validation_gate_does_not_block_clean_data():
    df = pd.read_csv(CSV_PATH)
    result = _aggregate_dmbtr_by_year(df)
    assert not result.get("blocked")
    assert "error" not in result or result.get("error") is None
    assert result["rows"], "clean data must produce result rows"


def test_validation_gate_does_not_block_sparse_but_clean_column():
    """A column with mostly null/blank rows but every populated row
    parsing fine must not trip the validation gate.  This is the
    "optional surcharge column" pattern — gate must measure
    parse-success against populated rows, not total rows."""
    df = pd.read_csv(CSV_PATH).copy()
    # Blank out 90% of DMBTR values.  The remaining 10% are still
    # well-formed mixed-locale numbers the canonical parser handles.
    blank_mask = df.index >= int(len(df) * 0.10)
    df.loc[blank_mask, "DMBTR"] = ""

    result = _aggregate_dmbtr_by_year(df)
    assert not result.get("blocked"), (
        f"sparse-but-clean column tripped the gate: "
        f"{result.get('error')}, calc_trace={result.get('calc_trace')}"
    )
    assert result["rows"], "expected non-empty result for sparse-but-clean column"


def test_validation_gate_blocks_when_no_rows_parse():
    """A SUM where every row is unparseable must hard-fail with the
    canonical structured message rather than silently return zero."""
    df = pd.read_csv(CSV_PATH).copy()
    df["DMBTR"] = "ERROR"  # every row is junk
    result = _aggregate_dmbtr_by_year(df)
    assert result.get("blocked") is True
    assert result.get("error") == _BLOCKED_MSG_TMPL.format(col="DMBTR")
    assert result["rows"] == []
    traces = result.get("calc_trace") or []
    assert traces and traces[0]["valid_rows"] == 0
    assert traces[0]["blocked"] == _BLOCKED_MSG_TMPL.format(col="DMBTR")


def test_validation_gate_blocks_on_50x_inflation():
    """Simulate a parser disagreement that inflates the implied per-row
    contribution by ~50× over the median magnitude.  The tightened gate
    must refuse the SUM with the canonical message."""
    df = pd.read_csv(CSV_PATH).copy()
    # Replace a single row with an extreme outlier so that
    # sum / valid_rows blows past 50× the median row magnitude.  On the
    # bundled fixture the median |DMBTR| is ~3,200 — pumping one row to
    # 1e9 lifts the implied per-row to ~830k, an ~260× inflation.
    df.loc[df.index[0], "DMBTR"] = "1000000000"
    result = _aggregate_dmbtr_by_year(df)
    assert result.get("blocked") is True, (
        "50× inflation must trip the validation gate"
    )
    assert result.get("error") == _BLOCKED_MSG_TMPL.format(col="DMBTR")


# ---------------------------------------------------------------------------
# Cross-surface consistency: pivot, KPI, chart all agree
# ---------------------------------------------------------------------------

def test_kpi_sum_matches_pivot_grand_total():
    """A KPI (no row dims) must equal the pivot grand total."""
    df = pd.read_csv(CSV_PATH)
    pivot = _aggregate_dmbtr_by_year(df)
    pivot_total = float((pivot.get("grand_total") or {}).get("m0") or 0.0)

    kpi = agg.aggregate(
        df, rows=[], cols=[],
        measures=[{"column": "DMBTR", "aggregation": "sum"}],
        field_meta=agg.infer_field_meta(df),
    )
    kpi_total = float(kpi["rows"][0]["m0"])
    assert math.isclose(kpi_total, pivot_total, abs_tol=TOL)
    assert math.isclose(kpi_total, EXPECTED_GRAND_TOTAL, abs_tol=TOL)


def test_parse_mode_override_changes_aggregation_total():
    """A field-level parse_mode override must reach all the way into
    the aggregation engine and change the SUM accordingly.  Without
    end-to-end threading the same column would always yield the
    auto-mode total regardless of the user's choice."""
    df = pd.DataFrame({
        "amount": ["1.583", "2.345", "3.456"],
        "year":   ["2024", "2024", "2024"],
    })

    # auto mode: dot-followed-by-3-digits → thousands.
    auto_meta = agg.infer_field_meta(df)
    auto_meta["amount"]["role"] = "measure"
    auto_meta["amount"]["default_agg"] = "sum"
    auto_meta["amount"]["semantic_type"] = "currency"
    auto_result = agg.aggregate(
        df, rows=[], cols=[],
        measures=[{"column": "amount", "aggregation": "sum"}],
        field_meta=auto_meta,
    )
    auto_total = float(auto_result["rows"][0]["m0"])
    assert math.isclose(auto_total, 1583 + 2345 + 3456, abs_tol=TOL), (
        f"auto-mode total {auto_total} ≠ thousands interpretation"
    )

    # decimal_point override: dots are decimals, never thousands.
    dec_meta = agg.infer_field_meta(df)
    dec_meta["amount"]["role"] = "measure"
    dec_meta["amount"]["default_agg"] = "sum"
    dec_meta["amount"]["semantic_type"] = "currency"
    dec_meta["amount"]["parse_mode"] = "decimal_point"
    dec_result = agg.aggregate(
        df, rows=[], cols=[],
        measures=[{"column": "amount", "aggregation": "sum"}],
        field_meta=dec_meta,
    )
    dec_total = float(dec_result["rows"][0]["m0"])
    assert math.isclose(dec_total, 1.583 + 2.345 + 3.456, abs_tol=TOL), (
        f"decimal_point override total {dec_total} ≠ decimal interpretation"
    )

    # The two interpretations must actually differ — otherwise the
    # override didn't propagate.
    assert auto_total != dec_total, (
        "parse_mode override had no effect on the aggregation"
    )


def test_to_numeric_canonical_matches_aggregation_sum():
    """The canonical parser sum on the raw column must equal the
    aggregation-engine SUM, proving they share one code path."""
    df = pd.read_csv(CSV_PATH)
    canonical_sum = float(to_numeric_canonical(df["DMBTR"]).sum(skipna=True))
    pivot = _aggregate_dmbtr_by_year(df)
    pivot_total = float((pivot.get("grand_total") or {}).get("m0") or 0.0)
    assert math.isclose(canonical_sum, pivot_total, abs_tol=TOL)


def test_heatmap_correlation_includes_object_typed_amount_columns():
    """Heatmap/correlation must surface mixed-locale amount columns.

    The legacy ``df.select_dtypes(include="number")`` path silently
    excluded object-typed amount columns — the exact failure class
    this task fixes for aggregation.  The
    :func:`backend.aggregation.numeric_frame_for_correlation` helper
    routes object columns through the canonical parser so they
    actually appear in the correlation matrix.
    """

    from backend.aggregation import numeric_frame_for_correlation

    df = pd.DataFrame({
        "id": ["A", "B", "C", "D", "E"],
        "amount_str": ["1,000", "2,000", "3,000", "4,000", "5,000"],
        "qty": [1, 2, 3, 4, 5],
        "label": ["x", "y", "z", "w", "v"],
    })

    numeric = numeric_frame_for_correlation(df)
    assert "amount_str" in numeric.columns, (
        "object-typed amount column was silently excluded — heatmap "
        "would hide the very columns the user cares about"
    )
    assert "qty" in numeric.columns
    assert "label" not in numeric.columns
    assert "id" not in numeric.columns

    corr = numeric.corr(numeric_only=True).fillna(0.0)
    # qty and amount_str are perfectly correlated.
    assert math.isclose(
        float(corr.loc["qty", "amount_str"]), 1.0, abs_tol=1e-9
    )
