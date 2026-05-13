"""Tests for the mode-aware predictions engine (Task #245).

Covers:
  * Auto-pick between LinearRegression and RandomForestRegressor on
    the regression path (the lower-RMSE wins).
  * Classification path with predict_proba CIs and macro-averaged
    metrics.
  * Time-series path (Prophet, with native CI) on the canonical
    monthly fixture.
  * Inventory helpers — declining-trend flag, days-to-stockout flag,
    and all three discount tiers.
  * The dual ``{guided, expert}`` payload shape, CV mean/std presence,
    and CI presence on every family.
  * Metric correctness on a tiny deterministic linear fixture.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend import predictions_engine as pe


# ---------------------------------------------------------------------------
# Dual-payload shape (validated on every family)
# ---------------------------------------------------------------------------

DUAL_TOP_KEYS = {"guided", "expert", "mode"}
GUIDED_KEYS = {"summary", "confidence", "confidence_score", "recommendations"}
EXPERT_KEYS = {
    "model_used", "problem_type", "target", "metrics",
    "cross_validation", "parameters", "feature_importance",
    "confidence_interval", "trend_direction", "trend_slope",
    "predictions",
}


def _assert_dual_shape(out: dict) -> None:
    assert DUAL_TOP_KEYS.issubset(out.keys()), f"missing top keys: {out.keys()}"
    assert GUIDED_KEYS.issubset(out["guided"].keys()), out["guided"].keys()
    assert EXPERT_KEYS.issubset(out["expert"].keys()), out["expert"].keys()
    cv = out["expert"]["cross_validation"]
    assert "mean" in cv and "std" in cv and "scores" in cv, cv
    ci = out["expert"]["confidence_interval"]
    assert ci, "confidence_interval must be populated"
    assert isinstance(out["guided"]["recommendations"], list)


# ---------------------------------------------------------------------------
# Regression path — LR vs RF auto-pick
# ---------------------------------------------------------------------------

def test_regression_autopick_dual_payload(driver_regression_df):
    out = pe.run_prediction(driver_regression_df, target_col="sales")
    _assert_dual_shape(out)
    expert = out["expert"]
    assert expert["problem_type"] == "regression"
    assert expert["model_used"] in {"LinearRegression", "RandomForestRegressor"}
    # Both candidates must have been tried and ranked by RMSE.
    cands = expert.get("candidates")
    assert isinstance(cands, list) and len(cands) == 2
    rmses = [c["rmse"] for c in cands]
    assert expert["metrics"]["rmse"] == min(rmses)
    # CV summary
    cv = expert["cross_validation"]
    assert cv["folds"] == 5
    assert cv["metric"] == "rmse"
    assert isinstance(cv["mean"], float) and isinstance(cv["std"], float)
    # CI band
    ci = expert["confidence_interval"]
    assert ci["method"] in {"bootstrap_95", "analytical_95"}
    assert len(ci["lower"]) == len(ci["upper"]) == len(expert["predictions"])
    # Guided summary mentions r2
    assert "R²" in out["guided"]["summary"]


def test_regression_metrics_correct_on_deterministic_linear(synthetic_linear_df):
    """y = 3 * x + 5 → R² ≈ 1.0, RMSE ≈ 0."""
    out = pe.run_prediction(synthetic_linear_df, target_col="y")
    metrics = out["expert"]["metrics"]
    assert metrics["r2"] >= 0.99, metrics
    assert metrics["rmse"] < 0.5, metrics
    assert metrics["mae"] < 0.5, metrics


# ---------------------------------------------------------------------------
# Classification path
# ---------------------------------------------------------------------------

def test_classification_path_predicts_classes(classification_df):
    out = pe.run_prediction(classification_df, target_col="label")
    _assert_dual_shape(out)
    expert = out["expert"]
    assert expert["problem_type"] == "classification"
    assert expert["model_used"] == "RandomForestClassifier"
    classes = expert.get("classes")
    assert classes and len(classes) >= 2
    # Macro metrics are present.
    for k in ("accuracy", "f1", "precision", "recall"):
        assert k in expert["metrics"]
    # CV mean/std are populated.
    cv = expert["cross_validation"]
    assert cv["metric"] == "accuracy"
    assert cv["mean"] is not None and cv["std"] is not None
    # CI = predicted class probabilities.
    ci = expert["confidence_interval"]
    assert ci["method"] == "predict_proba"
    assert len(ci["probabilities"]) == len(expert["predictions"])
    assert len(ci["probabilities"][0]) == len(ci["classes"])


# ---------------------------------------------------------------------------
# Time-series path — Prophet (with linear-trend fallback acceptable)
# ---------------------------------------------------------------------------

def test_timeseries_prophet_path_dual_payload(timeseries_sales_df):
    out = pe.run_prediction(
        timeseries_sales_df,
        target_col="revenue",
        date_col="date",
        periods=6,
    )
    _assert_dual_shape(out)
    expert = out["expert"]
    assert expert["problem_type"] == "timeseries"
    assert expert["model_used"] in {"prophet", "linear_trend"}
    assert expert["periods"] == 6
    forecast = expert["forecast"]
    assert isinstance(forecast, list) and len(forecast) == 6
    assert all({"ds", "yhat", "lower", "upper"}.issubset(p.keys()) for p in forecast)
    ci = expert["confidence_interval"]
    assert ci["method"] in {"prophet_native_95", "analytical_95"}
    assert len(ci["lower"]) == len(ci["upper"]) == 6
    cv = expert["cross_validation"]
    assert cv["mean"] is not None and cv["std"] is not None
    assert "MAPE" in out["guided"]["summary"] or "n/a" in out["guided"]["summary"]


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------

def test_inventory_declining_trend_and_stockout_flagged(inventory_df):
    out = pe.run_prediction(
        inventory_df,
        target_col="quantity",
        date_col="date",
        stockout_horizon_days=30,
    )
    inv = out["expert"].get("inventory")
    assert inv is not None and inv["available"] is True, inv
    declining_products = {d["product"] for d in inv["declining"]}
    # The "Widget" product was synthesized with a strong negative slope.
    assert "Widget" in declining_products
    stockout_products = {s["product"] for s in inv["stockout_risk"]}
    # The "LowStock" product has tiny remaining stock + strong outflow.
    assert "LowStock" in stockout_products
    # Per-product 7/14/30 day forecasts are present.
    horizons = inv["products"][0]["forecasts"]
    assert {"next_7_days", "next_14_days", "next_30_days"} == set(horizons.keys())


def test_inventory_discount_tiers_all_three():
    """All three discount tiers must be reachable from the helper."""
    today = pd.Timestamp("2025-01-01")
    rows = []
    # Aging buckets: 70d (>60 → 20%), 100d (>90 → 30%), 150d (>120 → bundle)
    for prod, days_old in (("LightAged", 70), ("DeepAged", 100), ("Clearance", 150)):
        rows.append({"product": prod, "date": today - pd.Timedelta(days=days_old),
                     "quantity": 5.0})
    # Add a fresh product to ensure today's max-date anchor is "today".
    rows.append({"product": "Fresh", "date": today, "quantity": 1.0})
    df = pd.DataFrame(rows)
    inv = pe._inventory_signals(
        df, product_col="product", qty_col="quantity", date_col="date",
        stockout_horizon=14,
    )
    discounts = {d["product"]: d for d in inv["discount_suggestions"]}
    assert discounts["LightAged"]["tier"] == "light_discount"
    assert discounts["LightAged"]["discount_pct"] == 20
    assert discounts["DeepAged"]["tier"] == "deep_discount"
    assert discounts["DeepAged"]["discount_pct"] == 30
    assert discounts["Clearance"]["tier"] == "bundle_clearance"
    assert discounts["Clearance"]["discount_pct"] is None
    assert "Fresh" not in discounts


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def test_detect_problem_type_routing(timeseries_sales_df, driver_regression_df,
                                     classification_df):
    assert pe._detect_problem_type(timeseries_sales_df, "revenue", "date") == "timeseries"
    assert pe._detect_problem_type(driver_regression_df, "sales", None) == "regression"
    assert pe._detect_problem_type(classification_df, "label", None) == "classification"


# ---------------------------------------------------------------------------
# Fixtures local to this file
# ---------------------------------------------------------------------------

@pytest.fixture
def synthetic_linear_df() -> pd.DataFrame:
    """y = 3 * x + 5 — a perfectly linear deterministic fixture."""
    x = np.arange(40, dtype=float)
    return pd.DataFrame({"x": x, "y": 3.0 * x + 5.0})


@pytest.fixture
def classification_df() -> pd.DataFrame:
    """Two-class problem: label depends on a clear linear boundary."""
    rng = np.random.default_rng(123)
    n = 80
    a = rng.normal(0, 1, size=n)
    b = rng.normal(0, 1, size=n)
    label = np.where(a + b > 0, "yes", "no")
    return pd.DataFrame({"feature_a": a, "feature_b": b, "label": label})


@pytest.fixture
def inventory_df() -> pd.DataFrame:
    """Multi-product, multi-date inventory fixture covering each branch.

    Products synthesised:
      * ``Widget`` — strong negative slope (declining demand).
      * ``LowStock`` — high outflow but very low remaining stock.
      * ``Steady`` — flat baseline (control product).
    """
    base_date = pd.Timestamp("2025-01-01")
    days = pd.date_range(base_date, periods=30, freq="D")
    rows = []
    for i, d in enumerate(days):
        # Widget: starts at 100, decays linearly to ~10 (declining slope).
        rows.append({"product": "Widget", "date": d,
                     "quantity": float(100 - 3 * i)})
        # Steady: hovers around 50.
        rows.append({"product": "Steady", "date": d,
                     "quantity": 50.0 + (i % 3 - 1) * 0.5})
        # LowStock: heavy outflow most days, but the LATEST observation
        # is 2.0 — average outflow / current stock → days-to-zero ~0.
        if i < 29:
            rows.append({"product": "LowStock", "date": d,
                         "quantity": 20.0})
        else:
            rows.append({"product": "LowStock", "date": d,
                         "quantity": 2.0})
    return pd.DataFrame(rows)
