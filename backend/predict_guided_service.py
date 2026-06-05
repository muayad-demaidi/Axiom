"""Service layer for the guided predictive flow (Task #212).

Pure ML + LLM logic — no FastAPI imports here. Public surface:

  • ``analyze_dataset(df)`` — profile the dataset, detect the time
    column, propose a target, rank likely drivers, and produce the
    Arabic clarifying questions used by the wizard's "Questioning"
    phase.
  • ``run_prediction(df, target, time_column, drivers, answers)`` —
    fit the appropriate model (Prophet for time-series, scikit-learn
    LinearRegression / RandomForest for driver-based targets),
    compute a confidence score with sub-scores, and wrap the ML
    numbers in an Arabic narrative via GPT-4o.

The two LLM calls are isolated in ``_gpt4o_analyze`` and
``_arabic_narrative`` so tests can stub them via monkeypatching the
module-level ``_chat_completion`` helper.

The narrative call receives every numeric value as an
already-formatted Arabic string and is instructed to quote them
verbatim — the model never invents a number.
"""
from __future__ import annotations

import json
import logging
import math
from typing import Any

import numpy as np
import pandas as pd

from context.type_inference import to_numeric_canonical as _canonical_num  # type: ignore

log = logging.getLogger("axiom.predict_guided")


GUIDED_FLOW_TAG = "guided"
MIN_ROWS_REGRESSION = 10
MIN_ROWS_TIMESERIES = 12


# ---------------------------------------------------------------------------
# Profiling: detect time column, candidate target, and likely drivers
# ---------------------------------------------------------------------------

_TIME_COLUMN_HINTS = (
    "date", "time", "month", "year", "day", "period", "week",
    "تاريخ", "شهر", "سنة", "يوم", "اسبوع", "أسبوع", "فترة",
)
_TARGET_COLUMN_HINTS = (
    "revenue", "sales", "amount", "value", "total", "price", "qty",
    "quantity", "units", "profit", "income", "spend", "cost",
    "ايراد", "إيراد", "مبيعات", "قيمة", "سعر", "كمية", "ربح",
    "مصروف", "تكلفة", "دخل",
)


def _column_score(name: str, hints: tuple[str, ...]) -> int:
    n = str(name).strip().lower()
    return sum(1 for h in hints if h in n)


