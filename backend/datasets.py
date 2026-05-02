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
from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile,
)
from pydantic import BaseModel

import models  # type: ignore
from data_analyzer import generate_summary_report  # type: ignore
from data_modelling import _cardinality, suggest_relationships  # type: ignore

from ._json import jsonify
from .auth import get_current_user, get_db_session
from .cross_predict import discover_relationships_after_upload

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

# ---------------------------------------------------------------------------
# Large-join guard — Task #254
# ---------------------------------------------------------------------------
# A join on a non-key column (e.g. country↔country) can fan out from a few
# thousand rows on each side to millions in the merged frame and write a
# huge parquet blob into the database. We refuse to persist such results
# unless the caller explicitly opts in with ``confirm_large_join: true``.
#
# The cap is "exceeded" when *either* of the following is true:
#   * the projected row count is over ``LARGE_JOIN_ABSOLUTE_CAP`` (a hard
#     ceiling regardless of input size), OR
#   * the projection is more than ``LARGE_JOIN_FANOUT_RATIO`` times the
#     larger input AND has at least ``LARGE_JOIN_MIN_ROWS`` rows. The
#     row floor stops tiny developer / test datasets from tripping the
#     guard on what is, in absolute terms, still a small frame.
LARGE_JOIN_ABSOLUTE_CAP = 1_000_000
LARGE_JOIN_FANOUT_RATIO = 5
LARGE_JOIN_MIN_ROWS = 1_000


def _is_large_join(result_rows: int, left_rows: int, right_rows: int) -> bool:
    larger = max(left_rows, right_rows, 1)
    if result_rows > LARGE_JOIN_ABSOLUTE_CAP:
        return True
    if (
        result_rows > LARGE_JOIN_FANOUT_RATIO * larger
        and result_rows > LARGE_JOIN_MIN_ROWS
    ):
        return True
    return False


