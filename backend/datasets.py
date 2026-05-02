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
from pydantic import BaseModel

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
    # The list endpoint intentionally returns only the lightweight fields
    # the sidebar/grid needs. Heavier per-dataset payloads (`summary` /
    # `summary_stats`) are still served by GET /api/datasets/{id} when a
    # caller actually needs them, keeping this list response small even
    # for users with dozens of attached datasets.
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


# ---------------------------------------------------------------------------
# Join two datasets — Task #247
# ---------------------------------------------------------------------------

_VALID_JOIN_TYPES = {"inner", "left", "right", "outer"}


class JoinRequest(BaseModel):
    """Body for ``POST /api/datasets/join``.

    The endpoint serves both the live preview (``preview_only=True``)
    and the persist step (``preview_only=False``). Keeping them on the
    same route means the preview rows the UI shows the user are
    *exactly* the rows that will be saved if they hit "Save" — no
    second materialisation pass that could drift.
    """

    left_dataset_id: int
    right_dataset_id: int
    join_key: str
    join_type: str = "inner"
    result_name: str | None = None
    preview_only: bool = True
    # Optional separate keys for the two sides — defaults to ``join_key``
    # on both. Lets a user join e.g. ``customer_id`` on the left to
    # ``id`` on the right without renaming columns first.
    left_key: str | None = None
    right_key: str | None = None


def _join_summary(merged: pd.DataFrame, left: pd.DataFrame, right: pd.DataFrame,
                  left_key: str, right_key: str, join_type: str,
                  collisions: list[str]) -> dict[str, Any]:
    """Per-column null counts + headline counts the UI shows above the
    preview table. Collision warnings are surfaced separately so the
    Expert view can prefix them with the SQL rename guidance."""
    null_counts = {str(c): int(merged[c].isna().sum()) for c in merged.columns}
    return {
        "join_type": join_type,
        "left_rows": int(len(left)),
        "right_rows": int(len(right)),
        "result_rows": int(len(merged)),
        "result_cols": int(len(merged.columns)),
        "left_key": left_key,
        "right_key": right_key,
        "null_counts": null_counts,
        "collisions": collisions,
    }


@router.post("/join")
async def join_datasets(
    body: JoinRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    join_type = (body.join_type or "inner").lower()
    if join_type not in _VALID_JOIN_TYPES:
        raise HTTPException(
            400,
            f"join_type must be one of {sorted(_VALID_JOIN_TYPES)}",
        )

    left_rec = models.get_dataset_record_strict(
        db, body.left_dataset_id, user_id=user.id,
    )
    right_rec = models.get_dataset_record_strict(
        db, body.right_dataset_id, user_id=user.id,
    )
    if not left_rec or not left_rec.source_parquet:
        raise HTTPException(404, "Left dataset not found")
    if not right_rec or not right_rec.source_parquet:
        raise HTTPException(404, "Right dataset not found")

    left_df = pd.read_parquet(io.BytesIO(left_rec.source_parquet))
    right_df = pd.read_parquet(io.BytesIO(right_rec.source_parquet))

    left_key = (body.left_key or body.join_key or "").strip()
    right_key = (body.right_key or body.join_key or "").strip()
    if not left_key or not right_key:
        raise HTTPException(400, "join_key is required")
    if left_key not in left_df.columns:
        raise HTTPException(
            400, f"join key '{left_key}' is not a column in the left dataset",
        )
    if right_key not in right_df.columns:
        raise HTTPException(
            400, f"join key '{right_key}' is not a column in the right dataset",
        )

    # Columns (other than the join keys themselves) that exist on both
    # sides — pandas will rename them with our ``_left`` / ``_right``
    # suffixes. We surface the list separately so the UI can warn.
    left_cols = set(left_df.columns) - {left_key}
    right_cols = set(right_df.columns) - {right_key}
    collisions = sorted(left_cols & right_cols)

    try:
        merged = pd.merge(
            left_df, right_df,
            how=join_type,
            left_on=left_key, right_on=right_key,
            suffixes=("_left", "_right"),
        )
    except Exception as e:
        raise HTTPException(400, f"Merge failed: {e}")

    summary = _join_summary(
        merged, left_df, right_df,
        left_key, right_key, join_type, collisions,
    )

    if body.preview_only:
        # Stringify NaN so the JSON encoder doesn't choke on float NaN.
        preview = merged.head(20).where(pd.notnull(merged.head(20)), None)
        return jsonify({
            "preview_only": True,
            "summary": summary,
            "columns": [
                {"name": str(c), "dtype": str(merged[c].dtype)}
                for c in merged.columns
            ],
            "preview_rows": preview.to_dict(orient="records"),
        })

    # Persist as a brand-new dataset under the LEFT dataset's project
    # (per spec — the left side is the "FROM" table conceptually).
    name = (body.result_name or "").strip()
    if not name:
        left_label = left_rec.dataset_name or left_rec.filename or "left"
        right_label = right_rec.dataset_name or right_rec.filename or "right"
        name = f"{left_label} ⋈ {right_label}"

    parquet_buf = io.BytesIO()
    merged.to_parquet(parquet_buf, index=False)
    parquet_bytes = parquet_buf.getvalue()
    data_hash = hashlib.sha256(parquet_bytes).hexdigest()
    now = datetime.utcnow()
    df_summary = _df_summary(merged)
    record = models.save_dataset_record(
        db,
        filename=f"{name}.parquet",
        dataset_name=name,
        period_month=now.month,
        period_year=now.year,
        row_count=df_summary["rows"],
        column_count=df_summary["cols"],
        columns_info=_columns_info(merged),
        data_hash=data_hash,
        summary_stats=jsonify(df_summary["report"]),
        user_id=user.id,
        source_parquet=parquet_bytes,
        project_id=left_rec.project_id,
    )
    return jsonify({
        "preview_only": False,
        "summary": summary,
        "dataset_id": record.id,
        "dataset_name": record.dataset_name,
        "project_id": record.project_id,
        "rows": record.row_count,
        "cols": record.column_count,
    })