def _is_datetime_like(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().astype(str).head(40)
    if sample.empty:
        return False
    parsed = pd.to_datetime(sample, errors="coerce")
    return parsed.notna().mean() >= 0.7


def detect_time_column(df: pd.DataFrame) -> str | None:
    """Pick the column most likely to be a time axis.

    Prefers columns whose name suggests a date / time, then falls back
    to any column whose values parse as dates for ≥70 % of non-null
    rows.
    """
    candidates: list[tuple[int, str]] = []
    for col in df.columns:
        score = _column_score(col, _TIME_COLUMN_HINTS)
        if score == 0 and not _is_datetime_like(df[col]):
            continue
        if not _is_datetime_like(df[col]):
            continue
        candidates.append((score, str(col)))
    if not candidates:
        return None
    candidates.sort(key=lambda kv: (-kv[0], kv[1]))
    return candidates[0][1]


def detect_target_column(
    df: pd.DataFrame, exclude: list[str] | None = None
) -> str | None:
    """Pick the most plausible numeric target.

    Heuristic: prefer numeric columns whose name matches a known
    target hint (revenue / sales / etc.), then fall back to the
    numeric column with the highest variance (more signal => more
    interesting to predict).
    """
    excluded = set(exclude or [])
    numeric_cols = [
        c for c in df.columns
        if c not in excluded and pd.api.types.is_numeric_dtype(df[c])
        and df[c].dropna().size >= 3
    ]
    if not numeric_cols:
        return None
    scored = [
        (_column_score(c, _TARGET_COLUMN_HINTS), -float(df[c].std() or 0.0), str(c))
        for c in numeric_cols
    ]
    scored.sort(key=lambda kv: (-kv[0], kv[1]))
    return scored[0][2]


def rank_drivers(
    df: pd.DataFrame, target: str, time_column: str | None, top_k: int = 5
) -> list[dict[str, Any]]:
    """Rank candidate driver columns by absolute correlation with the target."""
    if target not in df.columns:
        return []
    excluded = {target}
    if time_column:
        excluded.add(time_column)
    target_series = _canonical_num(df[target])
    if target_series.dropna().size < 3:
        return []

    rows: list[dict[str, Any]] = []
    for col in df.columns:
        if col in excluded:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        x = _canonical_num(df[col])
        joined = pd.concat([x, target_series], axis=1).dropna()
        if len(joined) < 3:
            continue
        x_clean = joined.iloc[:, 0]
        y_clean = joined.iloc[:, 1]
        if x_clean.std() == 0 or y_clean.std() == 0:
            continue
        corr = float(x_clean.corr(y_clean))
        if math.isnan(corr):
            continue
        rows.append(
            {
                "column": str(col),
                "correlation": round(corr, 4),
                "abs_correlation": round(abs(corr), 4),
            }
        )
    rows.sort(key=lambda r: r["abs_correlation"], reverse=True)
    return rows[:top_k]


# ---------------------------------------------------------------------------
# Confidence score
# ---------------------------------------------------------------------------

def _bound01(x: float) -> float:
    if not math.isfinite(x):
        return 0.0
    return max(0.0, min(1.0, x))


def compute_confidence(sub_scores: dict[str, float]) -> dict[str, Any]:
    """Blend the four sub-scores into a 0–100 confidence value.

    Sub-scores are each in [0, 1]; the overall score is a weighted
    average. Weights are stored alongside the result so the UI can
    explain "why" the confidence is high or low.
    """
    weights = {
        "data_volume": 0.25,
        "data_quality": 0.20,
        "signal_strength": 0.40,
        "time_coverage": 0.15,
    }
    bounded = {k: _bound01(float(sub_scores.get(k, 0.0))) for k in weights}
    overall = sum(bounded[k] * w for k, w in weights.items())
    band = "low"
    if overall >= 0.75:
        band = "high"
    elif overall >= 0.50:
        band = "medium"
    return {
        "score": round(overall * 100.0, 1),
        "band": band,
        "weights": weights,
        "sub_scores": {k: round(bounded[k] * 100.0, 1) for k in weights},
    }


def _data_volume_score(n_rows: int) -> float:
    # Smooth ramp: 10 rows ≈ 0.3, 100 rows ≈ 0.7, 1k+ rows ≈ 1.0.
    if n_rows <= 0:
        return 0.0
    return _bound01(math.log10(max(n_rows, 1)) / 3.0)


def _data_quality_score(df: pd.DataFrame, columns: list[str]) -> float:
    if df.empty or not columns:
        return 0.0
    present = [c for c in columns if c in df.columns]
    if not present:
        return 0.0
    fracs = [float(df[c].notna().mean()) for c in present]
    return _bound01(sum(fracs) / len(fracs))


def _time_coverage_score(times: pd.Series) -> float:
    series = pd.to_datetime(times, errors="coerce").dropna().sort_values()
    if len(series) < 4:
        return 0.0
    span_days = (series.iloc[-1] - series.iloc[0]).days
    if span_days <= 0:
        return 0.0
    # ~12 distinct buckets across the span counts as "good coverage".
    bucket_count = min(series.nunique(), 365)
    return _bound01(0.4 * (bucket_count / 12.0) + 0.6 * (span_days / 365.0))


# ---------------------------------------------------------------------------
# Forecasting models
# ---------------------------------------------------------------------------

def _fit_prophet(
    df: pd.DataFrame, time_column: str, target: str, periods: int
) -> dict[str, Any]:
    """Fit Prophet on (time, target) — fall back to a sklearn trend
    fit if Prophet is unavailable for any reason."""
    work = pd.DataFrame(
        {
            "ds": pd.to_datetime(df[time_column], errors="coerce"),
            "y": _canonical_num(df[target]),
        }
    ).dropna()
    work = work.sort_values("ds").reset_index(drop=True)
    if len(work) < MIN_ROWS_TIMESERIES:
        raise ValueError(
            f"need at least {MIN_ROWS_TIMESERIES} time-stamped rows, "
            f"got {len(work)}"
        )

    freq = _infer_freq(work["ds"])
    try:
        from prophet import Prophet  # type: ignore

        model = Prophet(
            interval_width=0.85,
            yearly_seasonality="auto",
            weekly_seasonality="auto",
            daily_seasonality=False,
        )
        model.fit(work)
        future = model.make_future_dataframe(periods=periods, freq=freq)
        fcst = model.predict(future)
        # In-sample MAPE from fitted values against actuals.
        in_sample = fcst.iloc[: len(work)]
        mape = _safe_mape(work["y"].to_numpy(), in_sample["yhat"].to_numpy())
        history_points = [
            {"ds": d.isoformat(), "y": float(v)}
            for d, v in zip(work["ds"], work["y"])
        ]
        forecast_points = [
            {
                "ds": pd.Timestamp(r["ds"]).isoformat(),
                "yhat": float(r["yhat"]),
                "lower": float(r["yhat_lower"]),
                "upper": float(r["yhat_upper"]),
            }
            for _, r in fcst.tail(periods).iterrows()
        ]
        # Out-of-sample naive-baseline guardrail (shared with the
        # predictions engine): refit on an earlier slice, score the
        # held-out tail, and flag the forecast when it can't beat a
        # random walk so the guided UI never over-promises.
        from . import predictions_engine as pe

        def _prophet_refit(train_df: pd.DataFrame, h: int) -> np.ndarray:
            m = Prophet(
                interval_width=0.85,
                yearly_seasonality="auto",
                weekly_seasonality="auto",
                daily_seasonality=False,
            )
            m.fit(train_df[["ds", "y"]])
            fut = m.make_future_dataframe(periods=h, freq=freq)
            return m.predict(fut)["yhat"].to_numpy()[-h:]

        holdout_mase = pe._walk_forward_mase(work, _prophet_refit)
        baseline = pe._baseline_status(holdout_mase)
        return {
            "engine": "prophet",
            "freq": freq,
            "periods": periods,
            "history": history_points,
            "forecast": forecast_points,
            "metrics": {
                "mape": round(mape, 4) if mape is not None else None,
                "mase": holdout_mase,
                "n_train": int(len(work)),
            },
            "quality_status": baseline["quality_status"],
            "baseline_warning": baseline["warning"],
        }
    except Exception as exc:
        log.warning(
            "Prophet unavailable (%s) — trying Holt-Winters (statsmodels)",
            exc,
        )
        try:
            return _fit_holt_winters(work, periods, freq)
        except Exception as exc2:
            log.warning(
                "Holt-Winters failed (%s) — degrading to linear trend fit",
                exc2,
            )
            return _fit_linear_trend(work, periods, freq)


def _seasonal_periods(freq: str) -> int:
    """Observations per seasonal cycle for the inferred frequency."""
    return {"D": 7, "W": 52, "MS": 12, "M": 12, "QS": 4, "Q": 4}.get(freq, 0)


def _fit_holt_winters(
    work: pd.DataFrame, periods: int, freq: str
) -> dict[str, Any]:
    """Holt-Winters (statsmodels) trend + seasonal forecast.

    Sits between Prophet and the linear fallback: it captures both trend
    and seasonality with a dependency that is already installed and far
    lighter than Prophet (no Stan/cmdstanpy, no OOM risk on small free
    instances). Seasonality is only switched on with at least two full
    cycles of history; otherwise it degrades to a damped trend fit.
    Raises on any failure so the caller drops to the linear fit — a
    forecast is always produced.
    """
    from statsmodels.tsa.holtwinters import ExponentialSmoothing

    y = work["y"].to_numpy(dtype=float)
    n = y.size
    m = _seasonal_periods(freq)
    use_seasonal = m >= 2 and n >= 2 * m

    def _fit(arr: np.ndarray):
        kw: dict[str, Any] = {
            "trend": "add",
            "initialization_method": "estimated",
        }
        if m >= 2 and arr.size >= 2 * m:
            kw["seasonal"] = "add"
            kw["seasonal_periods"] = m
        return ExponentialSmoothing(arr, **kw).fit()

    model = _fit(y)
    fitted = np.asarray(model.fittedvalues, dtype=float)
    yhat = np.asarray(model.forecast(periods), dtype=float)
    mape = _safe_mape(y, fitted)
    resid_std = float(np.std(y - fitted)) or 1.0

    last_ds = work["ds"].iloc[-1]
    future_dates = pd.date_range(last_ds, periods=periods + 1, freq=freq)[1:]
    history_points = [
        {"ds": d.isoformat(), "y": float(v)}
        for d, v in zip(work["ds"], work["y"])
    ]
    forecast_points = [
        {
            "ds": pd.Timestamp(d).isoformat(),
            "yhat": float(p),
            "lower": float(p - 1.96 * resid_std),
            "upper": float(p + 1.96 * resid_std),
        }
        for d, p in zip(future_dates, yhat)
    ]

    from . import predictions_engine as pe

    def _hw_refit(train_df: pd.DataFrame, h: int) -> np.ndarray:
        return np.asarray(
            _fit(train_df["y"].to_numpy(dtype=float)).forecast(h), dtype=float
        )

    # When seasonality is in play, the holdout is only trustworthy if the
    # training window keeps at least two full cycles — otherwise the
    # refit silently drops to trend-only and unfairly fails a genuinely
    # seasonal forecast. Below that bar we return UNKNOWN (no false
    # alarm) rather than a misleading MASE.
    min_train = 2 * m if use_seasonal else MIN_ROWS_TIMESERIES
    holdout_mase = pe._walk_forward_mase(work, _hw_refit, min_train=min_train)
    baseline = pe._baseline_status(holdout_mase)
    return {
        "engine": "holt_winters_seasonal" if use_seasonal else "holt_winters",
        "freq": freq,
        "periods": periods,
        "history": history_points,
        "forecast": forecast_points,
        "metrics": {
            "mape": round(mape, 4) if mape is not None else None,
            "mase": holdout_mase,
            "n_train": int(n),
        },
        "quality_status": baseline["quality_status"],
        "baseline_warning": baseline["warning"],
    }


def _fit_linear_trend(
    work: pd.DataFrame, periods: int, freq: str
) -> dict[str, Any]:
    """Graceful sklearn fallback when Prophet can't load."""
    from sklearn.linear_model import LinearRegression

    x = np.arange(len(work)).reshape(-1, 1)
    y = work["y"].to_numpy()
    model = LinearRegression().fit(x, y)
    fitted = model.predict(x)
    mape = _safe_mape(y, fitted)
    residual_std = float(np.std(y - fitted)) or 1.0

    last_ds = work["ds"].iloc[-1]
    future_dates = pd.date_range(
        last_ds, periods=periods + 1, freq=freq
    )[1:]
    future_x = np.arange(len(work), len(work) + periods).reshape(-1, 1)
    yhat = model.predict(future_x)
    history_points = [
        {"ds": d.isoformat(), "y": float(v)}
        for d, v in zip(work["ds"], work["y"])
    ]
    forecast_points = [
        {
            "ds": pd.Timestamp(d).isoformat(),
            "yhat": float(p),
            "lower": float(p - 1.96 * residual_std),
            "upper": float(p + 1.96 * residual_std),
        }
        for d, p in zip(future_dates, yhat)
    ]
    # Out-of-sample naive-baseline guardrail (walk-forward holdout).
    from . import predictions_engine as pe

    def _linear_refit(train_df: pd.DataFrame, h: int) -> np.ndarray:
        ty = train_df["y"].to_numpy(dtype=float)
        tx = np.arange(ty.size).reshape(-1, 1)
        mm = LinearRegression().fit(tx, ty)
        fx = np.arange(ty.size, ty.size + h).reshape(-1, 1)
        return mm.predict(fx)

    holdout_mase = pe._walk_forward_mase(work, _linear_refit)
    baseline = pe._baseline_status(holdout_mase)
    return {
        "engine": "linear_trend",
        "freq": freq,
        "periods": periods,
        "history": history_points,
        "forecast": forecast_points,
        "metrics": {
            "mape": round(mape, 4) if mape is not None else None,
            "mase": holdout_mase,
            "n_train": int(len(work)),
        },
        "quality_status": baseline["quality_status"],
        "baseline_warning": baseline["warning"],
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
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])))


