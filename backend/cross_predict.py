"""Cross-dataset prediction endpoint (Task #246).

Exposes ``POST /api/projects/{project_id}/cross-predict`` which:

  1. Loads every ``DatasetRecord`` attached to ``project_id`` for the
     requesting user.
  2. Auto-detects join keys using the persisted
     ``ProjectRelationship`` rows that the user has accepted
     (``status == "confirmed"``) plus a fresh pass through
     :func:`semantic_model.propose_relationships_for_project` to pick
     up any new high-confidence pair the user hasn't reviewed yet.
  3. Materialises a single merged feature matrix via
     :func:`data_modelling.materialize_join` — chained left joins
     anchored on the target dataset.
  4. Calls :func:`backend.predictions_engine.run_prediction` on the
     merged frame.
  5. Returns the dual ``{guided, expert}`` payload plus a ``join_plan``
     block describing which datasets were joined on which keys, with
     pre/post row counts.

Background-discovery wiring on upload lives in
:mod:`backend.datasets`.
"""
from __future__ import annotations

import io
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import data_modelling as dm  # type: ignore
import models  # type: ignore
import semantic_model as sm  # type: ignore

from . import predictions_engine as pe
from ._json import jsonify
from .auth import get_current_user, get_db_session
from .mode_resolver import mode_dependency


router = APIRouter(tags=["cross-predict"])


# --------------------------------------------------------------------------
# Request body
# --------------------------------------------------------------------------

class CrossPredictRequest(BaseModel):
    target_dataset_id: int
    target_column: str
    date_column: str | None = None
    horizon: int | None = None
    request_mode: str | None = None


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _project_datasets(db, project_id: int, user_id: int) -> list[Any]:
    return (
        db.query(models.DatasetRecord)
        .filter(
            models.DatasetRecord.project_id == project_id,
            models.DatasetRecord.user_id == user_id,
        )
        .order_by(models.DatasetRecord.id.asc())
        .all()
    )


def _load_frame(record) -> pd.DataFrame | None:
    if not record.source_parquet:
        return None
    try:
        return pd.read_parquet(io.BytesIO(record.source_parquet))
    except Exception:
        return None


def _candidate_relationships(
    db,
    project_id: int,
    name_by_id: dict[int, str],
    id_by_name: dict[str, int],
    frames_by_id: dict[int, pd.DataFrame],
) -> list[dict]:
    """Return a confidence-sorted list of join candidates between
    project datasets.

    Only **user-accepted** persisted ``ProjectRelationship`` rows
    (``status == "confirmed"``) are honoured — joining on links the
    user has not approved would silently change prediction inputs.
    A fresh ``propose_relationships_for_project`` pass is then layered
    on top to surface any **new** high-band pair that hasn't been
    reviewed yet, so unreviewed-but-obvious links still help.
    """
    out: list[dict] = []
    seen: set[tuple[int, str, int, str]] = set()

    persisted = (
        db.query(models.ProjectRelationship)
        .filter(
            models.ProjectRelationship.project_id == project_id,
            models.ProjectRelationship.status == "confirmed",
        )
        .all()
    )
    for r in persisted:
        key = (r.left_dataset_id, r.left_column,
               r.right_dataset_id, r.right_column)
        seen.add(key)
        # User-confirmed → ranked above any auto proposal so chained
        # joins prefer the human-approved key when it competes with a
        # newly proposed one.
        out.append({
            "left_id": r.left_dataset_id,
            "left_col": r.left_column,
            "right_id": r.right_dataset_id,
            "right_col": r.right_column,
            "confidence": float(r.confidence or 0.0) + 1.0,
            "band": "user",
            "source": "confirmed",
        })

    # Also re-score all pairs to catch any newly-uploaded dataset whose
    # high-confidence link wasn't auto-persisted yet (paranoid belt +
    # braces — auto-discovery on upload should already cover this).
    profiles: list[dict] = []
    for did, df in frames_by_id.items():
        try:
            profiles.append(sm.profile_table(name_by_id[did], df))
        except Exception:
            continue
    if len(profiles) >= 2:
        try:
            proposals = sm.propose_relationships_for_project(
                profiles, {p["name"]: frames_by_id[id_by_name[p["name"]]]
                           for p in profiles if p["name"] in id_by_name},
            )
        except Exception:
            proposals = []
        for p in proposals:
            if p.band != "high":
                continue
            ldid = id_by_name.get(p.left_table)
            rdid = id_by_name.get(p.right_table)
            if not ldid or not rdid:
                continue
            key = (ldid, p.left_column, rdid, p.right_column)
            rev_key = (rdid, p.right_column, ldid, p.left_column)
            if key in seen or rev_key in seen:
                continue
            seen.add(key)
            out.append({
                "left_id": ldid, "left_col": p.left_column,
                "right_id": rdid, "right_col": p.right_column,
                "confidence": float(p.confidence),
                "band": p.band, "source": "proposed",
            })

    out.sort(key=lambda r: r["confidence"], reverse=True)
    return out


