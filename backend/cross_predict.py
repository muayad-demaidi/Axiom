"""Cross-dataset prediction endpoint (Task #246).

Exposes ``POST /api/projects/{project_id}/cross-predict`` which:

  1. Loads the ``DatasetRecord`` rows attached to ``project_id`` for
     the requesting user (metadata only — parquet payloads are loaded
     lazily, see step 3).
  2. Pulls join candidates from ``project_relationships`` first
     (``status == 'confirmed'`` plus ``status == 'proposed' & band ==
     'high'`` rows that the upload-time discovery already wrote). Only
     when persisted has nothing usable do we fall back to a fresh
     profile + propose pass — that legacy path loads every parquet, so
     it is reserved for projects that never benefited from
     auto-discovery on upload.
  3. Materialises a single merged feature matrix via
     :func:`data_modelling.materialize_join` — chained left joins
     anchored on the target dataset. Frames are loaded on demand, so a
     project with 50 datasets only ever materialises the ones that
     actually participate in the join graph reachable from the target.
     A pre-flight fan-out estimate downsamples the running merged
     frame before any join that would push the result past the
     ``MAX_MERGED_ROWS`` cap, so a runaway N:N chain cannot OOM the
     API process.
  4. Calls :func:`backend.predictions_engine.run_prediction` on the
     merged frame.
  5. Returns the dual ``{guided, expert}`` payload plus a ``join_plan``
     block describing which datasets were joined on which keys, with
     pre/post row counts and any downsampling warnings.

Background-discovery wiring on upload lives in
:mod:`backend.datasets`.
"""
from __future__ import annotations

import io
import os
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
# Memory budget — chained joins on huge projects are the worst case
# --------------------------------------------------------------------------

# Hard ceiling on the merged feature matrix the predictions engine is
# given. Downsampling rather than refusing keeps the surface usable on
# very large projects: the user gets a representative prediction
# instead of a 5xx. Override via ``AXIOM_CROSS_PREDICT_MAX_ROWS`` for
# tests / capacity tuning. The default (1M rows) is the same threshold
# the dataset-join save path enforces in :mod:`backend.datasets`.
def _resolve_max_merged_rows() -> int:
    raw = os.environ.get("AXIOM_CROSS_PREDICT_MAX_ROWS", "")
    try:
        v = int(raw) if raw else 1_000_000
    except (TypeError, ValueError):
        v = 1_000_000
    return max(1, v)


MAX_MERGED_ROWS = _resolve_max_merged_rows()


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
    if not record or not record.source_parquet:
        return None
    try:
        return pd.read_parquet(io.BytesIO(record.source_parquet))
    except Exception:
        return None


class _FrameLoader:
    """Lazy parquet loader.

    Holds the dataset metadata records but only deserialises a parquet
    payload when ``get(dataset_id)`` is actually called. Hits are
    cached so the same frame is never loaded twice. ``load_all`` is
    available for the rare slow path that genuinely needs every frame
    (the no-persisted-relationships fallback below).
    """

    def __init__(self, records: list):
        self._records_by_id = {r.id: r for r in records}
        self._cache: dict[int, pd.DataFrame | None] = {}

    def get(self, dataset_id: int) -> pd.DataFrame | None:
        if dataset_id in self._cache:
            return self._cache[dataset_id]
        rec = self._records_by_id.get(dataset_id)
        df = _load_frame(rec)
        self._cache[dataset_id] = df
        return df

    def has(self, dataset_id: int) -> bool:
        return dataset_id in self._records_by_id

    def load_all(self) -> dict[int, pd.DataFrame]:
        out: dict[int, pd.DataFrame] = {}
        for did in self._records_by_id:
            df = self.get(did)
            if df is not None:
                out[did] = df
        return out