def _fit_driver_model(
    df: pd.DataFrame, target: str, drivers: list[str], use_random_forest: bool
) -> dict[str, Any]:
    from sklearn.linear_model import LinearRegression
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.metrics import mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    feats = [c for c in drivers if c in df.columns and c != target]
    if not feats:
        raise ValueError("no usable driver columns")
    work = df[feats + [target]].apply(_canonical_num).dropna()
    if len(work) < MIN_ROWS_REGRESSION:
        raise ValueError(
            f"need at least {MIN_ROWS_REGRESSION} complete rows, "
            f"got {len(work)}"
        )
    x = work[feats]
    y = work[target]
    test_size = 0.2 if len(work) >= 25 else 0.1
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=test_size, random_state=42
    )

    if use_random_forest:
        model = RandomForestRegressor(n_estimators=120, random_state=42)
        model.fit(x_train, y_train)
        y_pred = model.predict(x_test)
        importance = [
            {"feature": str(f), "importance": round(float(imp), 5)}
            for f, imp in zip(feats, model.feature_importances_)
        ]
        engine = "random_forest"
    else:
        model = LinearRegression().fit(x_train, y_train)
        y_pred = model.predict(x_test)
        importance = [
            {
                "feature": str(f),
                "importance": round(abs(float(c)), 5),
                "coefficient": round(float(c), 5),
            }
            for f, c in zip(feats, model.coef_)
        ]
        engine = "linear_regression"
    importance.sort(key=lambda r: r["importance"], reverse=True)

    r2 = float(r2_score(y_test, y_pred))
    mae = float(mean_absolute_error(y_test, y_pred))

    feature_means = {f: float(x[f].mean()) for f in feats}
    baseline_input = pd.DataFrame([feature_means])
    baseline = float(model.predict(baseline_input)[0])
    return {
        "engine": engine,
        "metrics": {
            "r2": round(r2, 4),
            "mae": round(mae, 4),
            "n_train": int(len(x_train)),
            "n_test": int(len(x_test)),
        },
        "feature_importance": importance,
        "feature_means": feature_means,
        "baseline_prediction": baseline,
        "drivers": feats,
    }


# ---------------------------------------------------------------------------
# Number formatting helpers (Arabic-friendly)
# ---------------------------------------------------------------------------

def _fmt_number(value: float | int | None) -> str:
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:,.1f}"
    return f"{value:,.3f}"