def _resolve_column(merged: pd.DataFrame, name: str) -> str | None:
    """Return the actual column in ``merged`` for ``name``.

    ``materialize_join`` keeps non-key columns under their original
    name unless both sides had that name, in which case suffixes are
    appended. This helper looks for the bare name first, then any
    suffixed variant — needed when a join key in the running merged
    frame has been renamed by an earlier join.
    """
    if name in merged.columns:
        return name
    # Look for any suffixed variant: ``name_<label>``.
    for col in merged.columns:
        if str(col).startswith(f"{name}_"):
            return str(col)
    return None


def _build_merged(
    target_id: int,
    frames_by_id: dict[int, pd.DataFrame],
    name_by_id: dict[int, str],
    candidates: list[dict],
) -> tuple[pd.DataFrame, list[dict]]:
    """Chain left joins anchored on the target dataset.

    Walks the candidate list in confidence order and joins any
    relationship that connects an already-joined dataset to a still-
    unjoined one. Continues until no more progress is possible — this
    naturally handles multi-hop chains (target → A → B) without an
    explicit graph search.
    """
    target_df = frames_by_id[target_id]
    merged = target_df.copy()
    joined_ids: set[int] = {target_id}
    steps: list[dict] = []

    # Repeat until no further join is applicable.
    while True:
        progress = False
        for rel in candidates:
            l_id, l_col = rel["left_id"], rel["left_col"]
            r_id, r_col = rel["right_id"], rel["right_col"]
            # Decide direction: one side must already be joined, the
            # other must still be unjoined.
            if l_id in joined_ids and r_id not in joined_ids:
                joined_col_raw, new_id, new_col = l_col, r_id, r_col
            elif r_id in joined_ids and l_id not in joined_ids:
                joined_col_raw, new_id, new_col = r_col, l_id, l_col
            else:
                continue

            new_df = frames_by_id.get(new_id)
            if new_df is None or new_df.empty:
                continue
            if new_col not in new_df.columns:
                continue
            actual_left_col = _resolve_column(merged, joined_col_raw)
            if actual_left_col is None:
                continue

            rows_before = int(len(merged))
            try:
                merged = dm.materialize_join(
                    merged, new_df,
                    actual_left_col, new_col,
                    join_type="left",
                    left_label="m",
                    right_label=name_by_id.get(new_id, f"ds_{new_id}"),
                )
            except Exception as e:  # pragma: no cover — defensive
                steps.append({
                    "dataset_id": new_id,
                    "dataset_name": name_by_id.get(new_id),
                    "left_column": actual_left_col,
                    "right_column": new_col,
                    "rows_before": rows_before,
                    "rows_after": rows_before,
                    "error": str(e),
                    "confidence": rel.get("confidence"),
                    "band": rel.get("band"),
                    "source": rel.get("source"),
                })
                continue
            steps.append({
                "dataset_id": new_id,
                "dataset_name": name_by_id.get(new_id),
                "left_column": actual_left_col,
                "right_column": new_col,
                "rows_before": rows_before,
                "rows_after": int(len(merged)),
                "confidence": rel.get("confidence"),
                "band": rel.get("band"),
                "source": rel.get("source"),
            })
            joined_ids.add(new_id)
            progress = True
            # Restart the candidate scan so confidence ordering still
            # wins after every successful join.
            break
        if not progress:
            break
    return merged, steps


