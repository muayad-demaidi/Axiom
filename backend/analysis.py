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
    return {
        "rows_before": int(len(df)),
        "rows_after": int(len(cleaned)),
        "report": report,
        "preview": cleaned.head(20).to_dict(orient="records"),
        "columns": [{"name": c, "dtype": str(cleaned[c].dtype)} for c in cleaned.columns],
    }


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
    return {
        "applied": applied,
        "rows": int(len(df)),
        "preview": df.head(20).to_dict(orient="records"),
        "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
    }


class DatasetIdRequest(BaseModel):
    dataset_id: int


@router.post("/statistics")
async def statistics(req: DatasetIdRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    _, df = _require_dataset(db, req.dataset_id, user.id)
    return {"dataset_id": req.dataset_id, "report": generate_summary_report(df)}


class PredictRequest(BaseModel):
    dataset_id: int
    column: str
    periods: int = 3


@router.post("/predict")
async def predict(req: PredictRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    _, df = _require_dataset(db, req.dataset_id, user.id)
    if req.column not in df.columns:
        raise HTTPException(400, f"Column '{req.column}' not in dataset")
    series = pd.to_numeric(df[req.column], errors="coerce").dropna().tolist()
    if len(series) < 3:
        raise HTTPException(400, "Need at least 3 numeric points to forecast")
    return {"column": req.column, "forecast": simple_forecast(series, periods=req.periods)}


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
        return {"method": "kmeans", "k": k, "cluster_sizes": sizes}

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
        return {"method": "randomforest", "target": req.target, "feature_importance": importance[:25]}

    raise HTTPException(400, f"Unknown method '{req.method}'")


class VisualizeRequest(BaseModel):
    dataset_id: int
    chart: str  # "bar" | "line" | "scatter" | "pie" | "histogram" | "box" | "heatmap"
    x: str | None = None
    y: str | None = None
    bins: int = 20

    model_config = {"protected_namespaces": ()}


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
    """
    import numpy as np

    _, df = _require_dataset(db, req.dataset_id, user.id)
    chart = req.chart.lower()

    def _ensure(col: str | None) -> str:
        if not col or col not in df.columns:
            raise HTTPException(400, f"Column '{col}' not in dataset")
        return col

    if chart == "histogram":
        col = _ensure(req.x or req.y)
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            raise HTTPException(400, f"Column '{col}' has no numeric values")
        h, edges = np.histogram(series, bins=max(2, min(req.bins, 50)))
        points = [
            {"bin": f"{edges[i]:.2f}–{edges[i + 1]:.2f}", "count": int(h[i])}
            for i in range(len(h))
        ]
        return {"chart": "histogram", "x": col, "points": points}

    if chart == "pie":
        col = _ensure(req.x)
        counts = df[col].dropna().astype(str).value_counts().head(_MAX_CATEGORIES)
        if counts.empty:
            raise HTTPException(400, f"Column '{col}' has no values")
        return {
            "chart": "pie",
            "x": col,
            "points": [{"name": str(k), "value": int(v)} for k, v in counts.items()],
        }

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
            series = pd.to_numeric(df[col], errors="coerce").dropna()
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
        return {"chart": "box", "points": points}

    if chart == "heatmap":
        numeric_df = df.select_dtypes(include="number")
        # Cap to 12 columns so the matrix stays readable in the UI.
        if numeric_df.shape[1] > 12:
            numeric_df = numeric_df.iloc[:, :12]
        if numeric_df.shape[1] < 2:
            raise HTTPException(400, "Need at least two numeric columns for a heatmap")
        corr = numeric_df.corr(numeric_only=True).fillna(0.0)
        cols = [str(c) for c in corr.columns]
        matrix = [[float(v) for v in row] for row in corr.values.tolist()]
        return {"chart": "heatmap", "columns": cols, "matrix": matrix}

    # Bar / line / scatter all need both axes.
    x = _ensure(req.x)
    y = _ensure(req.y)
    # Use the column series directly (df[[x,y]] would collide if x == y).
    x_series = df[x]
    y_series = df[y]
    pair = pd.DataFrame({"x": x_series.values, "y": y_series.values}).dropna()

    if chart == "scatter":
        pair_x = pd.to_numeric(pair["x"], errors="coerce")
        pair_y = pd.to_numeric(pair["y"], errors="coerce")
        sub = pd.DataFrame({"x": pair_x, "y": pair_y}).dropna()
        if sub.empty:
            raise HTTPException(400, f"Scatter needs numeric values in both '{x}' and '{y}'")
        if len(sub) > _MAX_SCATTER_POINTS:
            sub = sub.sample(_MAX_SCATTER_POINTS, random_state=42)
        points = [{"x": float(rx), "y": float(ry)} for rx, ry in sub.itertuples(index=False, name=None)]
        return {"chart": "scatter", "x": x, "y": y, "points": points}

    if chart == "bar":
        if pair.empty:
            raise HTTPException(400, "No rows to plot after dropping nulls")
        y_numeric = pd.to_numeric(pair["y"], errors="coerce")
        if y_numeric.notna().any():
            sub = pair.assign(_y=y_numeric).dropna(subset=["_y"])
            grouped = (
                sub.groupby(sub["x"].astype(str))["_y"].mean()
                .sort_values(ascending=False)
                .head(_MAX_CATEGORIES)
            )
            points = [{"x": str(k), "y": float(v)} for k, v in grouped.items()]
            return {"chart": "bar", "x": x, "y": f"mean({y})", "points": points}
        # Both columns categorical — fall back to a frequency bar chart of X.
        counts = pair["x"].astype(str).value_counts().head(_MAX_CATEGORIES)
        points = [{"x": str(k), "y": int(v)} for k, v in counts.items()]
        return {"chart": "bar", "x": x, "y": "count", "points": points}

    if chart == "line":
        if pair.empty:
            raise HTTPException(400, "No rows to plot after dropping nulls")
        y_numeric = pd.to_numeric(pair["y"], errors="coerce")
        if not y_numeric.notna().any():
            raise HTTPException(400, f"Line chart needs a numeric Y column ('{y}' is non-numeric)")
        sub = pair.assign(_y=y_numeric).dropna(subset=["_y"])
        x_dt = pd.to_datetime(sub["x"], errors="coerce")
        x_num = pd.to_numeric(sub["x"], errors="coerce")
        threshold = max(3, int(0.6 * len(sub)))
        if x_dt.notna().sum() >= threshold:
            ordered = sub.assign(_x=x_dt).dropna(subset=["_x"]).sort_values("_x")
            points = [
                {"x": d.isoformat(), "y": float(v)}
                for d, v in zip(ordered["_x"], ordered["_y"])
            ]
        elif x_num.notna().sum() >= threshold:
            ordered = sub.assign(_x=x_num).dropna(subset=["_x"]).sort_values("_x")
            points = [{"x": float(d), "y": float(v)} for d, v in zip(ordered["_x"], ordered["_y"])]
        else:
            grouped = sub.groupby(sub["x"].astype(str))["_y"].mean()
            points = [{"x": str(k), "y": float(v)} for k, v in grouped.items()]
        if len(points) > _MAX_LINE_POINTS:
            step = max(1, len(points) // _MAX_LINE_POINTS)
            points = points[::step]
        return {"chart": "line", "x": x, "y": y, "points": points}

    raise HTTPException(400, f"Unknown chart type '{req.chart}'")
