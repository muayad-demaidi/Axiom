"""Section 1 + 4: predictions and predict_guided_service unit tests.

Covers the Arabic insufficient-data messages, the linear / Prophet
fallback, sklearn driver-based regression, and the documented
weighted confidence formula.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import predictions
import backend.predict_guided_service as svc


# ---------------------------------------------------------------------------
# simple_forecast
# ---------------------------------------------------------------------------

def test_simple_forecast_insufficient_data_arabic_message():
    out = predictions.simple_forecast([1.0])
    assert "error" in out
    assert "بيانات كافية" in out["error"]


def test_simple_forecast_returns_uptrend_for_linear_series():
    out = predictions.simple_forecast(list(range(1, 13)), periods=3)
    assert out.get("trend") == "صاعد"
    assert out.get("r2_score", 0) > 0.99
    preds = out["predictions"]
    assert len(preds) == 3
    # Each subsequent forecast value should keep increasing.
    assert preds[0] < preds[1] < preds[2]


# ---------------------------------------------------------------------------
# predict_column
# ---------------------------------------------------------------------------

def test_predict_column_missing_target_returns_arabic_error():
    df = pd.DataFrame({"a": [1, 2, 3]})
    out = predictions.predict_column(df, "ghost")
    assert out.get("error") == "العمود المستهدف غير موجود"


def test_predict_column_three_rows_returns_arabic_insufficient_message():
    df = pd.DataFrame({"a": [1, 2, 3], "b": [10.0, 20.0, 30.0]})
    out = predictions.predict_column(df, "a")
    assert "البيانات غير كافية" in out.get("error", "")


def test_predict_column_runs_and_reports_metrics(driver_regression_df):
    out = predictions.predict_column(driver_regression_df, "sales")
    assert "metrics" in out
    assert out["metrics"]["r2_score"] > 0.5
    assert "marketing_spend" in out["features_used"]


def test_predict_column_no_numeric_features_returns_arabic():
    df = pd.DataFrame({
        "name": ["a"] * 12, "country": ["LB"] * 12,
        "target": [1.0, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],
    })
    out = predictions.predict_column(df, "target")
    assert "لا توجد أعمدة" in out.get("error", "")


# ---------------------------------------------------------------------------
# build_ml_prediction_model
# ---------------------------------------------------------------------------

def test_build_ml_prediction_model_with_mostly_missing_target(
    mostly_missing_target_df,
):
    out = predictions.build_ml_prediction_model(
        mostly_missing_target_df, "target"
    )
    # 90% missing → fewer than 50 usable rows → English error.
    assert out.get("error") == "Not enough data for ML model (need at least 50 rows)"


def test_chat_predict_graceful_arabic_explanation_for_sparse_target(
    mostly_missing_target_df,
):
    """The chat ``predict_column`` tool must NOT raise on a target
    column that is mostly missing. Instead it returns a calm,
    bilingual notice with both English and Arabic copy so the user
    sees a friendly message in either locale rather than a red error
    box.

    Drives the same code path the FastAPI ``/api/chat/stream``
    endpoint uses to dispatch the documented ``predict_column`` tool.
    """
    from backend.chat import (
        _small_sample_predict_notice,
        PREDICT_MIN_ROWS,
    )

    # Simulate the post-dropna() row count the dispatcher sees.
    usable = int(mostly_missing_target_df["target"].notna().sum())
    assert usable < PREDICT_MIN_ROWS, (
        f"fixture should have <{PREDICT_MIN_ROWS} usable rows; got {usable}"
    )

    notice = _small_sample_predict_notice(usable, "target", PREDICT_MIN_ROWS)
    assert notice["kind"] == "small_sample_notice"
    assert notice["target"] == "target"
    assert notice["rows_available"] == usable
    assert notice["rows_required"] == PREDICT_MIN_ROWS
    # Arabic graceful explanation — the requirement.
    assert "ما فيني" in notice["message_ar"], (
        f"Arabic graceful copy missing; got: {notice['message_ar']!r}"
    )
    assert "تنبؤ" in notice["message_ar"]
    # English copy still present alongside.
    assert "predict" in notice["message_en"].lower()
    # Suggested next-step tools are present so the chat can guide the
    # user toward something that *will* work on a sparse dataset.
    assert "profile_dataset" in notice["suggested_tools"]


# ---------------------------------------------------------------------------
# predict_guided_service.analyze_dataset
# ---------------------------------------------------------------------------

def test_guided_analyze_empty_dataset_message():
    out = svc.analyze_dataset(pd.DataFrame())
    assert out["ok"] is False
    assert out["kind"] == "empty_dataset"
    assert "البيانات فارغة" in out["message_ar"]


def test_guided_analyze_small_sample_message(tiny_three_row_df):
    out = svc.analyze_dataset(tiny_three_row_df)
    assert out["ok"] is False
    assert out["kind"] == "small_sample"
    assert out["rows_required"] == svc.MIN_ROWS_REGRESSION


def test_guided_analyze_timeseries_detects_target_and_questions(
    timeseries_sales_df,
):
    out = svc.analyze_dataset(timeseries_sales_df)
    assert out["ok"] is True
    assert out["target"] == "revenue"
    assert out["time_column"] == "date"
    assert out["questions"], "expected at least one Arabic clarifying question"
    assert "partial_confidence" in out


# ---------------------------------------------------------------------------
# predict_guided_service.run_prediction
# ---------------------------------------------------------------------------

def test_guided_run_prediction_timeseries_returns_forecast(timeseries_sales_df):
    out = svc.run_prediction(
        timeseries_sales_df,
        target="revenue",
        time_column="date",
        drivers=[],
        answers={"horizon_periods": 6},
    )
    assert out["flow"] == svc.GUIDED_FLOW_TAG
    assert "model" in out or "model_payload" in out or "forecast" in out
    # The result should expose a confidence breakdown matching the
    # documented sub-score weights.
    conf = out.get("confidence") or {}
    assert "score" in conf
    sub = conf.get("sub_scores") or {}
    assert {"data_volume", "data_quality",
            "signal_strength", "time_coverage"}.issubset(sub.keys())


def test_guided_run_prediction_driver_path(driver_regression_df):
    out = svc.run_prediction(
        driver_regression_df,
        target="sales",
        time_column=None,
        drivers=["marketing_spend", "units"],
        answers={},
    )
    assert out["flow"] == svc.GUIDED_FLOW_TAG
    # Driver path should expose a baseline number and r2.
    nums = out.get("numbers") or out.get("formatted_numbers") or {}
    text = " ".join(str(v) for v in nums.values())
    assert text  # at least non-empty


# ---------------------------------------------------------------------------
# compute_confidence (weighted blend)
# ---------------------------------------------------------------------------

def test_compute_confidence_weights_match_spec():
    """data_volume=0.25, data_quality=0.20, signal_strength=0.40,
    time_coverage=0.15 — verified by feeding 1.0 to one component
    at a time and checking the resulting score equals the weight."""

    components = {
        "data_volume": 0.25,
        "data_quality": 0.20,
        "signal_strength": 0.40,
        "time_coverage": 0.15,
    }
    for key, expected in components.items():
        scores = {k: 0.0 for k in components}
        scores[key] = 1.0
        out = svc.compute_confidence(scores)
        # ``compute_confidence`` returns score on a 0–100 scale.
        assert isinstance(out, dict)
        actual = float(out.get("score", 0))
        assert abs(actual - expected * 100) < 1.0, (
            f"weight for {key} expected ~{expected*100}, got {actual}"
        )


def test_compute_confidence_all_ones_yields_unity():
    scores = {"data_volume": 1.0, "data_quality": 1.0,
              "signal_strength": 1.0, "time_coverage": 1.0}
    out = svc.compute_confidence(scores)
    actual = float(out.get("score", 0))
    assert 99.0 <= actual <= 100.0


def test_compute_confidence_all_zero_yields_zero():
    scores = {"data_volume": 0.0, "data_quality": 0.0,
              "signal_strength": 0.0, "time_coverage": 0.0}
    out = svc.compute_confidence(scores)
    assert float(out.get("score", 1)) <= 1.0
