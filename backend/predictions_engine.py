"""Mode-aware predictions engine (Task #245).

Single entry point :func:`run_prediction` that auto-detects the right
modelling family for the supplied dataframe, runs cross-validation
and confidence intervals, optionally surfaces inventory/sales
signals, and **always** returns the documented dual ``{guided,
expert}`` payload — regardless of mode — so every consumer (chat,
recommendations, daily pulse, cross-predict) can pick the surface it
needs.

Design notes
------------
* No FastAPI imports here — pure logic.
* No model registry / persistence; every call refits from scratch.
* The Guided summary is generated **locally** from the metrics so the
  engine works fully offline; LLM polish is a follow-up.
* Prophet is loaded lazily so unit tests that exercise the regression
  / classification paths never pay the Prophet import cost (and the
  Prophet path degrades to a linear-trend fit when Prophet is
  unavailable).

Public API
~~~~~~~~~~
``run_prediction(df, target_col=None, date_col=None, mode=None, **opts)``

Recognised ``opts``:
    * ``periods`` — forecast horizon for the timeseries family
      (default 30).
    * ``stockout_horizon_days`` — days threshold for the stockout
      flag in the inventory helper (default 14).
    * ``inventory_product_col`` / ``inventory_qty_col`` — explicit
      schema overrides for the inventory detector.
    * ``test_size`` — test split for the regression and
      classification holdout (default 0.2).
"""
from __future__ import annotations

import logging
import math
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger("axiom.predictions_engine")


# Minimums chosen so 5-fold CV is always feasible and the holdout
# split has at least one row in both train and test partitions.
MIN_ROWS_REGRESSION = 10
MIN_ROWS_CLASSIFICATION = 10
MIN_ROWS_TIMESERIES = 8
DEFAULT_PERIODS = 30
DEFAULT_STOCKOUT_HORIZON_DAYS = 14
DEFAULT_TEST_SIZE = 0.2
CV_FOLDS = 5
BOOTSTRAP_SAMPLES = 200
CI_Z = 1.96


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_prediction(
    df: pd.DataFrame,
    target_col: str | None = None,
    date_col: str | None = None,
    mode: str | None = None,
    **opts: Any,
) -> dict[str, Any]:
    """Auto-route a dataframe to the right model family.

    Always returns the dual ``{guided, expert}`` payload. The ``mode``
    argument is accepted but does **not** change the payload shape —
    it is reserved for future mode-aware extras (e.g. extra Expert
    diagnostics). Both surfaces are always populated so consumers can
    pick whichever they need.
    """
    if df is None or df.empty:
        raise ValueError("dataset is empty")

    periods = int(opts.get("periods") or DEFAULT_PERIODS)
    stockout_horizon = int(
        opts.get("stockout_horizon_days") or DEFAULT_STOCKOUT_HORIZON_DAYS
    )
    test_size = float(opts.get("test_size") or DEFAULT_TEST_SIZE)

    target_col = _resolve_target_col(df, target_col, date_col)
    date_col = _resolve_date_col(df, date_col, exclude=[target_col])
    problem_type = _detect_problem_type(df, target_col, date_col)

    if problem_type == "timeseries":
        family_payload = _fit_prophet(df, date_col, target_col, periods=periods)
    elif problem_type == "classification":
        family_payload = _fit_classifier(df, target_col, test_size=test_size)
    else:
        family_payload = _fit_regression_pair_and_pick(
            df, target_col, test_size=test_size
        )

    inventory = _maybe_inventory_signals(
        df,
        target_col=target_col,
        date_col=date_col,
        stockout_horizon=stockout_horizon,
        product_col=opts.get("inventory_product_col"),
        qty_col=opts.get("inventory_qty_col"),
    )

    return _assemble_response(
        problem_type=problem_type,
        target_col=target_col,
        date_col=date_col,
        mode=mode or "guided",
        family_payload=family_payload,
        inventory=inventory,
    )


# ---------------------------------------------------------------------------
# Schema detection
# ---------------------------------------------------------------------------

_DATE_HINTS = (
    "date", "time", "month", "year", "day", "period", "week",
    "تاريخ", "شهر", "سنة", "يوم", "اسبوع", "أسبوع", "فترة",
)
_TARGET_HINTS = (
    "revenue", "sales", "amount", "value", "total", "price", "qty",
    "quantity", "units", "profit", "income", "spend", "cost",
)
_PRODUCT_HINTS = ("product", "sku", "item", "asin", "model", "variant")
_QTY_HINTS = ("qty", "quantity", "units", "stock", "demand", "sales")


def _is_datetime_like(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().astype(str).head(40)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, errors="coerce")
    return float(parsed.notna().mean()) >= 0.7


def _detect_date_col(df: pd.DataFrame, exclude: list[str] | None = None) -> str | None:
    excluded = set(exclude or [])
    candidates: list[tuple[int, str]] = []
    for col in df.columns:
        if col in excluded:
            continue
        if not _is_datetime_like(df[col]):
            continue
        score = sum(1 for h in _DATE_HINTS if h in str(col).lower())
        candidates.append((score, str(col)))
    if not candidates:
        return None
    candidates.sort(key=lambda kv: (-kv[0], kv[1]))
    return candidates[0][1]


