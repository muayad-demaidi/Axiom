"""Tests for SHAP integration on the RandomForest paths (Task #250).

When the optional ``shap`` package is installed, the predictions
engine attaches the top-5 mean-absolute SHAP values under
``feature_importance.shap_top``. When it's not installed, the engine
attaches an explanatory ``feature_importance.note`` instead. Both
behaviours must be exercised so the engine remains reliable on
Replit (where the wheel is occasionally unavailable for the active
Python version).
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import pytest

from backend import predictions_engine as pe


try:
    import shap  # type: ignore  # noqa: F401
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False


@pytest.fixture
def rf_regression_df() -> pd.DataFrame:
    """A non-linear-ish driver fixture so RF wins over LinearRegression.

    The interaction term + the squared term mean RandomForest
    consistently beats LinearRegression on the holdout RMSE — that
    way the SHAP path is exercised under regression as well.
    """
    rng = np.random.default_rng(17)
    n = 120
    spend = rng.uniform(10, 100, size=n)
    units = rng.uniform(1, 50, size=n)
    season = rng.integers(0, 4, size=n).astype(float)
    noise = rng.normal(0, 3, size=n)
    sales = (
        2.0 * spend
        + 1.5 * units
        + 5.0 * (season == 3).astype(float) * units
        + 0.05 * spend * units
        + noise
    )
    return pd.DataFrame({
        "marketing_spend": spend.round(2),
        "units": units.round(2),
        "season": season,
        "sales": sales.round(2),
    })


@pytest.fixture
def rf_classification_df() -> pd.DataFrame:
    rng = np.random.default_rng(19)
    n = 120
    a = rng.normal(0, 1, size=n)
    b = rng.normal(0, 1, size=n)
    c = rng.normal(0, 1, size=n)
    label = np.where(a + b - 0.5 * c > 0, "yes", "no")
    return pd.DataFrame({
        "feature_a": a, "feature_b": b, "feature_c": c, "label": label,
    })


def _shap_or_note(feature_importance: dict) -> tuple[bool, dict | str | None]:
    """Return (has_shap_top, payload-or-note) for assertion convenience."""
    if "shap_top" in feature_importance:
        return True, feature_importance["shap_top"]
    return False, feature_importance.get("note")


@pytest.mark.skipif(not SHAP_AVAILABLE, reason="shap not installed")
def test_classifier_attaches_shap_top_when_available(rf_classification_df):
    out = pe.run_prediction(rf_classification_df, target_col="label")
    fi = out["expert"]["feature_importance"]
    has, payload = _shap_or_note(fi)
    assert has, fi
    assert isinstance(payload, dict) and 1 <= len(payload) <= 5
    for name, value in payload.items():
        assert isinstance(name, str)
        assert isinstance(value, (int, float))
        assert value >= 0


@pytest.mark.skipif(not SHAP_AVAILABLE, reason="shap not installed")
def test_regression_rf_attaches_shap_top_when_available(rf_regression_df):
    out = pe.run_prediction(rf_regression_df, target_col="sales")
    expert = out["expert"]
    if expert["model_used"] != "RandomForestRegressor":
        pytest.skip(
            f"LinearRegression won the auto-pick ({expert['model_used']}); "
            "SHAP only attaches to the RF path."
        )
    fi = expert["feature_importance"]
    has, payload = _shap_or_note(fi)
    assert has, fi
    assert isinstance(payload, dict) and 1 <= len(payload) <= 5


def test_classifier_emits_note_when_shap_missing(monkeypatch, rf_classification_df):
    """Force the import to fail and assert the engine degrades gracefully."""
    # Block both the freshly imported module and any cached binding so
    # the inner ``import shap`` raises ImportError.
    monkeypatch.setitem(sys.modules, "shap", None)

    out = pe.run_prediction(rf_classification_df, target_col="label")
    fi = out["expert"]["feature_importance"]
    assert "shap_top" not in fi
    assert "note" in fi and isinstance(fi["note"], str)
    assert "shap" in fi["note"].lower()


def test_regression_emits_note_when_shap_missing(monkeypatch, rf_regression_df):
    monkeypatch.setitem(sys.modules, "shap", None)

    out = pe.run_prediction(rf_regression_df, target_col="sales")
    expert = out["expert"]
    fi = expert["feature_importance"]
    if expert["model_used"] == "RandomForestRegressor":
        assert "shap_top" not in fi
        assert "note" in fi and "shap" in fi["note"].lower()
    else:
        # LR path doesn't compute SHAP at all — just assert the
        # baseline coefficient-derived importances still ship.
        assert any(isinstance(v, (int, float)) for v in fi.values()), fi