def _project_join_size(
    left_key: pd.Series, right_key: pd.Series, how: str,
) -> int:
    """Estimate the merged row count *without* actually running
    ``pd.merge``. Used to short-circuit the save path before pandas
    allocates a multi-million-row result frame for a runaway N:N
    join — see Task #254.

    The math mirrors how pandas materialises the merge:

      * Group both sides by the join key and multiply the per-key
        counts on the matched keys (this is the only way an
        N:N can fan out — every key on the left is paired with
        every matching key on the right).
      * For ``left`` / ``right`` / ``outer`` joins, add the rows
        whose key never appears on the other side; pandas keeps each
        of them once with NULLs on the missing side. ``NaN`` keys
        never match across sides (pandas treats ``NaN != NaN`` in
        the merge), so they always fall into the unmatched bucket.

    The number is exact for the row count pandas would produce; we
    intentionally don't try to estimate column count because the
    column count is a function of the input schemas, not the merge.
    """
    lk = left_key.dropna()
    rk = right_key.dropna()
    lvc = lk.value_counts()
    rvc = rk.value_counts()
    common = lvc.index.intersection(rvc.index)
    if len(common) > 0:
        matched = int((lvc.loc[common] * rvc.loc[common]).sum())
        matched_left_rows = int(lvc.loc[common].sum())
        matched_right_rows = int(rvc.loc[common].sum())
    else:
        matched = 0
        matched_left_rows = 0
        matched_right_rows = 0
    unmatched_left = (
        int(len(left_key) - matched_left_rows)
        if how in ("left", "outer")
        else 0
    )
    unmatched_right = (
        int(len(right_key) - matched_right_rows)
        if how in ("right", "outer")
        else 0
    )
    return matched + unmatched_left + unmatched_right


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
    background_tasks: BackgroundTasks,
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
    # Auto-discover cross-dataset relationships in the background as
    # soon as a project gets a second sheet — saves the user from
    # having to open the data-model page and click Refresh just to
    # surface the obvious "customer_id ↔ customer_id" links.
    # The trigger dataset id is forwarded so the post-upload
    # notification can name the file that surfaced the new join.
    if project_id is not None:
        background_tasks.add_task(
            discover_relationships_after_upload,
            project_id, user.id, record.id,
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
    # Footgun guard — see ``_is_large_join``. When the projected merge
    # is unexpectedly huge (e.g. the user accidentally joined on
    # ``country`` instead of an id) the save is refused with a 400
    # unless the caller has seen the warning and re-submitted with
    # ``confirm_large_join: true``.
    confirm_large_join: bool = False


def _join_summary(merged: pd.DataFrame, left: pd.DataFrame, right: pd.DataFrame,
                  left_key: str, right_key: str, join_type: str,
                  collisions: list[str], cardinality: str) -> dict[str, Any]:
    """Per-column null counts + headline counts the UI shows above the
    preview table. Collision warnings are surfaced separately so the
    Expert view can prefix them with the SQL rename guidance.

    ``cardinality`` is the 1:1 / 1:N / N:1 / N:N classification of the
    join keys (computed from ``data_modelling._cardinality``) and
    ``large_join`` flags whether the projected row count tripped the
    fan-out guard — both are surfaced so the UI can warn before save.
    """
    null_counts = {str(c): int(merged[c].isna().sum()) for c in merged.columns}
    left_rows = int(len(left))
    right_rows = int(len(right))
    result_rows = int(len(merged))
    return {
        "join_type": join_type,
        "left_rows": left_rows,
        "right_rows": right_rows,
        "result_rows": result_rows,
        "result_cols": int(len(merged.columns)),
        "left_key": left_key,
        "right_key": right_key,
        "null_counts": null_counts,
        "collisions": collisions,
        "cardinality": cardinality,
        "large_join": _is_large_join(result_rows, left_rows, right_rows),
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

    # ----- Pre-merge fan-out guard (Task #254) ---------------------------
    # Compute the cardinality and project the result row count *before*
    # calling ``pd.merge`` so a runaway N:N join can be refused without
    # ever materialising the huge frame in memory.
    cardinality = _cardinality(left_df[left_key], right_df[right_key])
    left_rows = int(len(left_df))
    right_rows = int(len(right_df))
    projected_rows = _project_join_size(
        left_df[left_key], right_df[right_key], join_type,
    )
    if (
        not body.preview_only
        and _is_large_join(projected_rows, left_rows, right_rows)
        and not body.confirm_large_join
    ):
        raise HTTPException(
            400,
            (
                f"Refusing to save: this {cardinality} join would produce "
                f"~{projected_rows:,} rows from inputs of "
                f"{left_rows:,} × {right_rows:,}. "
                "If this is intentional, re-submit with "
                "`confirm_large_join: true`."
            ),
        )

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
        left_key, right_key, join_type, collisions, cardinality,
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


# ---------------------------------------------------------------------------
# Suggest the strongest join column based on actual values — Task #252
# ---------------------------------------------------------------------------


class JoinSuggestRequest(BaseModel):
    """Body for ``POST /api/datasets/join/suggest``.

    Returns the same ranked list the Data Model screen uses, so the
    Join page can pick the strongest column-pair by *real* value
    overlap (Jaccard) + name similarity + dtype compatibility instead
    of just naming heuristics.
    """

    left_dataset_id: int
    right_dataset_id: int


@router.post("/join/suggest")
async def suggest_join_columns(
    body: JoinSuggestRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Score every (left_col, right_col) pair across the two selected
    datasets and return the ranked candidates.

    The Join page calls this after the user picks two datasets so it
    can pre-select a column pair backed by actual value overlap rather
    than name match alone. A null-overlap candidate is still returned
    (when name + dtype clear the threshold) so the UI can flag it as
    a warning instead of silently auto-accepting it.
    """
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

    suggestions = suggest_relationships(left_df, right_df)
    return jsonify({
        "left_dataset_id": body.left_dataset_id,
        "right_dataset_id": body.right_dataset_id,
        "suggestions": [s.to_dict() for s in suggestions],
    })