def _detect_target_col(
    df: pd.DataFrame, exclude: list[str] | None = None
) -> str | None:
    excluded = set(exclude or [])
    numeric = [
        c for c in df.columns
        if c not in excluded and pd.api.types.is_numeric_dtype(df[c])
        and df[c].dropna().size >= 3
    ]
    if numeric:
        scored = [
            (sum(1 for h in _TARGET_HINTS if h in str(c).lower()),
             -float(df[c].std() or 0.0), str(c))
            for c in numeric
        ]
        scored.sort(key=lambda kv: (-kv[0], kv[1]))
        return scored[0][2]
    # Fall back to a plausible categorical target (low-cardinality).
    cats = [
        c for c in df.columns
        if c not in excluded and df[c].dropna().size >= 3
        and df[c].nunique(dropna=True) <= max(10, len(df) // 5)
    ]
    return str(cats[0]) if cats else None


def _resolve_target_col(
    df: pd.DataFrame, target_col: str | None, date_col: str | None
) -> str:
    if target_col and target_col in df.columns:
        return target_col
    detected = _detect_target_col(df, exclude=[date_col] if date_col else None)
    if not detected:
        raise ValueError("could not detect a target column for prediction")
    return detected


def _resolve_date_col(
    df: pd.DataFrame, date_col: str | None, exclude: list[str]
) -> str | None:
    if date_col and date_col in df.columns and _is_datetime_like(df[date_col]):
        return date_col
    return _detect_date_col(df, exclude=exclude)


def _detect_problem_type(
    df: pd.DataFrame, target_col: str, date_col: str | None
) -> str:
    """Return one of ``timeseries`` / ``classification`` / ``regression``."""
    target = df[target_col]
    is_numeric = pd.api.types.is_numeric_dtype(target)
    if date_col and is_numeric and len(df) >= MIN_ROWS_TIMESERIES:
        return "timeseries"
    if not is_numeric:
        return "classification"
    # Numeric but very low cardinality / integer-coded labels look like
    # classification (e.g. {0,1}, {1,2,3}).
    nunique = int(target.dropna().nunique())
    if nunique <= max(2, min(10, len(df) // 20)) and pd.api.types.is_integer_dtype(target):
        return "classification"
    return "regression"


# ---------------------------------------------------------------------------
# Feature preparation
# ---------------------------------------------------------------------------

def _numeric_features(
    df: pd.DataFrame, target_col: str, date_col: str | None
) -> pd.DataFrame:
    excluded = {target_col}
    if date_col:
        excluded.add(date_col)
    numeric = df.select_dtypes(include="number").drop(
        columns=[c for c in excluded if c in df.columns],
        errors="ignore",
    )
    return numeric


def _aligned_xy(
    df: pd.DataFrame, target_col: str, date_col: str | None
) -> tuple[pd.DataFrame, pd.Series]:
    """Return aligned (X, y) with NA rows dropped."""
    x = _numeric_features(df, target_col, date_col)
    if x.empty:
        # Fall back to a synthetic time-index feature so univariate
        # numeric series still get a regression / classification fit.
        x = pd.DataFrame({"__row_index__": np.arange(len(df), dtype=float)},
                         index=df.index)
    y = df[target_col]
    joined = pd.concat([x, y.rename("__y__")], axis=1).dropna()
    if joined.empty:
        raise ValueError("no aligned rows after dropping nulls")
    return joined.drop(columns=["__y__"]), joined["__y__"]


# ---------------------------------------------------------------------------
# Regression — fit LR + RF, pick lower RMSE
# ---------------------------------------------------------------------------

def _fit_regression_pair_and_pick(
    df: pd.DataFrame, target_col: str, test_size: float = DEFAULT_TEST_SIZE,
) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.linear_model import LinearRegression
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    from sklearn.model_selection import train_test_split

    x, y = _aligned_xy(df, target_col, date_col=None)
    if len(x) < MIN_ROWS_REGRESSION:
        raise ValueError(
            f"need at least {MIN_ROWS_REGRESSION} complete rows, got {len(x)}"
        )

    test_size = max(0.05, min(0.4, float(test_size)))
    if len(x) < 25:
        test_size = max(1.0 / len(x), min(test_size, 0.2))
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=test_size, random_state=42
    )

    candidates: list[dict[str, Any]] = []
    for name, builder in (
        ("LinearRegression", lambda: LinearRegression()),
        ("RandomForestRegressor", lambda: RandomForestRegressor(
            n_estimators=100, random_state=42, n_jobs=1,
        )),
    ):
        try:
            model = builder()
            model.fit(x_train, y_train)
            y_pred = model.predict(x_test)
            rmse = float(np.sqrt(mean_squared_error(y_test, y_pred)))
            mae = float(mean_absolute_error(y_test, y_pred))
            r2 = float(r2_score(y_test, y_pred)) if len(y_test) >= 2 else float("nan")
            candidates.append({
                "name": name,
                "model": model,
                "y_pred": y_pred,
                "rmse": rmse,
                "mae": mae,
                "r2": r2,
            })
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("regression candidate %s failed: %s", name, exc)

    if not candidates:
        raise ValueError("no regression model could be fitted")

    best = min(candidates, key=lambda c: c["rmse"])
    cv = _cross_validate_regression(best["model"], x, y, name=best["name"])
    ci = _bootstrap_regression_ci(
        best["model"], x_train, y_train, x_test, best["y_pred"],
    )

    feature_importance = _regression_feature_importance(best["model"], list(x.columns))
    if best["name"] == "RandomForestRegressor":
        _attach_shap_top(feature_importance, best["model"], x_test, list(x.columns))
    parameters = _model_parameters(best["model"])

    trend = _trend_from_predictions(np.asarray(best["y_pred"], dtype=float))

    return {
        "family": "regression",
        "model_used": best["name"],
        "candidates": [
            {"name": c["name"], "rmse": round(c["rmse"], 4),
             "mae": round(c["mae"], 4), "r2": round(c["r2"], 4)}
            for c in candidates
        ],
        "metrics": {
            "rmse": round(best["rmse"], 4),
            "mae": round(best["mae"], 4),
            "r2": round(best["r2"], 4),
            "n_train": int(len(x_train)),
            "n_test": int(len(x_test)),
        },
        "cross_validation": cv,
        "confidence_interval": ci,
        "parameters": parameters,
        "feature_importance": feature_importance,
        "predictions": [
            {"index": int(i), "yhat": float(p),
             "lower": float(ci["lower"][k]) if ci.get("lower") else None,
             "upper": float(ci["upper"][k]) if ci.get("upper") else None}
            for k, (i, p) in enumerate(zip(x_test.index.tolist(), best["y_pred"]))
        ],
        "trend_direction": trend["direction"],
        "trend_slope": trend["slope"],
    }


def _attach_shap_top(
    feature_importance: dict[str, Any],
    model: Any,
    x_test: pd.DataFrame,
    feature_names: list[str],
    top_k: int = 5,
) -> None:
    """Attach top-K SHAP feature importances to ``feature_importance``.

    Mutates the dict in-place. Adds ``shap_top`` (object of
    ``{feature: mean_abs_shap}``) when SHAP is available; otherwise
    adds an explanatory ``note`` so callers can explain the gap to
    Expert-mode users (Task #250).
    """
    try:
        import shap  # type: ignore
    except ImportError:
        feature_importance["note"] = (
            "shap_top unavailable: the 'shap' package is not installed."
        )
        return
    except Exception as exc:  # pragma: no cover - defensive
        feature_importance["note"] = f"shap_top unavailable: {exc}"
        return
    if x_test is None or len(x_test) == 0 or not feature_names:
        feature_importance["note"] = (
            "shap_top unavailable: no test rows to explain."
        )
        return
    try:
        # Cap the number of rows we explain so SHAP stays cheap on
        # large holdout sets — top features are stable past ~200 rows.
        sample = x_test.head(200) if len(x_test) > 200 else x_test
        explainer = shap.TreeExplainer(model)
        values = explainer.shap_values(sample)
        arr = np.asarray(values)
        # Classification returns one matrix per class; collapse classes
        # by averaging mean-abs across them so multi-class still gets
        # a single ranking.
        if arr.ndim == 3:
            mean_abs = np.mean(np.abs(arr), axis=(0, 1))
        elif arr.ndim == 2:
            mean_abs = np.mean(np.abs(arr), axis=0)
        else:
            mean_abs = np.abs(arr)
        if mean_abs.shape[0] != len(feature_names):
            feature_importance["note"] = (
                "shap_top unavailable: feature length mismatch."
            )
            return
        ranking = sorted(
            zip(feature_names, mean_abs.tolist()),
            key=lambda kv: float(kv[1]),
            reverse=True,
        )
        feature_importance["shap_top"] = {
            str(name): round(float(value), 5)
            for name, value in ranking[: max(1, int(top_k))]
        }
    except Exception as exc:
        feature_importance["note"] = f"shap_top unavailable: {exc}"


def _regression_feature_importance(model, feature_names: list[str]) -> dict[str, float]:
    if hasattr(model, "feature_importances_"):
        return {
            name: round(float(v), 5)
            for name, v in zip(feature_names, model.feature_importances_)
        }
    if hasattr(model, "coef_"):
        coefs = np.asarray(model.coef_, dtype=float).flatten()
        return {
            name: round(float(abs(c)), 5)
            for name, c in zip(feature_names, coefs)
        }
    return {}


def _model_parameters(model) -> dict[str, Any]:
    try:
        params = model.get_params(deep=False)
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, (int, float, str, bool)) or v is None:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Classification — RandomForest with predict_proba
# ---------------------------------------------------------------------------

def _fit_classifier(
    df: pd.DataFrame, target_col: str, test_size: float = DEFAULT_TEST_SIZE,
) -> dict[str, Any]:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        accuracy_score, f1_score, precision_score, recall_score,
    )
    from sklearn.model_selection import train_test_split

    x, y = _aligned_xy(df, target_col, date_col=None)
    if len(x) < MIN_ROWS_CLASSIFICATION:
        raise ValueError(
            f"need at least {MIN_ROWS_CLASSIFICATION} complete rows, "
            f"got {len(x)}"
        )

    classes = list(map(_normalize_label, sorted(map(str, y.dropna().unique()))))
    if len(set(classes)) < 2:
        raise ValueError("classification needs at least two distinct classes")

    test_size = max(0.05, min(0.4, float(test_size)))
    try:
        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=test_size, random_state=42, stratify=y,
        )
    except ValueError:
        # Fall back to non-stratified when a class has < 2 members.
        x_train, x_test, y_train, y_test = train_test_split(
            x, y, test_size=test_size, random_state=42,
        )

    model = RandomForestClassifier(
        n_estimators=100, random_state=42, n_jobs=1,
    )
    model.fit(x_train, y_train)
    y_pred = model.predict(x_test)

    # Use macro-averaging always so binary problems with non-numeric
    # labels work without a ``pos_label`` argument.
    avg = "macro"
    metrics = {
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "f1": round(float(f1_score(y_test, y_pred, average=avg, zero_division=0)), 4),
        "precision": round(float(precision_score(y_test, y_pred, average=avg, zero_division=0)), 4),
        "recall": round(float(recall_score(y_test, y_pred, average=avg, zero_division=0)), 4),
        "n_train": int(len(x_train)),
        "n_test": int(len(x_test)),
    }

    cv = _cross_validate_classifier(model, x, y)

    proba = None
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(x_test)
    ci = _classifier_confidence_interval(model, y_pred, proba)

    feature_importance = {
        name: round(float(v), 5)
        for name, v in zip(x.columns, model.feature_importances_)
    }
    _attach_shap_top(feature_importance, model, x_test, list(x.columns))

    return {
        "family": "classification",
        "model_used": "RandomForestClassifier",
        "classes": classes,
        "metrics": metrics,
        "cross_validation": cv,
        "confidence_interval": ci,
        "parameters": _model_parameters(model),
        "feature_importance": feature_importance,
        "predictions": [
            {"index": int(i), "predicted": _normalize_label(p)}
            for i, p in zip(x_test.index.tolist(), y_pred.tolist())
        ],
        "trend_direction": "n/a",
        "trend_slope": None,
    }


