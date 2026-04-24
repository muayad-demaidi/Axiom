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
    chart: str  # "bar" | "line" | "scatter" | "pie" | "histogram"
    x: str | None = None
    y: str | None = None
    bins: int = 20


@router.post("/visualize")
async def visualize(req: VisualizeRequest, user=Depends(get_current_user), db=Depends(get_db_session)):
    """Return aggregated series for the requested chart.

    The endpoint deliberately returns small JSON (capped to 200 points)
    so the browser doesn't have to download the underlying dataset just to
    render a chart.
    """
    _, df = _require_dataset(db, req.dataset_id, user.id)
    chart = req.chart.lower()

    def _ensure(col: str | None) -> str:
        if not col or col not in df.columns:
            raise HTTPException(400, f"Column '{col}' not in dataset")
        return col

    if chart == "histogram":
        import numpy as np
        col = _ensure(req.x or req.y)
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if series.empty:
            raise HTTPException(400, f"Column '{col}' has no numeric values")
        h, edges = np.histogram(series, bins=max(2, min(req.bins, 50)))
        points = [
            {"bin": f"{edges[i]:.2f}–{edges[i+1]:.2f}", "count": int(h[i])}
            for i in range(len(h))
        ]
        return {"chart": "histogram", "x": col, "points": points}

    if chart == "pie":
        col = _ensure(req.x)
        counts = df[col].astype(str).value_counts().head(20)
        return {
            "chart": "pie",
            "x": col,
            "points": [{"name": k, "value": int(v)} for k, v in counts.items()],
        }

    x = _ensure(req.x)
    y = _ensure(req.y)
    sub = df[[x, y]].dropna().head(200)
    points = [{"x": (str(r[x]) if not isinstance(r[x], (int, float)) else r[x]),
               "y": float(r[y]) if pd.api.types.is_numeric_dtype(df[y]) else str(r[y])}
              for _, r in sub.iterrows()]
    return {"chart": chart, "x": x, "y": y, "points": points}
