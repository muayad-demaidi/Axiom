"""Analysis routes — clean / transform / statistics / predict / model.

Each handler loads the persisted DataFrame from PostgreSQL (via parquet
bytes), invokes the existing module function, and returns a JSON-friendly
view that the Next.js frontend renders directly.
"""
from __future__ import annotations

import io
import json
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import models  # type: ignore
from data_cleaner import clean_data  # type: ignore
from data_analyzer import generate_summary_report  # type: ignore
from predictions import simple_forecast  # type: ignore

from context.type_inference import to_numeric_canonical as _canonical_num  # type: ignore

from . import aggregation as agg
from . import predictions_engine as pe
from ._json import jsonify
from .auth import get_current_user, get_db_session
from .datasets import load_dataset_dataframe
from .mode_resolver import resolve_mode

router = APIRouter(prefix="/api", tags=["analysis"])


def _require_dataset(db, dataset_id: int, user_id: int):
    record = models.get_dataset_record(db, dataset_id, user_id=user_id)
    if not record:
        raise HTTPException(404, "Dataset not found")
    df = load_dataset_dataframe(record)
    return record, df


class CleanRequest(BaseModel):
    dataset_id: int
    enabled: dict[str, bool] | None = None
    params: dict[str, dict] | None = None


@router.post("/clean")
async def clean(req: CleanRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    _, df = _require_dataset(db, req.dataset_id, user.id)
    cleaned, report = clean_data(df, enabled=req.enabled, params=req.params)
    return jsonify({
        "rows_before": int(len(df)),
        "rows_after": int(len(cleaned)),
        "report": report,
        "preview": cleaned.head(20).to_dict(orient="records"),
        "columns": [{"name": c, "dtype": str(cleaned[c].dtype)} for c in cleaned.columns],
    })


class TransformStep(BaseModel):
    op: str  # "rename", "drop", "filter", "fillna", "uppercase", "lowercase"
    column: str | None = None
    target: str | None = None
    value: Any | None = None


class TransformRequest(BaseModel):
    dataset_id: int
    steps: list[TransformStep] = []


@router.post("/transform")
async def transform(req: TransformRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    """Apply a small but real set of Power Query–style transforms.

    The full transforms.py palette is broader; this endpoint covers the
    common operations the frontend exposes today and serves as the bridge
    we'll widen as additional UI affordances ship.
    """
    _, df = _require_dataset(db, req.dataset_id, user.id)
    applied: list[dict] = []
    for step in req.steps:
        op = step.op
        col = step.column
        try:
            if op == "rename" and col and step.target:
                df = df.rename(columns={col: step.target})
            elif op == "drop" and col:
                df = df.drop(columns=[col], errors="ignore")
            elif op == "fillna" and col:
                df[col] = df[col].fillna(step.value)
            elif op == "uppercase" and col:
                df[col] = df[col].astype(str).str.upper()
            elif op == "lowercase" and col:
                df[col] = df[col].astype(str).str.lower()
            elif op == "filter" and col:
                df = df[df[col] == step.value]
            else:
                applied.append({"op": op, "column": col, "status": "skipped"})
                continue
            applied.append({"op": op, "column": col, "status": "applied"})
        except Exception as e:
            applied.append({"op": op, "column": col, "status": f"error: {e}"})
    return jsonify({
        "applied": applied,
        "rows": int(len(df)),
        "preview": df.head(20).to_dict(orient="records"),
        "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
    })


class DatasetIdRequest(BaseModel):
    dataset_id: int


@router.post("/statistics")
async def statistics(req: DatasetIdRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    _, df = _require_dataset(db, req.dataset_id, user.id)
    return jsonify({"dataset_id": req.dataset_id, "report": generate_summary_report(df)})


class PredictRequest(BaseModel):
    dataset_id: int
    column: str
    periods: int = 3
    date_column: str | None = None
    assistant_mode: str | None = None
    project_id: int | None = None


@router.post("/predict")
async def predict(req: PredictRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    """Mode-aware predict endpoint (Task #245).

    Returns the documented dual ``{guided, expert}`` payload by routing
    the request through :mod:`backend.predictions_engine`. Existing
    callers that only sent ``{dataset_id, column, periods}`` keep
    working — the extra fields are additive and the legacy
    ``forecast`` block is preserved at the top level for backwards
    compatibility.
    """
    record, df = _require_dataset(db, req.dataset_id, user.id)
    if req.column not in df.columns:
        raise HTTPException(400, f"Column '{req.column}' not in dataset")
    mode = resolve_mode(
        db, user,
        project_id=req.project_id or getattr(record, "project_id", None),
        request_mode=req.assistant_mode,
    )
    try:
        result = pe.run_prediction(
            df,
            target_col=req.column,
            date_col=req.date_column,
            mode=mode,
            periods=int(req.periods),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    # Legacy fields kept so older clients (and the Streamlit shell)
    # continue to render without changes.
    series = _canonical_num(df[req.column]).dropna().tolist()
    legacy_forecast = (
        simple_forecast(series, periods=req.periods) if len(series) >= 3 else None
    )
    return jsonify({
        "column": req.column,
        "mode": mode,
        "guided": result["guided"],
        "expert": result["expert"],
        "forecast": legacy_forecast,
    })


class ModelRequest(BaseModel):
    dataset_id: int
    method: str = "kmeans"  # kmeans | randomforest
    k: int = 3
    target: str | None = None
    assistant_mode: str | None = None
    project_id: int | None = None


@router.post("/model")
async def model(req: ModelRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    """Mode-aware ML wrapper (Task #245).

    Returns the dual ``{guided, expert}`` payload for both clustering
    (KMeans) and supervised modelling (RandomForest). The KMeans
    branch is wrapped locally because clustering does not have a
    natural prediction surface, while RandomForest requests are routed
    through :mod:`backend.predictions_engine` which auto-picks
    classification vs. regression and runs cross-validation +
    confidence intervals.
    """
    record, df = _require_dataset(db, req.dataset_id, user.id)
    numeric = df.select_dtypes(include="number").dropna()
    if numeric.empty:
        raise HTTPException(400, "No numeric columns to model")
    mode = resolve_mode(
        db, user,
        project_id=req.project_id or getattr(record, "project_id", None),
        request_mode=req.assistant_mode,
    )

    if req.method == "kmeans":
        from sklearn.cluster import KMeans
        k = max(2, min(req.k, len(numeric) - 1, 10))
        kmeans = KMeans(n_clusters=k, n_init=10, random_state=42).fit(numeric)
        labels = kmeans.predict(numeric)
        sizes: dict[int, int] = {}
        for label in labels:
            sizes[int(label)] = sizes.get(int(label), 0) + 1
        guided = {
            "summary": f"Found {k} clusters across {int(len(numeric))} rows.",
            "confidence": "n/a",
            "confidence_score": None,
            "recommendations": [
                "Inspect cluster centers to label each segment.",
                "Use the cluster id as a feature in downstream predictions.",
            ],
        }
        expert = {
            "model_used": "KMeans",
            "problem_type": "clustering",
            "k": k,
            "cluster_sizes": sizes,
            "inertia": float(kmeans.inertia_),
            "parameters": {"n_init": 10, "random_state": 42, "n_clusters": k},
            "feature_importance": {},
            "metrics": {"inertia": float(kmeans.inertia_)},
            "cross_validation": {},
            "confidence_interval": {},
        }
        return jsonify({
            "method": "kmeans", "k": k, "cluster_sizes": sizes, "mode": mode,
            "guided": guided, "expert": expert,
        })

    if req.method == "randomforest":
        if not req.target or req.target not in df.columns:
            raise HTTPException(400, "target column required for randomforest")
        try:
            result = pe.run_prediction(
                df, target_col=req.target, date_col=None, mode=mode,
            )
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        return jsonify({
            "method": "randomforest", "target": req.target, "mode": mode,
            "guided": result["guided"], "expert": result["expert"],
        })

    raise HTTPException(400, f"Unknown method '{req.method}'")


class VisualizeRequest(BaseModel):
    dataset_id: int
    chart: str  # "bar" | "line" | "scatter" | "pie" | "histogram" | "box" | "heatmap"
    x: str | None = None
    y: str | None = None
    bins: int = 20
    # Optional explicit override; when omitted the engine uses the
    # field's role-aware default aggregation (e.g. SUM for revenue,
    # AVG for percentages, COUNT for non-numeric).
    aggregation: str | None = None

    model_config = {"protected_namespaces": ()}


def _resolved_field_meta(record, df: pd.DataFrame) -> dict:
    """Inferred + user-overridden field metadata for a dataset."""
    inferred = agg.infer_field_meta(df)
    overrides = (record.summary_stats or {}).get("_axiom_field_meta") or {}
    return agg.merge_field_meta(inferred, overrides if isinstance(overrides, dict) else {})


_MAX_CATEGORIES = 30
_MAX_SCATTER_POINTS = 500
_MAX_LINE_POINTS = 500


@router.post("/visualize")
async def visualize(req: VisualizeRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    """Return aggregated series for the requested chart.

    Aggregations happen server-side so the browser only ships the points it
    needs to render — never the raw dataset. Mirrors the chart palette in
    legacy `visualizations.py` (bar/line/scatter/box/pie/heatmap) plus a
    histogram for numeric distributions.

    Bar / line are routed through the central :mod:`backend.aggregation`
    engine so the chosen aggregation (SUM by default for additive
    measures like revenue, AVG with a warning for percentages, COUNT
    for non-numeric) matches what the pivot table and dashboard show.
    """
    record, df = _require_dataset(db, req.dataset_id, user.id)
    chart = req.chart.lower()
    field_meta = _resolved_field_meta(record, df)

    def _ensure(col: str | None) -> str:
        if not col or col not in df.columns:
            raise HTTPException(400, f"Column '{col}' not in dataset")
        return col

    if chart == "histogram":
        col = _ensure(req.x or req.y)
        series = _canonical_num(df[col]).dropna()
        if series.empty:
            raise HTTPException(400, f"Column '{col}' has no numeric values")
        h, edges = np.histogram(series, bins=max(2, min(req.bins, 50)))
        points = [
            {"bin": f"{edges[i]:.2f}–{edges[i + 1]:.2f}", "count": int(h[i])}
            for i in range(len(h))
        ]
        return jsonify({"chart": "histogram", "x": col, "points": points})

    if chart == "pie":
        col = _ensure(req.x)
        counts = df[col].dropna().astype(str).value_counts().head(_MAX_CATEGORIES)
        if counts.empty:
            raise HTTPException(400, f"Column '{col}' has no values")
        return jsonify({
            "chart": "pie",
            "x": col,
            "points": [{"name": str(k), "value": int(v)} for k, v in counts.items()],
        })

    if chart == "box":
        # Use X if numeric; otherwise fall back to all numeric columns (max 6).
        numeric_cols: list[str]
        if req.x and req.x in df.columns and pd.api.types.is_numeric_dtype(df[req.x]):
            numeric_cols = [req.x]
        else:
            numeric_cols = df.select_dtypes(include="number").columns.tolist()[:6]
        if not numeric_cols:
            raise HTTPException(400, "No numeric columns available for a box plot")
        points = []
        for col in numeric_cols:
            series = _canonical_num(df[col]).dropna()
            if series.empty:
                continue
            q1, median, q3 = (float(series.quantile(q)) for q in (0.25, 0.5, 0.75))
            points.append({
                "column": col,
                "min": float(series.min()),
                "q1": q1,
                "median": median,
                "q3": q3,
                "max": float(series.max()),
                "count": int(series.size),
            })
        if not points:
            raise HTTPException(400, "No numeric values to summarize")
        return jsonify({"chart": "box", "points": points})

    if chart == "heatmap":
        # Route through the canonical numeric view so mixed-locale
        # amount columns (object dtype) are not silently excluded.
        numeric_df = agg.numeric_frame_for_correlation(df)
        # Cap to 12 columns so the matrix stays readable in the UI.
        if numeric_df.shape[1] > 12:
            numeric_df = numeric_df.iloc[:, :12]
        if numeric_df.shape[1] < 2:
            raise HTTPException(400, "Need at least two numeric columns for a heatmap")
        corr = numeric_df.corr(numeric_only=True).fillna(0.0)
        cols = [str(c) for c in corr.columns]
        matrix = [[float(v) for v in row] for row in corr.values.tolist()]
        return jsonify({"chart": "heatmap", "columns": cols, "matrix": matrix})

    # Bar / line / scatter all need both axes.
    x = _ensure(req.x)
    y = _ensure(req.y)
    # Use the column series directly (df[[x,y]] would collide if x == y).
    x_series = df[x]
    y_series = df[y]
    pair = pd.DataFrame({"x": x_series.values, "y": y_series.values}).dropna()

    if chart == "scatter":
        pair_x = _canonical_num(pair["x"])
        pair_y = _canonical_num(pair["y"])
        sub = pd.DataFrame({"x": pair_x, "y": pair_y}).dropna()
        if sub.empty:
            raise HTTPException(400, f"Scatter needs numeric values in both '{x}' and '{y}'")
        if len(sub) > _MAX_SCATTER_POINTS:
            sub = sub.sample(_MAX_SCATTER_POINTS, random_state=42)
        points = [{"x": float(rx), "y": float(ry)} for rx, ry in sub.itertuples(index=False, name=None)]
        return jsonify({"chart": "scatter", "x": x, "y": y, "points": points})

    if chart in ("bar", "line"):
        if pair.empty:
            raise HTTPException(400, "No rows to plot after dropping nulls")
        y_numeric = _canonical_num(pair["y"])
        # For bar with both axes categorical, fall back to a frequency
        # bar chart of X (no measure metadata to drive a sum).
        if chart == "bar" and not y_numeric.notna().any():
            counts = pair["x"].astype(str).value_counts().head(_MAX_CATEGORIES)
            points = [{"x": str(k), "y": int(v)} for k, v in counts.items()]
            return jsonify({
                "chart": "bar", "x": x, "y": "count",
                "y_label": "Count", "aggregation": "count",
                "points": points,
                "warnings": [],
            })
        if chart == "line" and not y_numeric.notna().any():
            raise HTTPException(400, f"Line chart needs a numeric Y column ('{y}' is non-numeric)")
        # Pick the aggregation: explicit override → field default → SUM.
        y_meta = field_meta.get(y) or {}
        agg_kind = (req.aggregation or y_meta.get("default_agg") or "sum").lower()
        if agg_kind not in agg.AGGREGATIONS or agg_kind == "none":
            agg_kind = "sum"
        # For line charts, bucket the X axis by the natural date grain
        # if the column is datetime-like; for bar, we group on the raw X.
        date_grains: dict[str, str] = {}
        if chart == "line":
            x_meta = field_meta.get(x) or {}
            if x_meta.get("role") == "date" or x_meta.get("format_kind") == "date":
                date_grains[x] = "month"
        # Pre-flight validation routes through the same engine as the
        # pivot, dashboard and chat make_chart so every BI surface
        # emits the same warnings.
        pre = agg.validate_request(
            [x], [],
            [{"column": y, "aggregation": agg_kind}],
            field_meta, df.columns,
        )
        result = agg.aggregate(
            df,
            rows=[x],
            cols=[],
            measures=[{"column": y, "aggregation": agg_kind}],
            date_grains=date_grains,
            field_meta=field_meta,
            include_subtotals=False,
        )
        max_points = _MAX_CATEGORIES if chart == "bar" else _MAX_LINE_POINTS
        rows_out = result["rows"][:max_points]
        points = [
            {"x": r["_dims"].get(x), "y": r.get("m0")} for r in rows_out
            if r.get("m0") is not None
        ]
        m0 = (result["measures"][0] if result["measures"] else {})
        warnings = list(dict.fromkeys((pre or []) + (result.get("warnings") or [])))
        return jsonify({
            "chart": chart,
            "x": x,
            "y": y,
            "y_label": m0.get("label") or y,
            "aggregation": agg_kind,
            "format_kind": m0.get("format_kind"),
            "points": points,
            "warnings": warnings,
            "grand_total": result.get("grand_total", {}).get("m0"),
        })

    raise HTTPException(400, f"Unknown chart type '{req.chart}'")


# ---------------------------------------------------------------------------
# Expert mode — Task #250 (statistical tests + expert charts)
# ---------------------------------------------------------------------------

class StatisticalTestRequest(BaseModel):
    dataset_id: int
    test: str  # "t_test" | "anova" | "chi_square" | "adf"
    columns: list[str] = []
    groups: list[str] | None = None
    alpha: float = 0.05
    assistant_mode: str | None = None
    project_id: int | None = None


def _verdict(p_value: float, alpha: float) -> str:
    return "reject H0" if (p_value is not None and p_value < alpha) else "fail to reject H0"


def _numeric_clean(series: pd.Series) -> pd.Series:
    return _canonical_num(series).dropna()


@router.post("/analysis/statistical-tests")
async def statistical_tests(
    req: StatisticalTestRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Run a classical statistical test on a stored dataset (Task #250).

    Returns a numeric block (test statistic, p-value, etc.) plus a
    ``plain_language`` line so the Guided UI can surface the verdict
    without rendering the raw numbers. ``mode`` is included in the
    payload — the response shape itself is invariant across modes.
    """
    from scipy import stats as _sp_stats

    record, df = _require_dataset(db, req.dataset_id, user.id)
    mode = resolve_mode(
        db, user,
        project_id=req.project_id or getattr(record, "project_id", None),
        request_mode=req.assistant_mode,
    )
    test = (req.test or "").strip().lower()
    alpha = float(req.alpha) if req.alpha is not None else 0.05
    if alpha <= 0 or alpha >= 1:
        raise HTTPException(400, "alpha must be in (0, 1)")
    cols = list(req.columns or [])

    def _need(n: int) -> None:
        if len(cols) < n:
            raise HTTPException(
                400, f"{test} requires at least {n} column(s) in 'columns'",
            )
        for c in cols[:n]:
            if c not in df.columns:
                raise HTTPException(400, f"Column '{c}' not in dataset")

    if test == "t_test":
        # Two-sample independent t-test. Two ways to call:
        # 1) two numeric columns directly (cols[0] vs cols[1])
        # 2) one numeric column split by ``groups`` (categorical labels)
        _need(1)
        if req.groups and len(req.groups) >= 2 and len(cols) >= 2:
            # Split numeric column cols[0] by category column cols[1].
            num_col, cat_col = cols[0], cols[1]
            if cat_col not in df.columns:
                raise HTTPException(400, f"Column '{cat_col}' not in dataset")
            cat_series = df[cat_col].astype(str)
            a = _numeric_clean(df.loc[cat_series == req.groups[0], num_col])
            b = _numeric_clean(df.loc[cat_series == req.groups[1], num_col])
            label_a, label_b = req.groups[0], req.groups[1]
        else:
            _need(2)
            a = _numeric_clean(df[cols[0]])
            b = _numeric_clean(df[cols[1]])
            label_a, label_b = cols[0], cols[1]
        if len(a) < 2 or len(b) < 2:
            raise HTTPException(400, "t_test needs at least 2 values per group")
        result = _sp_stats.ttest_ind(a, b, equal_var=False)
        t_stat = float(result.statistic)
        p_value = float(result.pvalue)
        df_param = float(getattr(result, "df", len(a) + len(b) - 2))
        mean_a, mean_b = float(a.mean()), float(b.mean())
        verdict = _verdict(p_value, alpha)
        plain = (
            f"Independent t-test of {label_a} vs {label_b}: "
            f"t={t_stat:.3f}, p={p_value:.4f} → {verdict} at α={alpha:.2f}."
        )
        payload = {
            "test": "t_test",
            "t_stat": t_stat,
            "p_value": p_value,
            "df": df_param,
            "mean_a": mean_a,
            "mean_b": mean_b,
            "n_a": int(len(a)),
            "n_b": int(len(b)),
            "alpha": alpha,
            "interpretation": verdict,
            "plain_language": plain,
            "mode": mode,
        }
        return jsonify(payload)

    if test == "anova":
        # One-way ANOVA. Two call shapes (mirror t_test):
        # 1) ``columns`` lists 3+ numeric columns directly.
        # 2) ``columns=[numeric, category]`` + ``groups`` of 3+ labels.
        if req.groups and len(req.groups) >= 3 and len(cols) >= 2:
            num_col, cat_col = cols[0], cols[1]
            if num_col not in df.columns or cat_col not in df.columns:
                raise HTTPException(400, "anova columns must exist in dataset")
            cat_series = df[cat_col].astype(str)
            samples: list[pd.Series] = []
            group_means: dict[str, float] = {}
            for label in req.groups:
                vals = _numeric_clean(df.loc[cat_series == label, num_col])
                if len(vals) < 2:
                    raise HTTPException(
                        400, f"anova group '{label}' needs at least 2 values",
                    )
                samples.append(vals)
                group_means[str(label)] = float(vals.mean())
            labels = list(req.groups)
        else:
            if len(cols) < 3:
                raise HTTPException(
                    400, "anova requires at least 3 numeric columns or 3+ groups",
                )
            samples = []
            group_means = {}
            labels = []
            for c in cols:
                if c not in df.columns:
                    raise HTTPException(400, f"Column '{c}' not in dataset")
                vals = _numeric_clean(df[c])
                if len(vals) < 2:
                    raise HTTPException(
                        400, f"anova column '{c}' needs at least 2 values",
                    )
                samples.append(vals)
                group_means[c] = float(vals.mean())
                labels.append(c)
        f_stat_obj = _sp_stats.f_oneway(*samples)
        f_stat = float(f_stat_obj.statistic)
        p_value = float(f_stat_obj.pvalue)
        k = len(samples)
        n_total = int(sum(len(s) for s in samples))
        df_between = float(k - 1)
        df_within = float(n_total - k)
        verdict = _verdict(p_value, alpha)
        plain = (
            f"One-way ANOVA across {k} groups: F={f_stat:.3f}, "
            f"p={p_value:.4f} → {verdict} at α={alpha:.2f}."
        )
        return jsonify({
            "test": "anova",
            "f_stat": f_stat,
            "p_value": p_value,
            "df_between": df_between,
            "df_within": df_within,
            "group_means": group_means,
            "groups": [str(l) for l in labels],
            "alpha": alpha,
            "interpretation": verdict,
            "plain_language": plain,
            "mode": mode,
        })

    if test == "chi_square":
        # Independence test over a contingency table built from two
        # categorical columns.
        _need(2)
        a_col, b_col = cols[0], cols[1]
        contingency = pd.crosstab(df[a_col], df[b_col])
        if contingency.size == 0 or contingency.shape[0] < 2 or contingency.shape[1] < 2:
            raise HTTPException(
                400, "chi_square needs a 2D contingency with at least 2 levels per axis",
            )
        chi2, p_value, dof, expected = _sp_stats.chi2_contingency(contingency.values)
        verdict = _verdict(float(p_value), alpha)
        plain = (
            f"Chi-square independence test of {a_col} vs {b_col}: "
            f"χ²={float(chi2):.3f}, p={float(p_value):.4f} → {verdict} at α={alpha:.2f}."
        )
        return jsonify({
            "test": "chi_square",
            "chi2": float(chi2),
            "p_value": float(p_value),
            "dof": int(dof),
            "expected": [[float(v) for v in row] for row in expected.tolist()],
            "observed": [[int(v) for v in row] for row in contingency.values.tolist()],
            "rows": [str(r) for r in contingency.index.tolist()],
            "cols": [str(c) for c in contingency.columns.tolist()],
            "alpha": alpha,
            "interpretation": verdict,
            "plain_language": plain,
            "mode": mode,
        })

    if test == "adf":
        # Augmented Dickey-Fuller stationarity test.
        try:
            from statsmodels.tsa.stattools import adfuller
        except ImportError:
            raise HTTPException(
                500, "statsmodels is required for the ADF test but is not installed",
            )
        _need(1)
        series = _numeric_clean(df[cols[0]])
        if len(series) < 8:
            raise HTTPException(
                400, "adf needs at least 8 numeric observations",
            )
        adf_stat, p_value, used_lag, n_obs, crit, _icbest = adfuller(series.values)
        verdict_p = _verdict(float(p_value), alpha)
        # ADF null = "non-stationary"; flip the human-readable verdict.
        stationarity = (
            "stationary" if verdict_p == "reject H0" else "non-stationary"
        )
        plain = (
            f"ADF test on {cols[0]}: stat={float(adf_stat):.3f}, "
            f"p={float(p_value):.4f} → series is likely {stationarity} at α={alpha:.2f}."
        )
        return jsonify({
            "test": "adf",
            "adf_stat": float(adf_stat),
            "p_value": float(p_value),
            "lags": int(used_lag),
            "n_obs": int(n_obs),
            "critical_values": {str(k): float(v) for k, v in crit.items()},
            "alpha": alpha,
            "interpretation": verdict_p,
            "stationarity": stationarity,
            "plain_language": plain,
            "mode": mode,
        })

    raise HTTPException(400, f"Unknown statistical test '{req.test}'")


class ExpertChartRequest(BaseModel):
    dataset_id: int
    chart: str  # "residuals" | "qq" | "acf" | "pacf"
    x_col: str | None = None
    y_col: str | None = None
    lags: int | None = None
    assistant_mode: str | None = None
    project_id: int | None = None


def _plotly_spec(fig) -> dict:
    """Render a Plotly figure as a JSON-safe dict spec."""
    return json.loads(fig.to_json())


@router.post("/visualize/expert-charts")
async def expert_charts(
    req: ExpertChartRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Render the four Expert-mode diagnostic charts (Task #250).

    Each chart returns a Plotly JSON spec consumable by the visualize
    page plus a small numerical ``summary`` block (mean residual, top
    autocorrelation lag, normality verdict, etc.).
    """
    import plotly.graph_objects as go
    from scipy import stats as _sp_stats

    record, df = _require_dataset(db, req.dataset_id, user.id)
    mode = resolve_mode(
        db, user,
        project_id=req.project_id or getattr(record, "project_id", None),
        request_mode=req.assistant_mode,
    )
    chart = (req.chart or "").strip().lower()

    def _ensure_col(name: str | None, label: str) -> str:
        if not name or name not in df.columns:
            raise HTTPException(400, f"{label} column required")
        return name

    if chart == "residuals":
        from sklearn.linear_model import LinearRegression

        x_col = _ensure_col(req.x_col, "x_col")
        y_col = _ensure_col(req.y_col, "y_col")
        x_series = _canonical_num(df[x_col])
        y_series = _canonical_num(df[y_col])
        pair = pd.DataFrame({"x": x_series, "y": y_series}).dropna()
        if len(pair) < 3:
            raise HTTPException(
                400, "residuals chart needs at least 3 numeric (x, y) pairs",
            )
        X = pair[["x"]].values
        y = pair["y"].values
        lr = LinearRegression().fit(X, y)
        fitted = lr.predict(X)
        residuals = y - fitted
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=fitted.tolist(), y=residuals.tolist(),
            mode="markers", name="residuals",
        ))
        fig.add_hline(y=0, line_dash="dash", line_color="grey")
        fig.update_layout(
            title=f"Residuals vs fitted ({y_col} ~ {x_col})",
            xaxis_title="Fitted values",
            yaxis_title="Residuals",
        )
        summary = {
            "mean_residual": float(np.mean(residuals)),
            "std_residual": float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0,
            "max_abs_residual": float(np.max(np.abs(residuals))),
            "n": int(len(residuals)),
            "slope": float(lr.coef_[0]),
            "intercept": float(lr.intercept_),
        }
        return jsonify({
            "chart": "residuals",
            "x_col": x_col,
            "y_col": y_col,
            "spec": _plotly_spec(fig),
            "summary": summary,
            "mode": mode,
        })

    if chart == "qq":
        col = _ensure_col(req.x_col or req.y_col, "x_col")
        series = _numeric_clean(df[col])
        if len(series) < 8:
            raise HTTPException(
                400, "qq chart needs at least 8 numeric values",
            )
        (osm, osr), (slope, intercept, r) = _sp_stats.probplot(
            series.values, dist="norm",
        )
        line = [slope * float(np.min(osm)) + intercept,
                slope * float(np.max(osm)) + intercept]
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=osm.tolist(), y=osr.tolist(),
            mode="markers", name="sample quantiles",
        ))
        fig.add_trace(go.Scatter(
            x=[float(np.min(osm)), float(np.max(osm))],
            y=line, mode="lines", name="reference",
            line={"dash": "dash", "color": "grey"},
        ))
        fig.update_layout(
            title=f"Normal Q-Q plot ({col})",
            xaxis_title="Theoretical quantiles",
            yaxis_title="Sample quantiles",
        )
        # Shapiro-Wilk normality verdict (only when n is in scipy range).
        normal_verdict = "unknown"
        sw_p = None
        if 3 <= len(series) <= 5000:
            sw = _sp_stats.shapiro(series.values)
            sw_p = float(sw.pvalue)
            normal_verdict = (
                "looks normal" if sw_p >= 0.05 else "deviates from normal"
            )
        return jsonify({
            "chart": "qq",
            "column": col,
            "spec": _plotly_spec(fig),
            "summary": {
                "n": int(len(series)),
                "slope": float(slope),
                "intercept": float(intercept),
                "r_squared": float(r) ** 2,
                "shapiro_p": sw_p,
                "normality": normal_verdict,
            },
            "mode": mode,
        })

    if chart in ("acf", "pacf"):
        try:
            from statsmodels.tsa.stattools import acf, pacf
        except ImportError:
            raise HTTPException(
                500, "statsmodels is required for ACF / PACF charts",
            )
        col = _ensure_col(req.x_col or req.y_col, "x_col")
        series = _numeric_clean(df[col])
        if len(series) < 8:
            raise HTTPException(
                400, f"{chart} needs at least 8 numeric observations",
            )
        # Cap lags to ~half the series length so PACF stays well-defined.
        default_lags = 20
        max_lags = max(1, min(default_lags, len(series) // 2))
        n_lags = int(req.lags) if req.lags else max_lags
        n_lags = max(1, min(n_lags, len(series) // 2))
        if chart == "acf":
            values = acf(series.values, nlags=n_lags, fft=False)
            label = "Autocorrelation"
        else:
            values = pacf(series.values, nlags=n_lags)
            label = "Partial autocorrelation"
        lag_idx = list(range(len(values)))
        fig = go.Figure()
        fig.add_trace(go.Bar(x=lag_idx, y=[float(v) for v in values], name=label))
        # 95% confidence band (approximate).
        ci = 1.96 / float(np.sqrt(len(series)))
        fig.add_hline(y=ci, line_dash="dot", line_color="grey")
        fig.add_hline(y=-ci, line_dash="dot", line_color="grey")
        fig.update_layout(
            title=f"{label} ({col}, n_lags={n_lags})",
            xaxis_title="Lag",
            yaxis_title=label,
        )
        # Top non-trivial lag (skip lag 0 which is always 1).
        nontrivial = [(i, float(v)) for i, v in enumerate(values) if i > 0]
        nontrivial.sort(key=lambda kv: abs(kv[1]), reverse=True)
        top_lag, top_value = (nontrivial[0] if nontrivial else (0, 0.0))
        return jsonify({
            "chart": chart,
            "column": col,
            "lags": n_lags,
            "values": [float(v) for v in values],
            "ci_band": float(ci),
            "spec": _plotly_spec(fig),
            "summary": {
                "n": int(len(series)),
                "n_lags": int(n_lags),
                "top_lag": int(top_lag),
                "top_value": float(top_value),
            },
            "mode": mode,
        })

    raise HTTPException(400, f"Unknown expert chart '{req.chart}'")