def _normalize_label(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def _classifier_confidence_interval(
    model, y_pred: np.ndarray, proba: np.ndarray | None
) -> dict[str, Any]:
    if proba is None:
        return {"method": "not_available"}
    classes = [
        _normalize_label(c) for c in getattr(model, "classes_", []).tolist()
    ]
    return {
        "method": "predict_proba",
        "classes": classes,
        "probabilities": [
            [round(float(p), 5) for p in row] for row in proba.tolist()
        ],
    }


# ---------------------------------------------------------------------------
# Time-series — Prophet (with linear-trend fallback)
# ---------------------------------------------------------------------------

def _fit_prophet(
    df: pd.DataFrame, date_col: str, target_col: str, periods: int,
) -> dict[str, Any]:
    work = pd.DataFrame({
        "ds": pd.to_datetime(df[date_col], errors="coerce"),
        "y": pd.to_numeric(df[target_col], errors="coerce"),
    }).dropna()
    # Multiple rows per timestamp (e.g. inventory data: one row per
    # SKU per day) would confuse Prophet. Sum the target so the
    # forecast operates on a clean one-row-per-period series.
    work = work.groupby("ds", as_index=False)["y"].sum()
    work = work.sort_values("ds").reset_index(drop=True)
    if len(work) < MIN_ROWS_TIMESERIES:
        raise ValueError(
            f"need at least {MIN_ROWS_TIMESERIES} time-stamped rows, "
            f"got {len(work)}"
        )

    freq = _infer_freq(work["ds"])
    history_points = [
        {"ds": d.isoformat(), "y": float(v)}
        for d, v in zip(work["ds"], work["y"])
    ]

    try:
        from prophet import Prophet  # type: ignore
        model = Prophet(
            interval_width=0.95,
            yearly_seasonality="auto",
            weekly_seasonality="auto",
            daily_seasonality=False,
        )
        model.fit(work)
        future = model.make_future_dataframe(periods=periods, freq=freq)
        fcst = model.predict(future)
        in_sample = fcst.iloc[: len(work)]
        forecast_tail = fcst.tail(periods)
        engine = "prophet"
        yhat_in = np.asarray(in_sample["yhat"], dtype=float)
        yhat_out = np.asarray(forecast_tail["yhat"], dtype=float)
        lower = np.asarray(forecast_tail["yhat_lower"], dtype=float)
        upper = np.asarray(forecast_tail["yhat_upper"], dtype=float)
        future_dates = pd.to_datetime(forecast_tail["ds"]).tolist()
    except Exception as exc:
        log.warning("prophet unavailable (%s) — degrading to linear trend", exc)
        return _fit_linear_trend(work, periods, freq, history_points)

    backtest_metrics = _regression_metrics(work["y"].to_numpy(), yhat_in)
    backtest_metrics["mape"] = _safe_mape(work["y"].to_numpy(), yhat_in)

    cv = _cross_validate_timeseries(work["y"].to_numpy(), yhat_in)
    trend = _trend_from_predictions(yhat_out)

    return {
        "family": "timeseries",
        "model_used": engine,
        "freq": freq,
        "periods": periods,
        "history": history_points,
        "forecast": [
            {"ds": pd.Timestamp(d).isoformat(),
             "yhat": float(yh), "lower": float(lo), "upper": float(up)}
            for d, yh, lo, up in zip(future_dates, yhat_out, lower, upper)
        ],
        "metrics": {
            **backtest_metrics,
            "n_train": int(len(work)),
        },
        "cross_validation": cv,
        "confidence_interval": {
            "method": "prophet_native_95",
            "lower": [float(v) for v in lower],
            "upper": [float(v) for v in upper],
        },
        "parameters": {
            "interval_width": 0.95,
            "yearly_seasonality": "auto",
            "weekly_seasonality": "auto",
            "freq": freq,
            "periods": periods,
        },
        "feature_importance": {},
        "trend_direction": trend["direction"],
        "trend_slope": trend["slope"],
    }


def _fit_linear_trend(
    work: pd.DataFrame, periods: int, freq: str, history_points: list[dict],
) -> dict[str, Any]:
    from sklearn.linear_model import LinearRegression

    x = np.arange(len(work), dtype=float).reshape(-1, 1)
    y = work["y"].to_numpy(dtype=float)
    model = LinearRegression().fit(x, y)
    fitted = model.predict(x)
    residual_std = float(np.std(y - fitted)) or 1.0
    last_ds = work["ds"].iloc[-1]
    future_dates = pd.date_range(last_ds, periods=periods + 1, freq=freq)[1:]
    future_x = np.arange(len(work), len(work) + periods, dtype=float).reshape(-1, 1)
    yhat_out = model.predict(future_x)
    lower = yhat_out - CI_Z * residual_std
    upper = yhat_out + CI_Z * residual_std
    backtest = _regression_metrics(y, fitted)
    backtest["mape"] = _safe_mape(y, fitted)
    cv = _cross_validate_timeseries(y, fitted)
    trend = _trend_from_predictions(yhat_out)
    return {
        "family": "timeseries",
        "model_used": "linear_trend",
        "freq": freq,
        "periods": periods,
        "history": history_points,
        "forecast": [
            {"ds": pd.Timestamp(d).isoformat(),
             "yhat": float(yh), "lower": float(lo), "upper": float(up)}
            for d, yh, lo, up in zip(future_dates, yhat_out, lower, upper)
        ],
        "metrics": {**backtest, "n_train": int(len(work))},
        "cross_validation": cv,
        "confidence_interval": {
            "method": "analytical_95",
            "lower": [float(v) for v in lower],
            "upper": [float(v) for v in upper],
        },
        "parameters": {"freq": freq, "periods": periods, "model": "linear_trend"},
        "feature_importance": {},
        "trend_direction": trend["direction"],
        "trend_slope": trend["slope"],
    }


def _infer_freq(times: pd.Series) -> str:
    parsed = pd.to_datetime(times, errors="coerce").dropna().sort_values()
    if len(parsed) < 3:
        return "D"
    deltas = parsed.diff().dropna().dt.days
    if deltas.empty:
        return "D"
    median = float(deltas.median())
    if median <= 1.5:
        return "D"
    if median <= 8.0:
        return "W"
    if median <= 45.0:
        return "MS"
    if median <= 110.0:
        return "QS"
    return "YS"


def _safe_mape(y_true: np.ndarray, y_pred: np.ndarray) -> float | None:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    mask = y_true != 0
    if not mask.any():
        return None
    return round(float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask]))), 4)