def _fmt_percent(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "—"
    return f"{value * 100:.1f}%"


# ---------------------------------------------------------------------------
# OpenAI helpers — isolated so tests can stub them
# ---------------------------------------------------------------------------

def _chat_completion(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.3,
    max_tokens: int = 800,
) -> str:
    """Wrapper around the project-wide OpenAI client.

    Reuses the singleton ``ai_assistant.client`` (configured once at
    module import time with `AI_INTEGRATIONS_OPENAI_API_KEY` and
    optional base URL) instead of instantiating a second client.

    Lives in this module — not in ``ai_assistant`` itself — so the
    predict-guided tests can monkey-patch ``svc._chat_completion``
    without touching the rest of the chat stack. Returns "" when no
    API key is configured so the wizard degrades to default questions
    and a deterministic narrative.
    """
    try:
        # Imported lazily so importing this service in tests doesn't
        # trigger an unconfigured-OpenAI failure during collection.
        from ai_assistant import (  # type: ignore
            client,
            AI_INTEGRATIONS_OPENAI_API_KEY,
        )
    except Exception as exc:  # pragma: no cover - import-time failure
        log.warning("ai_assistant client unavailable: %s", exc)
        return ""
    if not AI_INTEGRATIONS_OPENAI_API_KEY:
        return ""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:  # pragma: no cover - network-dependent
        log.warning("guided predict LLM call failed: %s", exc)
        return ""


def build_dataset_profile(df: pd.DataFrame) -> dict[str, Any]:
    """Build a rich profile of the dataset for GPT-4o analysis.

    For each column: name, dtype, null%, min/max/mean (numeric) or
    top-3 unique values (text). Includes first 5 rows as a sample.
    Hard budget enforced in layers so the serialised profile stays
    inside the ~2000-symbol (≈5000-char) limit set in the task spec:
      1. Column count capped at 30 (priority to target/time hint cols).
      2. sample_rows dropped if still over budget.
      3. top_values shrunk to 1 entry per text column as last resort.
    """
    MAX_CHARS = 5000  # safe ceiling (~1250 tokens — stays inside the 2000-symbol budget)
    MAX_COLS = 30     # cap on number of columns profiled
    TOP_N = 3         # unique-value samples per text column

    # Cap column count — prioritise target-hint and time-hint cols.
    cols = list(df.columns)
    if len(cols) > MAX_COLS:
        priority = sorted(
            cols,
            key=lambda c: (
                -_column_score(c, _TARGET_COLUMN_HINTS)
                - _column_score(c, _TIME_COLUMN_HINTS)
            ),
        )
        cols = priority[:MAX_COLS]

    columns_info: list[dict[str, Any]] = []
    for col in cols:
        col_info: dict[str, Any] = {
            "name": str(col),
            "dtype": str(df[col].dtype),
            "null_pct": round(float(df[col].isna().mean()) * 100, 1),
        }
        if pd.api.types.is_numeric_dtype(df[col]):
            clean = df[col].dropna()
            if len(clean) > 0:
                col_info["min"] = round(float(clean.min()), 4)
                col_info["max"] = round(float(clean.max()), 4)
                col_info["mean"] = round(float(clean.mean()), 4)
        else:
            top_vals = (
                df[col].dropna().astype(str).value_counts().head(TOP_N).index.tolist()
            )
            # Hard-clamp each string value to 40 chars to prevent
            # high-cardinality free-text columns from blowing the budget.
            col_info["top_values"] = [v[:40] for v in top_vals]
        columns_info.append(col_info)

    sample_rows = df.head(5).astype(str).to_dict(orient="records")

    profile: dict[str, Any] = {
        "n_rows": len(df),
        "n_cols": len(df.columns),
        "columns": columns_info,
        "sample_rows": sample_rows,
    }

    # Layer-2 truncation: drop sample_rows.
    if len(json.dumps(profile, ensure_ascii=False)) > MAX_CHARS:
        profile.pop("sample_rows", None)

    # Layer-3 truncation: shrink top_values to 1 entry per column.
    if len(json.dumps(profile, ensure_ascii=False)) > MAX_CHARS:
        for ci in profile["columns"]:
            if "top_values" in ci:
                ci["top_values"] = ci["top_values"][:1]

    # Layer-4 (last resort): truncate column names and string values
    # that are still extremely long after the above passes.
    if len(json.dumps(profile, ensure_ascii=False)) > MAX_CHARS:
        for ci in profile["columns"]:
            ci["name"] = ci["name"][:30]
            if "top_values" in ci:
                ci["top_values"] = [v[:20] for v in ci["top_values"]]

    return profile


def _infer_problem_type(
    df: pd.DataFrame, target: str, time_column: str | None
) -> str:
    """Deterministically infer problem type when GPT-4o is unavailable.

    - ``timeseries`` if a valid time column exists.
    - ``classification`` if the target looks categorical: ≤20 unique
      values and cardinality ratio < 5 % of row count.
    - ``regression`` otherwise.
    """
    if time_column:
        return "timeseries"
    if target not in df.columns:
        return "regression"
    col = df[target].dropna()
    n_unique = int(col.nunique())
    ratio = n_unique / max(len(col), 1)
    if n_unique <= 20 and ratio < 0.05:
        return "classification"
    return "regression"


def _gpt4o_analyze(
    profile: dict[str, Any],
    target: str,
    time_column: str | None,
    drivers: list[dict[str, Any]],
) -> dict[str, Any]:
    """Single GPT-4o call: domain inference + questions.

    Returns a dict with keys: ``domain``, ``target_reason``,
    ``problem_type``, and ``questions``.  Returns an empty dict when
    the LLM is unavailable so callers can fall back gracefully.
    """
    summary = {
        "profile": profile,
        "detected_target": target,
        "detected_time_column": time_column,
        "top_drivers": [d["column"] for d in drivers[:5]],
    }
    system = (
        "You are an expert data analyst. Given a dataset profile, you must:\n"
        "1. Infer the business domain (short Arabic phrase, e.g. 'بيانات مبيعات إقليمية').\n"
        "2. Explain in one Arabic sentence why the detected target column was chosen.\n"
        "3. Classify the problem type: 'timeseries' if a time column exists, "
        "'regression' for continuous numeric targets, 'classification' for categorical.\n"
        "4. Generate 3–5 clarifying questions TAILORED to the actual domain "
        "(HR data → turnover/attendance questions, sales data → promotions/seasonality, "
        "manufacturing → production rates/downtime, etc.).\n"
        "5. For each question add a short 'hint' field: one Arabic sentence explaining "
        "what this question controls and how the answer affects the forecast "
        "(e.g. 'يحدد هذا مدى التوقع — كلما قصرت المدة كان التوقع أدق').\n"
        "6. For dropdown and yesno questions add an 'option_hints' object mapping "
        "each option value to a one-line Arabic plain-language description "
        "(e.g. {\"7\": \"أسبوع واحد — دقيق جداً لكن قصير المدى\"}).\n\n"
        "Output ONLY valid JSON — no markdown, no commentary:\n"
        '{"domain":"...","target_reason":"...","problem_type":"timeseries|regression|classification",'
        '"questions":[{"id":"...","text":"...","kind":"slider|yesno|dropdown",'
        '"hint":"...","option_hints":{"option_value":"description"},'
        '"min":0,"max":100,"default":50,"unit":"%","options":["..."]}]}\n\n'
        "Rules:\n"
        "- domain, target_reason, all question text, hints and option_hints must be in Modern Standard Arabic.\n"
        "- Do NOT ask about raw numeric column values; ask about business context.\n"
        "- Always include a 'horizon_periods' dropdown question "
        "({\"id\":\"horizon_periods\",\"kind\":\"dropdown\",\"options\":[\"7\",\"14\",\"30\",\"60\",\"90\"],\"default\":\"30\"}) "
        "if problem_type is 'timeseries'."
    )
    user_payload = json.dumps(summary, ensure_ascii=False)
    # If the profile is very large, strip sample_rows to stay within token limits.
    if len(user_payload) > 6000:
        light_profile = {k: v for k, v in profile.items() if k != "sample_rows"}
        light_summary = {**summary, "profile": light_profile}
        user_payload = json.dumps(light_summary, ensure_ascii=False)

    raw = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": "Dataset profile (JSON): " + user_payload},
        ],
        temperature=0.2,
        max_tokens=900,
    )
    if not raw:
        return {}

    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
        try:
            obj = json.loads(text[start : end + 1])
        except Exception:
            return {}

    if not isinstance(obj, dict):
        return {}

    result: dict[str, Any] = {
        "domain": str(obj.get("domain") or "").strip(),
        "target_reason": str(obj.get("target_reason") or "").strip(),
        "problem_type": str(obj.get("problem_type") or "regression").strip(),
    }

    # Re-use the existing question parser against the already-parsed object
    # by reconstructing a minimal JSON string for _parse_questions.
    q_raw = json.dumps({"questions": obj.get("questions", [])}, ensure_ascii=False)
    result["questions"] = _parse_questions(q_raw)

    return result


