"""Dataset upload + listing routes.

Reuses ``models.save_dataset_record`` / ``get_dataset_record`` so the unified
app and the legacy Streamlit app share the same PostgreSQL rows.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import models  # type: ignore
from data_analyzer import generate_summary_report  # type: ignore

from ._json import jsonify
from .auth import get_current_user, get_db_session

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _read_dataframe(file: UploadFile, raw: bytes) -> pd.DataFrame:
    name = (file.filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return pd.read_excel(io.BytesIO(raw))
    try:
        return pd.read_csv(io.BytesIO(raw))
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(raw), encoding="latin-1")


def _df_summary(df: pd.DataFrame) -> dict[str, Any]:
    try:
        report = generate_summary_report(df)
    except Exception as e:
        report = {"error": f"summary failed: {e}"}
    return {
        "rows": int(len(df)),
        "cols": int(len(df.columns)),
        "columns": [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
        "report": report,
    }


def _columns_info(df: pd.DataFrame) -> dict[str, str]:
    return {str(c): str(df[c].dtype) for c in df.columns}


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    project_id: int | None = Form(None),
    dataset_name: str | None = Form(None),
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    try:
        df = _read_dataframe(file, raw)
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")

    summary = _df_summary(df)
    parquet_buf = io.BytesIO()
    df.to_parquet(parquet_buf, index=False)
    parquet_bytes = parquet_buf.getvalue()
    data_hash = hashlib.sha256(parquet_bytes).hexdigest()
    now = datetime.utcnow()

    record = models.save_dataset_record(
        db,
        filename=file.filename or "upload.csv",
        dataset_name=dataset_name or (file.filename or "Untitled"),
        period_month=now.month,
        period_year=now.year,
        row_count=summary["rows"],
        column_count=summary["cols"],
        columns_info=_columns_info(df),
        data_hash=data_hash,
        summary_stats=jsonify(summary["report"]),
        user_id=user.id,
        source_parquet=parquet_bytes,
        project_id=project_id,
    )
    return jsonify({
        "id": record.id,
        "filename": record.filename,
        "dataset_name": record.dataset_name,
        "rows": record.row_count,
        "cols": record.column_count,
        "summary": summary,
    })


@router.get("")
async def list_datasets(user=Depends(get_current_user), db=Depends(get_db_session)):
    rows = (
        db.query(models.DatasetRecord)
        .filter(models.DatasetRecord.user_id == user.id)
        .order_by(models.DatasetRecord.id.desc())
        .all()
    )
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "dataset_name": r.dataset_name,
            "rows": r.row_count,
            "cols": r.column_count,
            "project_id": r.project_id,
        }
        for r in rows
    ]


@router.get("/{dataset_id}")
async def get_dataset(dataset_id: int, user=Depends(get_current_user), db=Depends(get_db_session)):
    record = models.get_dataset_record(db, dataset_id, user_id=user.id)
    if not record:
        raise HTTPException(404, "Dataset not found")
    return jsonify({
        "id": record.id,
        "filename": record.filename,
        "dataset_name": record.dataset_name,
        "rows": record.row_count,
        "cols": record.column_count,
        "summary": record.summary_stats or {},
        "project_id": record.project_id,
    })


def load_dataset_dataframe(record) -> pd.DataFrame:
    if not record.source_parquet:
        raise HTTPException(410, "Dataset bytes were not retained")
    return pd.read_parquet(io.BytesIO(record.source_parquet))