def _regression_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
    rmse = float(np.sqrt(mean_squared_error(y_true, y_pred)))
    mae = float(mean_absolute_error(y_true, y_pred))
    try:
        r2 = float(r2_score(y_true, y_pred))
    except Exception:
        r2 = float("nan")
    return {"rmse": round(rmse, 4), "mae": round(mae, 4), "r2": round(r2, 4)}


def _trend_from_predictions(values: np.ndarray) -> dict[str, Any]:
    arr = np.asarray(values, dtype=float)
    if arr.size < 2:
        return {"slope": 0.0, "direction": "stable"}
    x = np.arange(arr.size, dtype=float)
    if float(np.std(arr)) == 0.0:
        return {"slope": 0.0, "direction": "stable"}
    # Slope of an OLS line through the predictions.
    slope = float(np.polyfit(x, arr, 1)[0])
    spread = float(np.std(arr)) or 1.0
    if abs(slope) < 0.01 * spread:
        direction = "stable"
    elif slope > 0:
        direction = "increasing"
    else:
        direction = "decreasing"
    return {"slope": round(slope, 6), "direction": direction}


# ---------------------------------------------------------------------------
# Cross-validation
# ---------------------------------------------------------------------------

def _cross_validate_regression(model, x: pd.DataFrame, y: pd.Series, name: str) -> dict[str, Any]:
    from sklearn.base import clone
    from sklearn.model_selection import KFold
    from sklearn.metrics import mean_squared_error
    n = len(x)
    folds = max(2, min(CV_FOLDS, n))
    kf = KFold(n_splits=folds, shuffle=True, random_state=42)
    scores: list[float] = []
    for train_idx, test_idx in kf.split(x):
        try:
            m = clone(model)
            m.fit(x.iloc[train_idx], y.iloc[train_idx])
            preds = m.predict(x.iloc[test_idx])
            score = float(np.sqrt(mean_squared_error(y.iloc[test_idx], preds)))
            scores.append(score)
        except Exception:
            continue
    return {
        "metric": "rmse",
        "folds": folds,
        "scores": [round(s, 4) for s in scores],
        "mean": round(float(np.mean(scores)), 4) if scores else None,
        "std": round(float(np.std(scores)), 4) if scores else None,
        "model": name,
    }


