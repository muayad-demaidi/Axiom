"""Analysis routes — clean / transform / statistics / predict / model.

Each handler loads the persisted DataFrame from PostgreSQL (via parquet
bytes), invokes the existing module function, and returns a JSON-friendly
view that the Next.js frontend renders directly.
"""
from __future__ import annotations

import io
import json
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import models  # type: ignore
from data_cleaner import clean_data  # type: ignore
from data_analyzer import generate_summary_report  # type: ignore
from predictions import simple_forecast  # type: ignore

from context.type_inference import to_numeric_canonical as _canonical_num  # type: ignore

from . import aggregation as agg
from ._json import jsonify
from .auth import get_current_user, get_db_session
from .datasets import load_dataset_dataframe

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


@router.post("/predict")
async def predict(req: PredictRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    _, df = _require_dataset(db, req.dataset_id, user.id)
    if req.column not in df.columns:
        raise HTTPException(400, f"Column '{req.column}' not in dataset")
    series = _canonical_num(df[req.column]).dropna().tolist()
    if len(series) < 3:
        raise HTTPException(400, "Need at least 3 numeric points to forecast")
    return jsonify({"column": req.column, "forecast": simple_forecast(series, periods=req.periods)})


class ModelRequest(BaseModel):
    dataset_id: int
    method: str = "kmeans"  # kmeans | randomforest
    k: int = 3
    target: str | None = None


@router.post("/model")
async def model(req: ModelRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    """Lightweight ML wrapper.

    Calls into sklearn directly for KMeans and RandomForest because the
    legacy `data_modelling.py` is tightly coupled to Streamlit session
    state. We will swap to module-level functions there once they are
    refactored to be UI-agnostic.
    """
    _, df = _require_dataset(db, req.dataset_id, user.id)
    numeric = df.select_dtypes(include="number").dropna()
    if numeric.empty:
        raise HTTPException(400, "No numeric columns to model")

    if req.method == "kmeans":
        from sklearn.cluster import KMeans
        k = max(2, min(req.k, len(numeric) - 1, 10))
        labels = KMeans(n_clusters=k, n_init=10, random_state=42).fit_predict(numeric)
        sizes: dict[int, int] = {}
        for label in labels:
            sizes[int(label)] = sizes.get(int(label), 0) + 1
        return jsonify({"method": "kmeans", "k": k, "cluster_sizes": sizes})

    if req.method == "randomforest":
        from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
        if not req.target or req.target not in df.columns:
            raise HTTPException(400, "target column required for randomforest")
        y = df[req.target]
        x = numeric.drop(columns=[req.target], errors="ignore")
        if x.empty:
            raise HTTPException(400, "Need at least one numeric feature column besides the target")
        rf = (RandomForestRegressor if pd.api.types.is_numeric_dtype(y) else RandomForestClassifier)(
            n_estimators=100, random_state=42
        )
        rf.fit(x, y.loc[x.index])
        importance = sorted(
            ({"feature": f, "importance": float(i)} for f, i in zip(x.columns, rf.feature_importances_)),
            key=lambda r: r["importance"],
            reverse=True,
        )
        return jsonify({"method": "randomforest", "target": req.target, "feature_importance": importance[:25]})

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
    import numpy as np

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
