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

The two LLM calls are isolated in ``_arabic_questions`` and
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
    target_series = pd.to_numeric(df[target], errors="coerce")
    if target_series.dropna().size < 3:
        return []

    rows: list[dict[str, Any]] = []
    for col in df.columns:
        if col in excluded:
            continue
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue
        x = pd.to_numeric(df[col], errors="coerce")
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
            "y": pd.to_numeric(df[target], errors="coerce"),
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
        return {
            "engine": "prophet",
            "freq": freq,
            "periods": periods,
            "history": history_points,
            "forecast": forecast_points,
            "metrics": {
                "mape": round(mape, 4) if mape is not None else None,
                "n_train": int(len(work)),
            },
        }
    except Exception as exc:
        log.warning(
            "Prophet unavailable (%s) — degrading to linear trend fit",
            exc,
        )
        return _fit_linear_trend(work, periods, freq)


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
    return {
        "engine": "linear_trend",
        "freq": freq,
        "periods": periods,
        "history": history_points,
        "forecast": forecast_points,
        "metrics": {
            "mape": round(mape, 4) if mape is not None else None,
            "n_train": int(len(work)),
        },
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
    work = df[feats + [target]].apply(pd.to_numeric, errors="coerce").dropna()
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


def _arabic_questions(
    target: str,
    time_column: str | None,
    drivers: list[dict[str, Any]],
    n_rows: int,
) -> list[dict[str, Any]]:
    """Ask GPT-4o for 3–5 Arabic clarifying questions for the wizard.

    Falls back to a deterministic Arabic question set when the LLM
    returns nothing parseable, so the wizard always has questions to
    show.
    """
    summary = {
        "target": target,
        "time_column": time_column,
        "drivers": [d["column"] for d in drivers],
        "row_count": n_rows,
    }
    system = (
        "You generate clarifying questions for an Arabic-speaking "
        "business user about to run a forecast on their dataset. "
        "Output ONLY valid JSON of the form "
        "{\"questions\":[{\"id\":\"...\",\"text\":\"...\",\"kind\":"
        "\"slider|yesno|dropdown\",\"options\":[...],\"min\":0,\"max\":"
        "100,\"default\":50}]}. Provide between 3 and 5 questions. All "
        "user-facing text must be in Modern Standard Arabic. Do NOT "
        "ask for raw numeric column values; ask about business "
        "context (e.g. expected promotion lift, planned spend "
        "change, season expectations)."
    )
    user = (
        "Dataset summary (JSON): " + json.dumps(summary, ensure_ascii=False)
    )
    raw = _chat_completion(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=0.2,
        max_tokens=600,
    )
    parsed = _parse_questions(raw)
    if parsed:
        return parsed
    return _default_questions(target, time_column)


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
    target: str, time_column: str | None
) -> list[dict[str, Any]]:
    """Deterministic Arabic question set used when the LLM is offline."""
    questions = [
        {
            "id": "horizon_change",
            "text": (
                "هل تتوقع أن يتغير سلوك "
                f"{target} بشكل كبير خلال الفترة القادمة؟"
            ),
            "kind": "yesno",
            "default": "no",
        },
        {
            "id": "promo_lift",
            "text": (
                "ما النسبة المتوقعة لتأثير العروض أو التغييرات "
                "التشغيلية على النتيجة؟"
            ),
            "kind": "slider",
            "min": -50.0,
            "max": 50.0,
            "default": 0.0,
            "unit": "%",
        },
        {
            "id": "season_effect",
            "text": "ما درجة التأثير الموسمي المتوقع؟",
            "kind": "dropdown",
            "options": ["منخفض", "متوسط", "مرتفع"],
            "default": "متوسط",
        },
    ]
    if time_column:
        questions.append(
            {
                "id": "horizon_periods",
                "text": "كم فترة مستقبلية ترغب بتوقعها؟",
                "kind": "dropdown",
                "options": ["7", "14", "30", "60", "90"],
                "default": "30",
            }
        )
    return questions


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
    """Profile the dataset and prepare the wizard's "Questioning" payload."""
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
    questions = _arabic_questions(target, time_column, drivers, n_rows)

    # Partial / pre-run confidence breakdown — every component except
    # `signal_strength` can be estimated before fitting any model, so
    # the wizard can preview "where confidence will come from" already
    # in the Questioning phase. `signal_strength` is approximated by
    # the strongest absolute correlation with the target (capped at 1).
    pre_signal = (
        float(drivers[0]["abs_correlation"]) if drivers else 0.4
    )
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

    return {
        "ok": True,
        "row_count": n_rows,
        "time_column": time_column,
        "target": target,
        "drivers": drivers,
        "questions": questions,
        "partial_confidence": partial_confidence,
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
            else float(pd.to_numeric(df[target], errors="coerce").mean())
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
    }