def _cross_validate_classifier(model, x: pd.DataFrame, y: pd.Series) -> dict[str, Any]:
    from sklearn.base import clone
    from sklearn.metrics import accuracy_score
    from sklearn.model_selection import StratifiedKFold, KFold
    n = len(x)
    folds = max(2, min(CV_FOLDS, n))
    # StratifiedKFold needs at least `folds` members per class.
    counts = y.value_counts(dropna=True)
    if int(counts.min()) >= folds:
        splitter = StratifiedKFold(n_splits=folds, shuffle=True, random_state=42)
    else:
        splitter = KFold(n_splits=folds, shuffle=True, random_state=42)
    scores: list[float] = []
    for train_idx, test_idx in splitter.split(x, y):
        try:
            m = clone(model)
            m.fit(x.iloc[train_idx], y.iloc[train_idx])
            preds = m.predict(x.iloc[test_idx])
            scores.append(float(accuracy_score(y.iloc[test_idx], preds)))
        except Exception:
            continue
    return {
        "metric": "accuracy",
        "folds": folds,
        "scores": [round(s, 4) for s in scores],
        "mean": round(float(np.mean(scores)), 4) if scores else None,
        "std": round(float(np.std(scores)), 4) if scores else None,
        "model": "RandomForestClassifier",
    }