def _parse_questions(raw: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except Exception:
        # Try to rescue the JSON object by finding the first '{' / last '}'.
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            obj = json.loads(text[start : end + 1])
        except Exception:
            return []
    items = obj.get("questions") if isinstance(obj, dict) else None
    if not isinstance(items, list) or not items:
        return []
    out: list[dict[str, Any]] = []
    for i, q in enumerate(items[:5]):
        if not isinstance(q, dict):
            continue
        kind = str(q.get("kind") or "slider").lower()
        if kind not in ("slider", "yesno", "dropdown"):
            kind = "slider"
        entry: dict[str, Any] = {
            "id": str(q.get("id") or f"q{i+1}"),
            "text": str(q.get("text") or "").strip(),
            "kind": kind,
        }
        if not entry["text"]:
            continue
        # Hint and option_hints — use LLM value when present, otherwise inject a
        # deterministic Arabic fallback so the frontend always has something to show.
        _HINT_FALLBACKS: dict[str, str] = {
            "slider": "اضبط القيمة بناءً على معرفتك بالبيانات — يمكنك دائماً تعديل الإجابة لاحقاً.",
            "yesno": "اختر الإجابة الأنسب بناءً على سياق بياناتك.",
            "dropdown": "اختر الخيار الذي يصف بياناتك بشكل أدق.",
        }
        hint = str(q.get("hint") or "").strip()
        entry["hint"] = hint or _HINT_FALLBACKS.get(kind, _HINT_FALLBACKS["slider"])
        raw_oh = q.get("option_hints")
        if isinstance(raw_oh, dict) and raw_oh:
            entry["option_hints"] = {str(k): str(v) for k, v in raw_oh.items()}
        elif kind == "yesno":
            # Ensure yes/no options always have a description
            entry["option_hints"] = {
                "yes": "نعم — ينطبق هذا على بياناتي.",
                "no": "لا — لا ينطبق هذا على بياناتي.",
            }
        if kind == "slider":
            entry["min"] = float(q.get("min", -50))
            entry["max"] = float(q.get("max", 50))
            entry["default"] = float(q.get("default", 0))
            entry["unit"] = str(q.get("unit") or "%")
        elif kind == "dropdown":
            opts = q.get("options") or []
            entry["options"] = [str(o) for o in opts if str(o).strip()]
            if not entry["options"]:
                continue
            entry["default"] = entry["options"][0]
        else:  # yesno
            entry["default"] = "no"
        out.append(entry)
    return out


def _default_questions(
    target: str,
    time_column: str | None,
    problem_type: str = "regression",
) -> list[dict[str, Any]]:
    """Branched deterministic Arabic question set used when the LLM is offline.

    Branches by ``problem_type`` so HR data doesn't get sales questions
    and manufacturing data doesn't get seasonality questions.
    """
    if problem_type == "timeseries" or time_column:
        return _default_questions_timeseries(target, time_column)
    if problem_type == "classification":
        return _default_questions_classification(target)
    return _default_questions_regression(target)


def _default_questions_timeseries(
    target: str, time_column: str | None
) -> list[dict[str, Any]]:
    """Fallback questions for time-series problems."""
    return [
        {
            "id": "horizon_periods",
            "text": "كم فترة مستقبلية ترغب بتوقعها؟",
            "kind": "dropdown",
            "options": ["7", "14", "30", "60", "90"],
            "default": "30",
            "hint": "يحدد هذا مدى التوقع الزمني — كلما قصرت المدة كان التوقع أدق وأكثر موثوقية.",
            "option_hints": {
                "7": "أسبوع — دقيق جداً ومناسب للتخطيط قصير الأمد",
                "14": "أسبوعان — توازن جيد بين الدقة وطول الأفق",
                "30": "شهر — خيار متوازن وشائع للتوقعات الشهرية",
                "60": "شهران — نظرة أبعد مع قدر من الغموض",
                "90": "ثلاثة أشهر — تخطيط ربع سنوي، الدقة أقل نسبياً",
            },
        },
        {
            "id": "season_effect",
            "text": f"ما مستوى التأثير الموسمي المتوقع على {target}؟",
            "kind": "dropdown",
            "options": ["منخفض", "متوسط", "مرتفع"],
            "default": "متوسط",
            "hint": "يساعدنا هذا على ضبط قوة النمط الموسمي في النموذج — إذا كانت بياناتك تتأثر بالمواسم كثيراً اختر 'مرتفع'.",
            "option_hints": {
                "منخفض": "البيانات مستقرة نسبياً ولا تتأثر كثيراً بالمواسم",
                "متوسط": "يوجد تأثير موسمي ملحوظ لكنه ليس مهيمناً",
                "مرتفع": "البيانات تتأثر بشكل واضح بالمواسم أو الأحداث الدورية",
            },
        },
        {
            "id": "trend_change",
            "text": f"هل تتوقع تغيراً في اتجاه {target} خلال الفترة القادمة؟",
            "kind": "yesno",
            "default": "no",
            "hint": "إذا كنت تعلم بوجود تغيير مخطط (كحملة تسويقية أو تغيير في السياسة)، حدد 'نعم' ليأخذ النموذج ذلك بالاعتبار.",
            "option_hints": {
                "yes": "نعم — أتوقع تغيراً ملحوظاً في الاتجاه",
                "no": "لا — سيستمر الوضع على ما هو عليه",
            },
        },
        {
            "id": "external_shock",
            "text": "هل ثمة أحداث خارجية متوقعة (حملات، إجازات، أزمات) قد تؤثر على التوقع؟",
            "kind": "yesno",
            "default": "no",
            "hint": "الأحداث الخارجية كالإجازات والحملات التسويقية تؤثر على الأرقام؛ تحديدها يجعل التوقع أكثر دقة.",
            "option_hints": {
                "yes": "نعم — هناك أحداث أو عوامل خارجية متوقعة",
                "no": "لا — لا توجد أحداث استثنائية متوقعة",
            },
        },
    ]


def _default_questions_regression(target: str) -> list[dict[str, Any]]:
    """Fallback questions for regression problems."""
    return [
        {
            "id": "expected_change",
            "text": f"ما النسبة المتوقعة للتغير في {target} مقارنةً بالفترة السابقة؟",
            "kind": "slider",
            "min": -50.0,
            "max": 50.0,
            "default": 0.0,
            "unit": "%",
            "hint": "تساعدنا هذه الإجابة على ضبط نقطة البداية للتوقع — صفر يعني أنك لا تتوقع تغييراً كبيراً.",
        },
        {
            "id": "key_driver_change",
            "text": "هل ستطرأ تغييرات على العوامل الرئيسية المؤثرة في النتيجة؟",
            "kind": "yesno",
            "default": "no",
            "hint": "إذا كان هناك تغيير متوقع في المتغيرات المؤثرة (كالأسعار أو الكميات)، فإن التوقع سيأخذ ذلك بعين الاعتبار.",
            "option_hints": {
                "yes": "نعم — أتوقع تغييراً في العوامل المؤثرة الرئيسية",
                "no": "لا — ستبقى العوامل المؤثرة مستقرة كما هي",
            },
        },
        {
            "id": "confidence_level",
            "text": "ما مستوى الدقة المطلوب في التوقع؟",
            "kind": "dropdown",
            "options": ["تقديري (سريع)", "متوازن", "عالي الدقة"],
            "default": "متوازن",
            "hint": "يتحكم هذا في عمق التحليل الإحصائي — الدقة العالية تستغرق وقتاً أطول لكنها أكثر موثوقية.",
            "option_hints": {
                "تقديري (سريع)": "سريع — تقدير أولي خلال ثوانٍ، مناسب للاستكشاف السريع",
                "متوازن": "متوازن — يجمع بين السرعة والدقة، الخيار الأمثل لمعظم الحالات",
                "عالي الدقة": "دقيق — تحليل معمّق يستغرق وقتاً أطول لكنه أكثر موثوقية",
            },
        },
    ]


def _default_questions_classification(target: str) -> list[dict[str, Any]]:
    """Fallback questions for classification problems."""
    return [
        {
            "id": "class_balance",
            "text": f"هل توزيع الفئات في {target} متوازن أم يوجد فئات نادرة؟",
            "kind": "dropdown",
            "options": ["متوازن", "غير متوازن", "لا أعرف"],
            "default": "لا أعرف",
            "hint": "توزيع الفئات يؤثر على طريقة تدريب النموذج — إذا كانت إحدى الفئات نادرة جداً فالنموذج يحتاج معالجة خاصة.",
            "option_hints": {
                "متوازن": "الفئات موزعة بشكل متساوٍ تقريباً في البيانات",
                "غير متوازن": "إحدى الفئات أكثر بكثير من الأخرى (كالاحتيال أو الأعطال)",
                "لا أعرف": "غير متأكد — النموذج سيكتشف ذلك تلقائياً",
            },
        },
        {
            "id": "threshold_priority",
            "text": "ما الأهم بالنسبة لك: تجنب الإيجابيات الخاطئة أم السلبيات الخاطئة؟",
            "kind": "dropdown",
            "options": ["تجنب الإيجابيات الخاطئة", "تجنب السلبيات الخاطئة", "متوازن"],
            "default": "متوازن",
            "hint": "يحدد هذا أولوية النموذج: هل تفضّل الحذر (عدم الإنذار الكاذب) أم الشمولية (عدم تفويت أي حالة)؟",
            "option_hints": {
                "تجنب الإيجابيات الخاطئة": "الأهم ألا ينبّه النموذج كاذباً — مناسب عندما تكلفة الإجراء عالية",
                "تجنب السلبيات الخاطئة": "الأهم ألا يفوّت النموذج أي حالة — مناسب عند خطورة عدم الاكتشاف",
                "متوازن": "توازن بين النوعين، مناسب لمعظم الحالات",
            },
        },
        {
            "id": "key_factor",
            "text": "هل هناك عامل تعتقد أنه الأكثر تأثيراً في تحديد الفئة؟",
            "kind": "yesno",
            "default": "no",
            "hint": "إذا كانت لديك معرفة مسبقة بالعامل الحاسم، يمكن للنموذج إعطاؤه وزناً أكبر.",
            "option_hints": {
                "yes": "نعم — أعتقد أن هناك عاملاً محدداً يؤثر بشكل رئيسي",
                "no": "لا — دع النموذج يكتشف العوامل المؤثرة بنفسه",
            },
        },
    ]


def _arabic_narrative(
    target: str,
    formatted_numbers: dict[str, str],
    drivers_summary: list[dict[str, Any]],
    confidence_band: str,
) -> dict[str, Any]:
    """Wrap the ML numbers in an Arabic narrative.

    The model receives every number as a pre-formatted string and is
    instructed to quote them verbatim. If the LLM is unavailable we
    fall back to a deterministic Arabic template.
    """
    payload = {
        "target": target,
        "numbers": formatted_numbers,
        "top_drivers": [d.get("feature") for d in drivers_summary[:3]],
        "confidence_band": confidence_band,
    }
    system = (
        "You write short Arabic business narratives for forecasts. "
        "Strict rules: 1) Reply in Modern Standard Arabic only. 2) "
        "Quote every numeric value VERBATIM from the provided "
        "'numbers' map — never invent, round, or alter a number. 3) "
        "Output ONLY valid JSON: {\"context\":\"...\",\"conditional\""
        ":\"...\",\"recommendations\":[\"...\",\"...\",\"...\"]}. "
        "'context' is one short paragraph. 'conditional' is one line "
        "in the form 'إذا قمت بـ … ← نتوقع …'. 'recommendations' is a "
        "list of 2 or 3 short Arabic action items."
    )
    user = (
        "Forecast payload (JSON): " + json.dumps(payload, ensure_ascii=False)
    )
    raw = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.3,
        max_tokens=600,
    )
    parsed = _parse_narrative(raw)
    if parsed:
        return parsed
    return _default_narrative(
        target, formatted_numbers, drivers_summary, confidence_band
    )