# --------------------------------------------------------------------------
# Background-task helper used by the upload route
# --------------------------------------------------------------------------

def discover_relationships_after_upload(project_id: int, user_id: int) -> None:
    """Auto-discover high-confidence project relationships.

    Called from the dataset-upload background task. Walks every dataset
    in the project, profiles each one, runs the proposer, and persists
    any ``band == 'high'`` pair that is not already represented in
    ``project_relationships``. Lower-confidence proposals continue to
    require a manual data-model refresh — the user keeps control over
    suggestions that aren't a slam dunk.

    Always opens a fresh DB session: the request session is closed by
    the time FastAPI dispatches the background task.
    """
    db = models.SessionLocal()
    try:
        records = (
            db.query(models.DatasetRecord)
            .filter(
                models.DatasetRecord.project_id == project_id,
                models.DatasetRecord.user_id == user_id,
            )
            .order_by(models.DatasetRecord.id.asc())
            .all()
        )
        if len(records) < 2:
            return
        name_by_id = {r.id: (r.dataset_name or r.filename or f"dataset_{r.id}")
                      for r in records}
        id_by_name = {v: k for k, v in name_by_id.items()}
        frames_by_name: dict[str, pd.DataFrame] = {}
        profiles: list[dict] = []
        for r in records:
            df = _load_frame(r)
            if df is None or df.empty:
                continue
            try:
                profiles.append(sm.profile_table(name_by_id[r.id], df))
            except Exception:
                continue
            frames_by_name[name_by_id[r.id]] = df
        if len(profiles) < 2:
            return
        try:
            proposals = sm.propose_relationships_for_project(profiles,
                                                              frames_by_name)
        except Exception:
            return

        existing = (
            db.query(models.ProjectRelationship)
            .filter(models.ProjectRelationship.project_id == project_id)
            .all()
        )
        existing_keys: set[tuple[int, str, int, str]] = set()
        for r in existing:
            existing_keys.add(
                (r.left_dataset_id, r.left_column,
                 r.right_dataset_id, r.right_column)
            )
            existing_keys.add(
                (r.right_dataset_id, r.right_column,
                 r.left_dataset_id, r.left_column)
            )

        added = 0
        for p in proposals:
            if p.band != "high":
                continue
            ldid = id_by_name.get(p.left_table)
            rdid = id_by_name.get(p.right_table)
            if not ldid or not rdid:
                continue
            # Normalise so left_id < right_id, matching the convention
            # used by the data-model refresh path.
            if ldid > rdid:
                ldid, rdid = rdid, ldid
                lcol, rcol = p.right_column, p.left_column
            else:
                lcol, rcol = p.left_column, p.right_column
            key = (ldid, lcol, rdid, rcol)
            if key in existing_keys:
                continue
            db.add(models.ProjectRelationship(
                project_id=project_id,
                left_dataset_id=ldid, left_column=lcol,
                right_dataset_id=rdid, right_column=rcol,
                cardinality=p.cardinality, join_type="left",
                status="proposed",
                band=p.band,
                confidence=float(p.confidence),
                evidence=p.evidence,
                overlap_score=float(p.overlap_score),
                name_score=float(p.name_score),
                dtype_score=float(p.dtype_score),
                user_locked=False,
            ))
            existing_keys.add(key)
            existing_keys.add((rdid, rcol, ldid, lcol))
            added += 1
        if added:
            db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        try:
            db.close()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Endpoint