def _cross_validate_timeseries(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, Any]:
    """Backtested-block CV summary on the in-sample fit."""
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    n = len(y_true)
    folds = max(2, min(CV_FOLDS, n // 3 or 2))
    chunk = max(1, n // folds)
    scores: list[float] = []
    for k in range(folds):
        start = k * chunk
        end = (k + 1) * chunk if k < folds - 1 else n
        if end <= start:
            continue
        block_true = y_true[start:end]
        block_pred = y_pred[start:end]
        if block_true.size == 0:
            continue
        rmse = float(np.sqrt(np.mean((block_true - block_pred) ** 2)))
        scores.append(rmse)
    return {
        "metric": "rmse",
        "folds": len(scores),
        "scores": [round(s, 4) for s in scores],
        "mean": round(float(np.mean(scores)), 4) if scores else None,
        "std": round(float(np.std(scores)), 4) if scores else None,
        "model": "block_backtest",
    }


# ---------------------------------------------------------------------------
# Confidence intervals — bootstrap for sklearn regressors
# ---------------------------------------------------------------------------

def _bootstrap_regression_ci(
    model, x_train: pd.DataFrame, y_train: pd.Series,
    x_test: pd.DataFrame, y_pred: np.ndarray,
) -> dict[str, Any]:
    """Wild bootstrap-style residual CI (95%).

    Resamples residuals from the in-sample fit and adds them to the
    point predictions to derive a 2.5 / 97.5 quantile band per
    prediction. Lightweight and works for any sklearn regressor.
    """
    try:
        in_sample = model.predict(x_train)
        residuals = np.asarray(y_train, dtype=float) - np.asarray(in_sample, dtype=float)
        residuals = residuals[np.isfinite(residuals)]
        if residuals.size == 0:
            raise ValueError("empty residuals")
        rng = np.random.default_rng(42)
        boot = rng.choice(
            residuals,
            size=(BOOTSTRAP_SAMPLES, len(y_pred)),
            replace=True,
        )
        sims = np.asarray(y_pred, dtype=float)[None, :] + boot
        lower = np.percentile(sims, 2.5, axis=0)
        upper = np.percentile(sims, 97.5, axis=0)
        return {
            "method": "bootstrap_95",
            "samples": BOOTSTRAP_SAMPLES,
            "lower": [float(v) for v in lower],
            "upper": [float(v) for v in upper],
        }
    except Exception as exc:
        log.warning("bootstrap CI failed (%s) — falling back to analytical", exc)
        std = float(np.std(np.asarray(y_pred, dtype=float))) or 1.0
        lower = np.asarray(y_pred, dtype=float) - CI_Z * std
        upper = np.asarray(y_pred, dtype=float) + CI_Z * std
        return {
            "method": "analytical_95",
            "lower": [float(v) for v in lower],
            "upper": [float(v) for v in upper],
        }


# ---------------------------------------------------------------------------
# Inventory / sales helpers
# ---------------------------------------------------------------------------

def _detect_inventory_columns(
    df: pd.DataFrame, product_col: str | None, qty_col: str | None,
    date_col: str | None,
) -> tuple[str | None, str | None]:
    if product_col and product_col in df.columns:
        prod = product_col
    else:
        prod = None
        for c in df.columns:
            name = str(c).lower()
            if any(h in name for h in _PRODUCT_HINTS) and not pd.api.types.is_numeric_dtype(df[c]):
                prod = str(c)
                break
    if qty_col and qty_col in df.columns:
        qty = qty_col
    else:
        qty = None
        for c in df.columns:
            name = str(c).lower()
            if any(h in name for h in _QTY_HINTS) and pd.api.types.is_numeric_dtype(df[c]):
                qty = str(c)
                break
    if not prod or not qty or not date_col:
        return prod, qty
    return prod, qty


def _maybe_inventory_signals(
    df: pd.DataFrame, target_col: str, date_col: str | None,
    stockout_horizon: int,
    product_col: str | None = None,
    qty_col: str | None = None,
) -> dict[str, Any] | None:
    if not date_col:
        return None
    prod, qty = _detect_inventory_columns(df, product_col, qty_col, date_col)
    if not prod or not qty:
        return None
    return _inventory_signals(
        df, product_col=prod, qty_col=qty, date_col=date_col,
        stockout_horizon=stockout_horizon,
    )


def _inventory_signals(
    df: pd.DataFrame, product_col: str, qty_col: str, date_col: str,
    stockout_horizon: int = DEFAULT_STOCKOUT_HORIZON_DAYS,
) -> dict[str, Any]:
    """Per-product inventory/sales signals.

    Returns horizons (7/14/30 days), declining-trend flags,
    days-to-stockout flags, and a discount tier per product.
    """
    work = pd.DataFrame({
        "product": df[product_col].astype(str),
        "ds": pd.to_datetime(df[date_col], errors="coerce"),
        "qty": pd.to_numeric(df[qty_col], errors="coerce"),
    }).dropna()
    if work.empty:
        return {
            "available": False,
            "products": [],
            "declining": [],
            "stockout_risk": [],
            "discount_suggestions": [],
        }
    today = work["ds"].max()

    products: list[dict[str, Any]] = []
    declining: list[dict[str, Any]] = []
    stockout: list[dict[str, Any]] = []
    discounts: list[dict[str, Any]] = []

    for prod, sub in work.groupby("product"):
        sub = sub.sort_values("ds")
        # Aggregate to per-day quantities so the trend / forecast works
        # on a regular axis even when the raw rows are uneven.
        daily = (
            sub.set_index("ds")["qty"].resample("D").sum().fillna(0.0)
        )
        if daily.empty:
            continue
        x = np.arange(len(daily), dtype=float)
        y = daily.to_numpy(dtype=float)
        slope = float(np.polyfit(x, y, 1)[0]) if len(y) >= 2 else 0.0
        intercept = float(np.polyfit(x, y, 1)[1]) if len(y) >= 2 else float(y.mean())
        avg_daily = float(y.mean()) if len(y) > 0 else 0.0
        last_seen = sub["ds"].max()
        days_since = int((today - last_seen).days)

        forecasts: dict[str, float] = {}
        for h in (7, 14, 30):
            future_x = np.arange(len(daily), len(daily) + h, dtype=float)
            preds = intercept + slope * future_x
            forecasts[f"next_{h}_days"] = round(float(preds.sum()), 4)

        product_payload = {
            "product": str(prod),
            "history_days": int(len(daily)),
            "avg_daily": round(avg_daily, 4),
            "slope": round(slope, 6),
            "days_since_last_activity": days_since,
            "forecasts": forecasts,
        }
        products.append(product_payload)

        if slope < 0:
            declining.append({"product": str(prod), "slope": round(slope, 6)})

        # Days-to-stockout: treat the latest observed daily quantity as
        # remaining stock and divide by the average outflow.
        latest_stock = float(y[-1])
        if avg_daily > 0:
            days_to_zero = latest_stock / avg_daily
            if days_to_zero <= stockout_horizon:
                stockout.append({
                    "product": str(prod),
                    "stock_remaining": round(latest_stock, 4),
                    "avg_daily_outflow": round(avg_daily, 4),
                    "days_to_zero": round(float(days_to_zero), 2),
                })

        tier = _discount_tier(days_since)
        if tier:
            discounts.append({
                "product": str(prod),
                "days_since_last_activity": days_since,
                **tier,
            })

    return {
        "available": True,
        "as_of": today.isoformat(),
        "stockout_horizon_days": stockout_horizon,
        "products": products,
        "declining": declining,
        "stockout_risk": stockout,
        "discount_suggestions": discounts,
    }


def _discount_tier(days_since: int) -> dict[str, Any] | None:
    """Map age (days) to a discount tier per the spec."""
    if days_since > 120:
        return {"tier": "bundle_clearance", "discount_pct": None,
                "action": "bundle/clearance"}
    if days_since > 90:
        return {"tier": "deep_discount", "discount_pct": 30, "action": "30% discount"}
    if days_since > 60:
        return {"tier": "light_discount", "discount_pct": 20, "action": "20% discount"}
    return None


# ---------------------------------------------------------------------------
# Dual-payload assembler
# ---------------------------------------------------------------------------

def _assemble_response(
    problem_type: str,
    target_col: str,
    date_col: str | None,
    mode: str,
    family_payload: dict[str, Any],
    inventory: dict[str, Any] | None,
) -> dict[str, Any]:
    expert: dict[str, Any] = {
        "model_used": family_payload.get("model_used"),
        "problem_type": problem_type,
        "target": target_col,
        "date_column": date_col,
        "metrics": family_payload.get("metrics", {}),
        "cross_validation": family_payload.get("cross_validation", {}),
        "parameters": family_payload.get("parameters", {}),
        "feature_importance": family_payload.get("feature_importance", {}),
        "confidence_interval": family_payload.get("confidence_interval", {}),
        "trend_direction": family_payload.get("trend_direction"),
        "trend_slope": family_payload.get("trend_slope"),
        "predictions": family_payload.get("predictions") or family_payload.get("forecast", []),
    }
    # Family-specific extras the Expert UI may want to show.
    for key in ("freq", "periods", "history", "forecast", "candidates", "classes"):
        if key in family_payload:
            expert[key] = family_payload[key]
    if inventory is not None:
        expert["inventory"] = inventory

    confidence_score, confidence_band = _confidence_from_metrics(
        problem_type, family_payload
    )
    summary = _guided_summary(problem_type, target_col, family_payload, confidence_band)
    recommendations = _guided_recommendations(
        problem_type, family_payload, inventory
    )
    guided = {
        "summary": summary,
        "confidence": confidence_band,
        "confidence_score": round(confidence_score, 4),
        "recommendations": recommendations,
    }
    if inventory and inventory.get("available"):
        guided["inventory_highlights"] = _inventory_highlights(inventory)

    return {
        "guided": guided,
        "expert": expert,
        "mode": mode,
    }


def _confidence_from_metrics(
    problem_type: str, family_payload: dict[str, Any]
) -> tuple[float, str]:
    metrics = family_payload.get("metrics", {}) or {}
    if problem_type == "regression":
        r2 = float(metrics.get("r2") or 0.0)
        score = max(0.0, min(1.0, r2))
    elif problem_type == "classification":
        score = max(0.0, min(1.0, float(metrics.get("accuracy") or 0.0)))
    elif problem_type == "timeseries":
        mape = metrics.get("mape")
        if mape is None or not math.isfinite(float(mape)):
            score = 0.5
        else:
            # MAPE 0 → score 1.0; MAPE 1.0+ → score 0.0.
            score = max(0.0, min(1.0, 1.0 - float(mape)))
    else:  # pragma: no cover - defensive
        score = 0.5
    if score >= 0.75:
        band = "high"
    elif score >= 0.5:
        band = "medium"
    else:
        band = "low"
    return score, band


def _guided_summary(
    problem_type: str, target_col: str, family_payload: dict[str, Any],
    confidence: str,
) -> str:
    metrics = family_payload.get("metrics", {}) or {}
    model = family_payload.get("model_used", "model")
    if problem_type == "regression":
        return (
            f"Predicted '{target_col}' with {model}. "
            f"R²={metrics.get('r2', 0):.2f}, RMSE={metrics.get('rmse', 0):.2f}. "
            f"Confidence: {confidence}."
        )
    if problem_type == "classification":
        return (
            f"Classified '{target_col}' with {model}. "
            f"Accuracy={metrics.get('accuracy', 0):.2%}, "
            f"F1={metrics.get('f1', 0):.2f}. Confidence: {confidence}."
        )
    if problem_type == "timeseries":
        mape = metrics.get("mape")
        mape_txt = f"MAPE={mape:.2%}" if mape is not None else "MAPE=n/a"
        return (
            f"Forecasted '{target_col}' with {model} for "
            f"{family_payload.get('periods', 0)} period(s). "
            f"{mape_txt}. Confidence: {confidence}."
        )
    return f"Prediction for '{target_col}' completed."  # pragma: no cover


def _guided_recommendations(
    problem_type: str, family_payload: dict[str, Any],
    inventory: dict[str, Any] | None,
) -> list[str]:
    recs: list[str] = []
    metrics = family_payload.get("metrics", {}) or {}
    trend = family_payload.get("trend_direction")
    if problem_type == "regression":
        r2 = float(metrics.get("r2") or 0.0)
        if r2 < 0.5:
            recs.append(
                "Model fit is weak — consider adding more features or "
                "more rows before relying on the predictions."
            )
        elif r2 < 0.75:
            recs.append("Moderate fit — verify with a holdout dataset.")
        else:
            recs.append("Strong fit — predictions are reliable for planning.")
        fi = family_payload.get("feature_importance") or {}
        if fi:
            # Skip non-numeric extras like ``shap_top`` / ``note``
            # added by the SHAP hook so the recommendation only
            # ranks real per-feature scores.
            numeric_fi = [
                (k, v) for k, v in fi.items()
                if isinstance(v, (int, float))
            ]
            if numeric_fi:
                top = sorted(numeric_fi, key=lambda kv: kv[1], reverse=True)[:1]
                recs.append(
                    f"Focus on '{top[0][0]}' — it has the largest impact on the target."
                )
    elif problem_type == "classification":
        acc = float(metrics.get("accuracy") or 0.0)
        if acc < 0.6:
            recs.append("Accuracy is low — add more features or rebalance classes.")
        else:
            recs.append("Use predicted probabilities to prioritise high-confidence cases.")
    elif problem_type == "timeseries":
        if trend == "increasing":
            recs.append("Trend is rising — plan for higher capacity.")
        elif trend == "decreasing":
            recs.append("Trend is falling — investigate causes and consider promotions.")
        else:
            recs.append("Trend is stable — keep current operations and re-check weekly.")
    if inventory and inventory.get("available"):
        if inventory.get("stockout_risk"):
            recs.append(
                f"{len(inventory['stockout_risk'])} product(s) at risk of stockout — "
                "reorder soon."
            )
        if inventory.get("discount_suggestions"):
            recs.append(
                f"{len(inventory['discount_suggestions'])} aging product(s) — "
                "apply suggested discounts to clear stock."
            )
    return recs[:5]


def _inventory_highlights(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "products_tracked": len(inventory.get("products") or []),
        "declining_count": len(inventory.get("declining") or []),
        "stockout_count": len(inventory.get("stockout_risk") or []),
        "discount_count": len(inventory.get("discount_suggestions") or []),
    }


__all__ = [
    "run_prediction",
    "MIN_ROWS_REGRESSION",
    "MIN_ROWS_CLASSIFICATION",
    "MIN_ROWS_TIMESERIES",
    "DEFAULT_PERIODS",
    "DEFAULT_STOCKOUT_HORIZON_DAYS",
]