def _parse_narrative(raw: str) -> dict[str, Any] | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        obj = json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        try:
            obj = json.loads(text[start : end + 1])
        except Exception:
            return None
    if not isinstance(obj, dict):
        return None
    context = str(obj.get("context") or "").strip()
    conditional = str(obj.get("conditional") or "").strip()
    recs_raw = obj.get("recommendations") or []
    recs = [str(r).strip() for r in recs_raw if str(r).strip()]
    if not (context and conditional and recs):
        return None
    return {
        "context": context,
        "conditional": conditional,
        "recommendations": recs[:3],
    }


def _default_narrative(
    target: str,
    formatted_numbers: dict[str, str],
    drivers_summary: list[dict[str, Any]],
    confidence_band: str,
) -> dict[str, Any]:
    next_value = formatted_numbers.get("next_period_forecast") or formatted_numbers.get("baseline")
    avg_value = formatted_numbers.get("forecast_average")
    band_label = {
        "high": "مرتفعة",
        "medium": "متوسطة",
        "low": "منخفضة",
    }.get(confidence_band, "متوسطة")
    top_driver = drivers_summary[0]["feature"] if drivers_summary else None
    pieces = [
        f"بناءً على البيانات المتاحة، التوقع لـ {target} يبقى ضمن ",
        f"نطاق قابل للتفسير، وثقتنا فيه {band_label}.",
    ]
    if avg_value:
        pieces.append(f" متوسط القيم المتوقعة هو {avg_value}.")
    context = "".join(pieces)
    conditional = (
        "إذا قمت بالحفاظ على الظروف الحالية ← "
        f"نتوقع {next_value}."
    )
    recs = [
        "راقب التغيرات الكبرى في المتغيرات الرئيسية أسبوعياً.",
        "اعد تشغيل التنبؤ بعد تحديث البيانات الجديدة.",
    ]
    if top_driver:
        recs.insert(
            0,
            f"ركّز على {top_driver} لأنه العامل الأكثر تأثيراً على {target}.",
        )
    return {
        "context": context,
        "conditional": conditional,
        "recommendations": recs[:3],
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_dataset(df: pd.DataFrame) -> dict[str, Any]:
    """Profile the dataset and prepare the wizard's "Questioning" payload.

    Builds a rich dataset profile and sends it to GPT-4o in a single
    call that returns the inferred domain, reason for the target choice,
    problem type, and data-aware clarifying questions.  Falls back to
    branched deterministic questions when GPT-4o is unavailable.
    """
    if df is None or df.empty:
        return {
            "ok": False,
            "kind": "empty_dataset",
            "message_ar": (
                "البيانات فارغة، لا يمكن إعداد التنبؤ. الرجاء "
                "رفع ملف يحتوي على صفوف فعلية."
            ),
        }
    n_rows = int(len(df))
    if n_rows < MIN_ROWS_REGRESSION:
        return {
            "ok": False,
            "kind": "small_sample",
            "rows_available": n_rows,
            "rows_required": MIN_ROWS_REGRESSION,
            "message_ar": (
                f"عدد الصفوف الحالي {n_rows} غير كافٍ لتشغيل التنبؤ — "
                f"نحتاج إلى {MIN_ROWS_REGRESSION} صفًا على الأقل. "
                "حاول رفع بيانات إضافية أو استخدم لوحة التحليل أولاً."
            ),
        }
    time_column = detect_time_column(df)
    target = detect_target_column(df, exclude=[time_column] if time_column else None)
    if not target:
        return {
            "ok": False,
            "kind": "no_target",
            "message_ar": (
                "لم نتمكن من اقتراح متغير رقمي للتنبؤ به. الرجاء "
                "اختيار عمود رقمي يدويًا والمحاولة مجددًا."
            ),
        }
    drivers = rank_drivers(df, target, time_column)

    # Build a rich profile and call GPT-4o once for domain + questions.
    profile = build_dataset_profile(df)
    gpt_result = _gpt4o_analyze(profile, target, time_column, drivers)

    domain: str = gpt_result.get("domain") or ""
    target_reason: str = gpt_result.get("target_reason") or ""
    _VALID_PROBLEM_TYPES = {"timeseries", "regression", "classification"}
    _raw_problem_type = str(gpt_result.get("problem_type") or "").strip().lower()
    problem_type: str = (
        _raw_problem_type
        if _raw_problem_type in _VALID_PROBLEM_TYPES
        else _infer_problem_type(df, target, time_column)
    )
    questions: list[dict[str, Any]] = gpt_result.get("questions") or []
    if not questions:
        questions = _default_questions(target, time_column, problem_type)

    # Collect all numeric columns (excluding time column) so the
    # frontend can let the user change the target if needed.
    numeric_columns = [
        c for c in df.columns
        if pd.api.types.is_numeric_dtype(df[c])
        and c != time_column
        and df[c].dropna().size >= 3
    ]

    # Partial / pre-run confidence breakdown — every component except
    # `signal_strength` can be estimated before fitting any model, so
    # the wizard can preview "where confidence will come from" already
    # in the Questioning phase.
    pre_signal = float(drivers[0]["abs_correlation"]) if drivers else 0.4
    columns_for_quality = [target] + (
        [time_column] if time_column else []
    ) + [d["column"] for d in drivers[:5]]
    partial_sub_scores = {
        "data_volume": _data_volume_score(n_rows),
        "data_quality": _data_quality_score(df, columns_for_quality),
        "signal_strength": _bound01(pre_signal),
        "time_coverage": (
            _time_coverage_score(df[time_column])
            if time_column and time_column in df.columns
            else 0.5
        ),
    }
    partial_confidence = compute_confidence(partial_sub_scores)
    partial_confidence["preliminary"] = True

    # Extract date range from time column for the summary card
    date_start: str | None = None
    date_end: str | None = None
    if time_column and time_column in df.columns:
        parsed_times = pd.to_datetime(df[time_column], errors="coerce").dropna()
        if not parsed_times.empty:
            date_start = parsed_times.min().strftime("%Y-%m-%d")
            date_end = parsed_times.max().strftime("%Y-%m-%d")

    return {
        "ok": True,
        "row_count": n_rows,
        "time_column": time_column,
        "target": target,
        "drivers": drivers,
        "questions": questions,
        "partial_confidence": partial_confidence,
        "domain": domain,
        "target_reason": target_reason,
        "problem_type": problem_type,
        "numeric_columns": numeric_columns,
        "date_start": date_start,
        "date_end": date_end,
        "flow": GUIDED_FLOW_TAG,
    }


def run_prediction(
    df: pd.DataFrame,
    target: str,
    time_column: str | None,
    drivers: list[str],
    answers: dict[str, Any],
    periods: int = 30,
) -> dict[str, Any]:
    """Run the appropriate model and assemble the wizard's "Result" payload."""
    if df is None or df.empty:
        raise ValueError("dataset is empty")
    if target not in df.columns:
        raise ValueError(f"target '{target}' not in dataset")
    horizon = int(answers.get("horizon_periods") or periods or 30)
    horizon = max(1, min(horizon, 365))

    drivers_clean = [
        c for c in (drivers or [])
        if c in df.columns and c != target
        and pd.api.types.is_numeric_dtype(df[c])
    ]
    is_timeseries = bool(time_column and time_column in df.columns)

    sub_scores: dict[str, float] = {}
    if is_timeseries:
        model_payload = _fit_prophet(df, time_column, target, periods=horizon)
        forecast_values = [p["yhat"] for p in model_payload["forecast"]]
        baseline_value = (
            float(forecast_values[0]) if forecast_values
            else float(_canonical_num(df[target]).mean())
        )
        forecast_avg = (
            float(np.mean(forecast_values)) if forecast_values else baseline_value
        )
        forecast_low = (
            float(model_payload["forecast"][0].get("lower"))
            if model_payload["forecast"] else baseline_value
        )
        forecast_high = (
            float(model_payload["forecast"][0].get("upper"))
            if model_payload["forecast"] else baseline_value
        )
        formatted_numbers = {
            "next_period_forecast": _fmt_number(baseline_value),
            "forecast_average": _fmt_number(forecast_avg),
            "lower_band": _fmt_number(forecast_low),
            "upper_band": _fmt_number(forecast_high),
            "horizon_periods": str(horizon),
        }
        mape = (model_payload.get("metrics") or {}).get("mape")
        signal = 1.0 - min(float(mape), 1.0) if mape is not None else 0.5
        # A forecast that can't beat a naive random walk must not read as
        # a strong signal, no matter how flattering its in-sample MAPE is.
        if model_payload.get("quality_status") == "FAIL_HIGH_NOISE":
            signal = min(signal, 0.15)
        sub_scores = {
            "data_volume": _data_volume_score(int(len(df))),
            "data_quality": _data_quality_score(df, [target, time_column]),
            "signal_strength": _bound01(signal),
            "time_coverage": _time_coverage_score(df[time_column]),
        }
        feature_importance = []
    else:
        if not drivers_clean:
            ranked = rank_drivers(df, target, time_column, top_k=8)
            drivers_clean = [r["column"] for r in ranked]
        if not drivers_clean:
            raise ValueError("no usable driver columns available")
        use_rf = len(df) >= 80 and len(drivers_clean) >= 3
        model_payload = _fit_driver_model(
            df, target, drivers_clean, use_random_forest=use_rf
        )
        baseline_value = float(model_payload["baseline_prediction"])
        formatted_numbers = {
            "baseline": _fmt_number(baseline_value),
            "r2": _fmt_percent(model_payload["metrics"].get("r2")),
            "mae": _fmt_number(model_payload["metrics"].get("mae")),
        }
        r2 = float(model_payload["metrics"].get("r2") or 0.0)
        sub_scores = {
            "data_volume": _data_volume_score(int(len(df))),
            "data_quality": _data_quality_score(df, [target] + drivers_clean),
            "signal_strength": _bound01(r2),
            "time_coverage": 0.5,
        }
        feature_importance = model_payload.get("feature_importance", [])

    confidence = compute_confidence(sub_scores)
    # Honest ceiling: a forecast that loses to a naive random walk is
    # never high/medium confidence, no matter how strong the other
    # signals (volume, coverage) look. Applied before the narrative so
    # the Arabic copy reflects the downgrade too.
    if model_payload.get("quality_status") == "FAIL_HIGH_NOISE":
        confidence["band"] = "low"
        confidence["score"] = min(confidence["score"], 35.0)
    narrative = _arabic_narrative(
        target, formatted_numbers, feature_importance, confidence["band"]
    )

    return {
        "flow": GUIDED_FLOW_TAG,
        "target": target,
        "time_column": time_column,
        "is_timeseries": is_timeseries,
        "horizon_periods": horizon,
        "answers": answers or {},
        "model": model_payload,
        "feature_importance": feature_importance,
        "formatted_numbers": formatted_numbers,
        "confidence": confidence,
        "narrative": narrative,
        "quality_status": model_payload.get("quality_status"),
        "baseline_warning": model_payload.get("baseline_warning"),
    }