# --------------------------------------------------------------------------

@router.post("/api/projects/{project_id}/cross-predict")
async def cross_predict(
    project_id: int,
    body: CrossPredictRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
    mode: str = Depends(mode_dependency(request_mode_field="request_mode")),
):
    project = models.get_project(db, project_id, user.id)
    if not project:
        raise HTTPException(404, "Project not found")

    records = _project_datasets(db, project_id, user.id)
    if not records:
        raise HTTPException(404, "Project has no datasets to predict on.")

    target_record = next(
        (r for r in records if r.id == body.target_dataset_id), None,
    )
    if target_record is None:
        raise HTTPException(
            422,
            f"target_dataset_id {body.target_dataset_id} does not "
            f"belong to project {project_id}.",
        )

    name_by_id = {r.id: (r.dataset_name or r.filename or f"dataset_{r.id}")
                  for r in records}
    id_by_name = {v: k for k, v in name_by_id.items()}
    frames_by_id: dict[int, pd.DataFrame] = {}
    for r in records:
        df = _load_frame(r)
        if df is None:
            continue
        frames_by_id[r.id] = df

    target_df = frames_by_id.get(target_record.id)
    if target_df is None or target_df.empty:
        raise HTTPException(
            400, "Target dataset has no rows or could not be loaded.",
        )

    candidates = _candidate_relationships(
        db, project_id, name_by_id, id_by_name, frames_by_id,
    )
    # Filter candidates to only those touching datasets we actually
    # have frames for — avoids spurious "couldn't load" errors.
    candidates = [
        c for c in candidates
        if c["left_id"] in frames_by_id and c["right_id"] in frames_by_id
    ]

    warnings: list[str] = []
    if not candidates or len(records) < 2:
        # Single-dataset fallback. Predict on the target dataset alone.
        merged = target_df.copy()
        steps: list[dict] = []
        skipped = True
        if len(records) >= 2:
            warnings.append(
                "No relationships were found between this project's "
                "datasets — predicting on the target dataset alone.",
            )
        else:
            warnings.append(
                "Only one dataset in this project — predicting on it "
                "alone.",
            )
    else:
        merged, steps = _build_merged(
            target_record.id, frames_by_id, name_by_id, candidates,
        )
        skipped = not steps
        if skipped:
            warnings.append(
                "No relationships were applicable to the target "
                "dataset — predicting on it alone.",
            )

    if body.target_column not in merged.columns:
        raise HTTPException(
            400,
            f"target_column '{body.target_column}' is not present in "
            f"the merged feature matrix.",
        )
    if body.date_column is not None and body.date_column not in merged.columns:
        # Surface as a warning rather than a hard failure: the engine
        # will fall back to non-timeseries family if the date is gone.
        warnings.append(
            f"date_column '{body.date_column}' is not in the merged "
            f"frame; falling back to auto-detection.",
        )
        date_col_for_engine: str | None = None
    else:
        date_col_for_engine = body.date_column

    horizon = int(body.horizon) if body.horizon else 30
    try:
        result = pe.run_prediction(
            merged,
            target_col=body.target_column,
            date_col=date_col_for_engine,
            mode=mode,
            periods=horizon,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    join_plan = {
        "target_dataset_id": target_record.id,
        "target_dataset_name": name_by_id.get(target_record.id),
        "target_rows": int(len(target_df)),
        "merged_rows": int(len(merged)),
        "merged_cols": int(len(merged.columns)),
        "skipped": skipped,
        "joins": steps,
        "warnings": warnings,
    }

    return jsonify({
        "project_id": project_id,
        "target_dataset_id": target_record.id,
        "target_column": body.target_column,
        "mode": mode,
        "guided": result["guided"],
        "expert": result["expert"],
        "join_plan": join_plan,
    })


__all__ = [
    "router",
    "discover_relationships_after_upload",
    "CrossPredictRequest",
]