def _reachable_dataset_ids(
    target_id: int, candidates: list[dict],
) -> set[int]:
    """Walk the (undirected) join graph and return every dataset id
    reachable from ``target_id`` through ``candidates``.

    Used to decide whether a persisted relationship set is *usable*
    for the requested target. A candidate that connects two unrelated
    datasets neither of which is the target contributes nothing to
    the prediction and should not block the propose-fallback.
    """
    reachable = {target_id}
    while True:
        progress = False
        for c in candidates:
            l, r = c["left_id"], c["right_id"]
            if l in reachable and r not in reachable:
                reachable.add(r)
                progress = True
            elif r in reachable and l not in reachable:
                reachable.add(l)
                progress = True
        if not progress:
            break
    return reachable


def _candidate_relationships(
    db,
    project_id: int,
    target_id: int,
    name_by_id: dict[int, str],
    id_by_name: dict[str, int],
    loader: _FrameLoader,
) -> list[dict]:
    """Return a confidence-sorted list of join candidates between
    project datasets — without loading any parquet payloads on the
    happy path.

    Strategy:

      * Read ``project_relationships`` first. Honour every
        ``status == 'confirmed'`` row (these are user-approved) and
        every ``status == 'proposed' & band == 'high'`` row (these
        were written by ``discover_relationships_after_upload`` at
        upload time, so re-running the proposer here would just
        duplicate that work).
      * Confirmed rows get a ``+1`` confidence boost so chained joins
        prefer the human-approved key when it competes with an
        auto-discovered one.
      * The propose fallback runs whenever persisted has no candidate
        that can be reached from ``target_id``. This catches both the
        empty-persisted case (legacy projects) AND projects where
        unrelated persisted edges exist but none touch the target —
        without it, the endpoint would silently degrade to a
        target-only prediction even when a fresh propose pass could
        find a usable join.
      * Persisted rows that *are* usable are kept and merged with the
        fallback proposals (rather than throwing away user-approved
        joins) so a partial persisted graph is still honoured.

    Lower-band proposed rows (``medium``/``low``/``inferred``) are
    intentionally skipped — joining on links the user has not approved
    would silently change prediction inputs, and the data-model page
    is the right place for the user to review them.
    """
    out: list[dict] = []
    seen: set[tuple[int, str, int, str]] = set()

    persisted = (
        db.query(models.ProjectRelationship)
        .filter(
            models.ProjectRelationship.project_id == project_id,
            models.ProjectRelationship.status.in_(["confirmed", "proposed"]),
        )
        .all()
    )
    for r in persisted:
        if r.status == "proposed" and r.band != "high":
            continue
        key = (r.left_dataset_id, r.left_column,
               r.right_dataset_id, r.right_column)
        rev_key = (r.right_dataset_id, r.right_column,
                   r.left_dataset_id, r.left_column)
        if key in seen or rev_key in seen:
            continue
        seen.add(key)
        boost = 1.0 if r.status == "confirmed" else 0.0
        out.append({
            "left_id": r.left_dataset_id,
            "left_col": r.left_column,
            "right_id": r.right_dataset_id,
            "right_col": r.right_column,
            "confidence": float(r.confidence or 0.0) + boost,
            "band": "user" if r.status == "confirmed" else r.band,
            "source": r.status,
        })

    # If persisted already gives us a join that can be reached from
    # the target, the auto-discovery on upload has done its job and
    # the propose pass would just duplicate work. Skip it.
    if out and len(_reachable_dataset_ids(target_id, out)) > 1:
        out.sort(key=lambda r: r["confidence"], reverse=True)
        return out

    # ---- Slow fallback ----
    # Either persisted is empty, or it has no edge reachable from the
    # target. Load every frame and run the full profile + propose
    # pass. This is the only path that materialises every parquet, so
    # it is reserved for the cases where we truly cannot answer
    # without it.
    frames_by_id = loader.load_all()
    if len(frames_by_id) < 2:
        out.sort(key=lambda r: r["confidence"], reverse=True)
        return out

    profiles: list[dict] = []
    for did, df in frames_by_id.items():
        try:
            profiles.append(sm.profile_table(name_by_id[did], df))
        except Exception:
            continue
    if len(profiles) < 2:
        out.sort(key=lambda r: r["confidence"], reverse=True)
        return out
    try:
        proposals = sm.propose_relationships_for_project(
            profiles,
            {p["name"]: frames_by_id[id_by_name[p["name"]]]
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


def _estimate_merge_rows(
    left: pd.DataFrame, right: pd.DataFrame,
    left_col: str, right_col: str,
) -> int:
    """Estimate the row count of a left-join *without* materialising it.

    Reuses the exact-row projection from :mod:`backend.datasets`
    (``_project_join_size``), which mirrors how pandas materialises
    the merge. Imported lazily to side-step a circular import between
    ``backend.datasets`` and this module. Returns a pessimistic upper
    bound on failure so a broken estimate never tricks the caller
    into skipping a downsample.
    """
    try:
        from .datasets import _project_join_size  # type: ignore
        return int(_project_join_size(left[left_col], right[right_col], "left"))
    except Exception:
        return int(len(left)) * int(max(1, len(right)))


def _build_merged(
    target_id: int,
    loader: _FrameLoader,
    name_by_id: dict[int, str],
    candidates: list[dict],
    max_rows: int = MAX_MERGED_ROWS,
) -> tuple[pd.DataFrame, list[dict]]:
    """Chain left joins anchored on the target dataset.

    Walks the candidate list in confidence order and joins any
    relationship that connects an already-joined dataset to a still-
    unjoined one. Continues until no more progress is possible — this
    naturally handles multi-hop chains (target → A → B) without an
    explicit graph search.

    Frames are pulled from ``loader`` on demand so a project with
    many large datasets only deserialises the parquet payloads that
    actually participate in the chain reachable from the target.

    A pre-flight estimate (:func:`_estimate_merge_rows`) is computed
    *before* each join. If the projected result would exceed
    ``max_rows``, the running merged frame is downsampled to a size
    that keeps the post-merge frame under the cap; a warning is
    recorded against the join step. After the merge, a paranoid
    second clip enforces the cap in case the estimate undershot.
    """
    target_df = loader.get(target_id)
    if target_df is None:
        # Caller already validated the target frame, but be defensive.
        return pd.DataFrame(), []
    merged = target_df.copy()
    joined_ids: set[int] = {target_id}
    steps: list[dict] = []
    if len(merged) > max_rows:
        # Target itself busts the cap. Downsample up-front and record
        # a synthetic step so the warning is surfaced to the caller.
        rows_before = int(len(merged))
        merged = merged.sample(
            n=max_rows, random_state=42,
        ).reset_index(drop=True)
        steps.append({
            "dataset_id": target_id,
            "dataset_name": name_by_id.get(target_id),
            "left_column": None,
            "right_column": None,
            "rows_before": rows_before,
            "rows_after": int(len(merged)),
            "confidence": None,
            "band": None,
            "source": "target_clip",
            "downsampled": True,
            "warning": (
                f"Target dataset had {rows_before:,} rows > "
                f"{max_rows:,} cap; downsampled to {max_rows:,} rows "
                f"before joining."
            ),
        })

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

            new_df = loader.get(new_id)
            if new_df is None or new_df.empty:
                continue
            if new_col not in new_df.columns:
                continue
            actual_left_col = _resolve_column(merged, joined_col_raw)
            if actual_left_col is None:
                continue

            rows_before = int(len(merged))

            # ---- Pre-flight cap enforcement ------------------------
            warning: str | None = None
            est_rows = _estimate_merge_rows(
                merged, new_df, actual_left_col, new_col,
            )
            if est_rows > max_rows and rows_before > 1:
                # Scale the left side down so the projected result
                # fits under the cap. Keep at least one row.
                ratio = max_rows / float(est_rows)
                target_left = max(1, int(rows_before * ratio))
                target_left = min(target_left, rows_before)
                merged = merged.sample(
                    n=target_left, random_state=42,
                ).reset_index(drop=True)
                warning = (
                    f"Estimated join would produce ~{est_rows:,} rows "
                    f"(>{max_rows:,} cap); downsampled left side from "
                    f"{rows_before:,} → {target_left:,} rows before "
                    f"merging."
                )
                rows_before = target_left

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

            # ---- Post-merge belt-and-braces clip --------------------
            if len(merged) > max_rows:
                clipped_from = int(len(merged))
                merged = merged.sample(
                    n=max_rows, random_state=42,
                ).reset_index(drop=True)
                extra = (
                    f"Merged frame still hit {clipped_from:,} rows after "
                    f"the join; clipped to the {max_rows:,}-row cap."
                )
                warning = f"{warning} {extra}" if warning else extra

            step = {
                "dataset_id": new_id,
                "dataset_name": name_by_id.get(new_id),
                "left_column": actual_left_col,
                "right_column": new_col,
                "rows_before": rows_before,
                "rows_after": int(len(merged)),
                "confidence": rel.get("confidence"),
                "band": rel.get("band"),
                "source": rel.get("source"),
            }
            if warning:
                step["downsampled"] = True
                step["warning"] = warning
            steps.append(step)
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

def discover_relationships_after_upload(
    project_id: int,
    user_id: int,
    trigger_dataset_id: int | None = None,
) -> dict:
    """Auto-discover high-confidence project relationships.

    Called from the dataset-upload background task. Walks every dataset
    in the project, profiles each one, runs the proposer, and persists
    any ``band == 'high'`` pair that is not already represented in
    ``project_relationships``. Lower-confidence proposals continue to
    require a manual data-model refresh — the user keeps control over
    suggestions that aren't a slam dunk.

    When at least one new high-confidence join is added, a single
    ``UploadNotification`` row is written so the frontend can surface a
    passive "we linked X ↔ Y automatically" toast/inbox card (Task
    #260). One notification per sweep — N joins added by the same
    upload collapse into one summary, never N rows.

    Returns a small summary dict the caller (and tests) can inspect::

        {
            "added": int,                # joins persisted this sweep
            "joins": [ {join dict}, ...],
            "notification_id": int|None, # row in upload_notifications
        }

    Always opens a fresh DB session: the request session is closed by
    the time FastAPI dispatches the background task.
    """
    summary: dict = {"added": 0, "joins": [], "notification_id": None}
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
            return summary
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
            return summary
        try:
            proposals = sm.propose_relationships_for_project(profiles,
                                                              frames_by_name)
        except Exception:
            return summary

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

        added_rows: list[models.ProjectRelationship] = []
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
            row = models.ProjectRelationship(
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
            )
            db.add(row)
            added_rows.append(row)
            existing_keys.add(key)
            existing_keys.add((rdid, rcol, ldid, lcol))
        if added_rows:
            # Flush so the relationship rows get IDs we can reference
            # from the notification payload.
            db.flush()
            joins_payload = []
            for row in added_rows:
                joins_payload.append({
                    "relationship_id": int(row.id),
                    "left_table": name_by_id.get(
                        row.left_dataset_id, str(row.left_dataset_id)),
                    "left_column": row.left_column,
                    "right_table": name_by_id.get(
                        row.right_dataset_id, str(row.right_dataset_id)),
                    "right_column": row.right_column,
                    "cardinality": row.cardinality,
                    "confidence": float(row.confidence or 0.0),
                })
            summary["added"] = len(added_rows)
            summary["joins"] = joins_payload
            note = _build_notification(
                db, project_id, user_id,
                joins_payload, trigger_dataset_id, name_by_id,
            )
            db.commit()
            summary["notification_id"] = (
                int(note.id) if note is not None else None
            )
        else:
            db.commit()
        return summary
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass
        return summary
    finally:
        try:
            db.close()
        except Exception:
            pass


def _build_notification(
    db,
    project_id: int,
    user_id: int,
    joins: list[dict],
    trigger_dataset_id: int | None,
    name_by_id: dict[int, str],
) -> Any | None:
    """Persist a single ``UploadNotification`` summarising one sweep.

    Per Task #260's "de-duplicated to one summary" rule, every sweep
    that adds ≥1 high-confidence join writes exactly one row. The
    summary string is plain English so the toast can render it
    verbatim; the JSON payload carries the structured detail the UI
    needs to deep-link into the data-model drawer.
    """
    if not joins:
        return None
    first = joins[0]
    head = (
        f"We linked {first['left_table']}.{first['left_column']} ↔ "
        f"{first['right_table']}.{first['right_column']} automatically"
    )
    if len(joins) > 1:
        summary_text = f"{head} (+{len(joins) - 1} more) — review →"
    else:
        summary_text = f"{head} — review →"

    trigger_name = (
        name_by_id.get(trigger_dataset_id)
        if trigger_dataset_id is not None else None
    )
    payload = {
        "added_count": len(joins),
        "relationship_ids": [j["relationship_id"] for j in joins],
        "joins": joins,
        "trigger_dataset_id": (
            int(trigger_dataset_id) if trigger_dataset_id is not None else None
        ),
        "trigger_dataset_name": trigger_name,
    }
    note = models.UploadNotification(
        project_id=project_id,
        user_id=user_id,
        kind="auto_link",
        summary=summary_text,
        payload=payload,
    )
    db.add(note)
    db.flush()
    return note


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

    # Lazy frame loader — only deserialises parquet payloads when a
    # specific dataset is actually needed for the join graph.
    loader = _FrameLoader(records)

    # Eagerly load only the target so we can validate row count + the
    # target column. Every other frame stays unloaded until (and
    # unless) the join walk reaches it.
    target_df = loader.get(target_record.id)
    if target_df is None or target_df.empty:
        raise HTTPException(
            400, "Target dataset has no rows or could not be loaded.",
        )

    candidates = _candidate_relationships(
        db, project_id, target_record.id, name_by_id, id_by_name, loader,
    )
    # Filter candidates to only those touching datasets we have a
    # record for — avoids spurious "couldn't load" errors. We do NOT
    # check ``loader._cache`` here: that would force-load every frame.
    # The build loop below handles "couldn't load" gracefully per-edge.
    candidates = [
        c for c in candidates
        if loader.has(c["left_id"]) and loader.has(c["right_id"])
    ]

    # Resolve the cap at request time so tests can monkeypatch the env.
    max_rows = _resolve_max_merged_rows()

    warnings: list[str] = []
    if not candidates or len(records) < 2:
        # Single-dataset fallback. Predict on the target dataset alone.
        merged = target_df.copy()
        if len(merged) > max_rows:
            merged = merged.sample(
                n=max_rows, random_state=42,
            ).reset_index(drop=True)
            warnings.append(
                f"Target dataset exceeded {max_rows:,} rows; "
                f"downsampled before prediction.",
            )
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
            target_record.id, loader, name_by_id, candidates, max_rows,
        )
        # ``target_clip`` is a synthetic step recorded when the target
        # frame busts the size cap before any join runs — it is not a
        # real join, so it must not flip ``skipped``.
        join_steps = [s for s in steps if s.get("source") != "target_clip"]
        skipped = not join_steps
        if skipped:
            warnings.append(
                "No relationships were applicable to the target "
                "dataset — predicting on it alone.",
            )
        for s in steps:
            if s.get("downsampled") and s.get("warning"):
                warnings.append(s["warning"])

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
        "max_merged_rows": int(max_rows),
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
    "MAX_MERGED_ROWS",
]
