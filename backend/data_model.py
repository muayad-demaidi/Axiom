"""Multi-CSV semantic model API.

Endpoints (all scoped under ``/api/projects/{project_id}/data-model``):

  GET    /                       — full bundle (tables, relationships,
                                   open questions, description)
  POST   /refresh                — re-profile every dataset in the
                                   project, propose new joins for any
                                   uncovered pair, regenerate questions
  PATCH  /tables/{dataset_id}    — update role/grain/PK/confirmed
  PATCH  /relationships/{id}     — accept / reject / edit
  POST   /relationships          — add a custom (user-drawn) relationship
  PUT    /description            — set the project's business description
  PATCH  /questions/{id}         — answer or dismiss a clarification

The router never mutates the legacy ``DatasetRelationship`` rows
directly; it writes to the new ``ProjectRelationship`` table and the
chat tools read from both.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from typing import Any

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import models  # type: ignore
import semantic_model as sm  # type: ignore

from ._json import jsonify
from .auth import get_current_user, get_db_session


router = APIRouter(tags=["data-model"])


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _require_project(db, project_id: int, user_id: int):
    proj = models.get_project(db, project_id, user_id)
    if not proj:
        raise HTTPException(404, "Project not found")
    return proj


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


def _load_frames(records: list[Any]) -> dict[int, pd.DataFrame]:
    out: dict[int, pd.DataFrame] = {}
    for r in records:
        if not r.source_parquet:
            continue
        try:
            out[r.id] = pd.read_parquet(io.BytesIO(r.source_parquet))
        except Exception:
            continue
    return out


def _table_view(row: models.ProjectSemanticTable, rec: Any) -> dict:
    cols_meta = row.columns_meta or []
    date_cols = [c.get("name") for c in cols_meta if (c or {}).get("kind") == "date"]
    measure_cols = [c.get("name") for c in cols_meta if (c or {}).get("kind") == "measure"]
    id_cols = [c.get("name") for c in cols_meta if (c or {}).get("kind") == "id"]
    return {
        "id": row.id,
        "dataset_id": row.dataset_id,
        "dataset_name": rec.dataset_name or rec.filename,
        "rows": int(rec.row_count or 0),
        "cols": int(rec.column_count or 0),
        "role": row.role,
        "grain": row.grain or {},
        "pk_columns": row.pk_columns or [],
        "fk_columns": row.fk_columns or [],
        "id_columns": [c for c in id_cols if c],
        "date_columns": [c for c in date_cols if c],
        "measure_columns": [c for c in measure_cols if c],
        "suspicious": row.suspicious or [],
        "role_signals": row.role_signals or [],
        "columns": cols_meta,
        "confirmed": bool(row.confirmed),
        "profiled_at": row.profiled_at.isoformat() if row.profiled_at else None,
    }


def _explain_rel(row: models.ProjectRelationship,
                 left_table: str, right_table: str) -> str:
    """One-sentence plain-language description of the join, suitable
    for showing in the UI under each relationship row."""
    card = row.cardinality or "1:N"
    overlap_pct = round(float(row.overlap_score or 0.0) * 100)
    band = row.band or "low"
    if card == "1:1":
        kind = "one row in each table matches one row in the other"
    elif card == "1:N":
        kind = f"each `{left_table}` row matches many `{right_table}` rows"
    elif card == "N:1":
        kind = f"each `{right_table}` row matches many `{left_table}` rows"
    elif card == "N:N":
        kind = "rows on both sides can match many rows on the other side"
    else:
        kind = "the two tables are linked"
    confidence = "strong" if band in ("high", "user") \
        else "medium" if band == "medium" \
        else "weak" if band in ("low", "inferred") \
        else band
    return (
        f"Join `{left_table}.{row.left_column}` to "
        f"`{right_table}.{row.right_column}` ({kind}); "
        f"{overlap_pct}% of values overlap, {confidence} match."
    )


def _rel_view(row: models.ProjectRelationship, name_by_id: dict[int, str]) -> dict:
    lt = name_by_id.get(row.left_dataset_id, str(row.left_dataset_id))
    rt = name_by_id.get(row.right_dataset_id, str(row.right_dataset_id))
    return {
        "id": row.id,
        "left_dataset_id": row.left_dataset_id,
        "left_table": lt,
        "left_column": row.left_column,
        "right_dataset_id": row.right_dataset_id,
        "right_table": rt,
        "right_column": row.right_column,
        "cardinality": row.cardinality,
        "join_type": row.join_type,
        "status": row.status,
        "band": row.band,
        "confidence": float(row.confidence or 0.0),
        "evidence": row.evidence or [],
        "explanation": _explain_rel(row, lt, rt),
        "overlap_score": float(row.overlap_score or 0.0),
        "user_locked": bool(row.user_locked),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _question_view(row: models.ProjectModelQuestion) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "prompt": row.prompt,
        "target": row.target or {},
        "options": row.options or [],
        "status": row.status,
        "answer": row.answer,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _bundle(db, project_id: int, user_id: int) -> dict:
    records = _project_datasets(db, project_id, user_id)
    name_by_id = {r.id: (r.dataset_name or r.filename or f"dataset_{r.id}")
                  for r in records}
    rec_by_id = {r.id: r for r in records}
    table_rows = (
        db.query(models.ProjectSemanticTable)
        .filter(models.ProjectSemanticTable.project_id == project_id)
        .all()
    )
    rel_rows = (
        db.query(models.ProjectRelationship)
        .filter(models.ProjectRelationship.project_id == project_id)
        .order_by(models.ProjectRelationship.confidence.desc(),
                  models.ProjectRelationship.id.asc())
        .all()
    )
    q_rows = (
        db.query(models.ProjectModelQuestion)
        .filter(models.ProjectModelQuestion.project_id == project_id,
                models.ProjectModelQuestion.status == "open")
        .order_by(models.ProjectModelQuestion.id.asc())
        .all()
    )
    sem = (
        db.query(models.ProjectSemanticModel)
        .filter(models.ProjectSemanticModel.project_id == project_id)
        .first()
    )
    tables_payload = []
    for t in table_rows:
        rec = rec_by_id.get(t.dataset_id)
        if rec is None:
            continue
        tables_payload.append(_table_view(t, rec))
    return {
        "project_id": project_id,
        "description": (sem.description if sem else None),
        "confirmed": bool(sem.confirmed) if sem else False,
        "last_refreshed_at": (sem.last_refreshed_at.isoformat()
                              if sem and sem.last_refreshed_at else None),
        "datasets": [
            {"id": r.id, "name": name_by_id[r.id],
             "rows": int(r.row_count or 0),
             "cols": int(r.column_count or 0)}
            for r in records
        ],
        "tables": tables_payload,
        "relationships": [_rel_view(r, name_by_id) for r in rel_rows],
        "questions": [_question_view(q) for q in q_rows],
    }


# --------------------------------------------------------------------------
# Read
# --------------------------------------------------------------------------

@router.get("/api/projects/{project_id}/data-model")
async def get_data_model(
    project_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_project(db, project_id, user.id)
    return jsonify(_bundle(db, project_id, user.id))


# --------------------------------------------------------------------------
# Refresh — re-profile + re-suggest for the whole project
# --------------------------------------------------------------------------

def refresh_project_model(db, project_id: int, user_id: int) -> dict:
    """Re-run the full pipeline and persist results.

    Behaviour:
      • Profile every dataset; upsert ProjectSemanticTable rows. User-
        confirmed rows keep their role/grain/PK overrides; only the
        auto-detected metadata (signals, suspicious, columns_meta) is
        refreshed.
      • Propose cross-table relationships. New high/medium proposals
        are inserted as ``status='proposed'``. Existing rows that match
        a new proposal get their confidence/evidence refreshed UNLESS
        ``user_locked=True``.
      • Generate clarification questions and replace any 'open' rows
        whose targets no longer exist.
    """
    records = _project_datasets(db, project_id, user_id)
    if not records:
        return _bundle(db, project_id, user_id)
    frames_by_id = _load_frames(records)
    name_by_id = {r.id: (r.dataset_name or r.filename or f"dataset_{r.id}")
                  for r in records}
    id_by_name = {v: k for k, v in name_by_id.items()}

    # ---- Profile every dataset --------------------------------------
    profiles: list[dict] = []
    for r in records:
        df = frames_by_id.get(r.id)
        prof = sm.profile_table(name_by_id[r.id], df if df is not None else pd.DataFrame())
        profiles.append(prof)
        existing = (
            db.query(models.ProjectSemanticTable)
            .filter(models.ProjectSemanticTable.dataset_id == r.id)
            .first()
        )
        if existing is None:
            row = models.ProjectSemanticTable(
                project_id=project_id,
                dataset_id=r.id,
                role=prof["role"],
                grain=prof["grain"],
                pk_columns=prof["pk_candidates"],
                fk_columns=prof["fk_candidates"],
                suspicious=prof["suspicious"],
                role_signals=prof["role_signals"],
                columns_meta=prof["columns"],
                confirmed=False,
                profiled_at=datetime.utcnow(),
            )
            db.add(row)
        else:
            # Always refresh diagnostics; only touch role/grain/pk when
            # the user hasn't locked them.
            existing.suspicious = prof["suspicious"]
            existing.role_signals = prof["role_signals"]
            existing.columns_meta = prof["columns"]
            existing.fk_columns = prof["fk_candidates"]
            existing.profiled_at = datetime.utcnow()
            if not existing.confirmed:
                existing.role = prof["role"]
                existing.grain = prof["grain"]
                existing.pk_columns = prof["pk_candidates"]
    db.commit()

    # ---- Relationship proposals -------------------------------------
    # Strict incremental scoring: only score pairs where at least one
    # side is a NEW dataset (no relationships scored against it yet) OR
    # the pair has no existing relationship row at all. Already-scored
    # pairs keep their confidence/evidence so user feedback doesn't get
    # silently overwritten on refresh. User-locked pairs are always
    # skipped regardless.
    frames_by_name = {name_by_id[i]: f for i, f in frames_by_id.items()}
    existing_rels = (
        db.query(models.ProjectRelationship)
        .filter(models.ProjectRelationship.project_id == project_id)
        .all()
    )
    rel_by_key = {
        (r.left_dataset_id, r.left_column,
         r.right_dataset_id, r.right_column): r for r in existing_rels
    }
    locked_pairs: set[tuple[int, int]] = set()
    seen_dataset_ids: set[int] = set()
    scored_pairs: set[tuple[int, int]] = set()
    for r in existing_rels:
        a, b = sorted((r.left_dataset_id, r.right_dataset_id))
        scored_pairs.add((a, b))
        seen_dataset_ids.add(r.left_dataset_id)
        seen_dataset_ids.add(r.right_dataset_id)
        if r.user_locked:
            locked_pairs.add((a, b))

    pair_profiles: list[dict] = []
    pair_frames: dict[str, pd.DataFrame] = {}
    for i, p_left in enumerate(profiles):
        for p_right in profiles[i + 1:]:
            ldid = id_by_name.get(p_left["name"])
            rdid = id_by_name.get(p_right["name"])
            if not ldid or not rdid:
                continue
            a, b = sorted((ldid, rdid))
            if (a, b) in locked_pairs:
                continue
            # Skip pairs that have already been scored in a prior
            # refresh AND involve no newly-added dataset. New datasets
            # are those not present in any existing relationship.
            both_seen = ldid in seen_dataset_ids and rdid in seen_dataset_ids
            if (a, b) in scored_pairs and both_seen:
                continue
            for prof in (p_left, p_right):
                if prof["name"] not in {pp["name"] for pp in pair_profiles}:
                    pair_profiles.append(prof)
                if prof["name"] in frames_by_name:
                    pair_frames[prof["name"]] = frames_by_name[prof["name"]]

    proposals = (
        sm.propose_relationships_for_project(pair_profiles, pair_frames)
        if pair_profiles else []
    )

    seen_keys: set = set()
    for p in proposals:
        ldid = id_by_name.get(p.left_table)
        rdid = id_by_name.get(p.right_table)
        if not ldid or not rdid:
            continue
        # Normalise ordering so left < right consistently.
        if ldid > rdid:
            ldid, rdid = rdid, ldid
            lcol, rcol = p.right_column, p.left_column
        else:
            lcol, rcol = p.left_column, p.right_column
        key = (ldid, lcol, rdid, rcol)
        seen_keys.add(key)
        existing = rel_by_key.get(key)
        if existing is None:
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
        else:
            if not existing.user_locked:
                existing.cardinality = p.cardinality
                existing.band = p.band
                existing.confidence = float(p.confidence)
                existing.evidence = p.evidence
                existing.overlap_score = float(p.overlap_score)
                existing.name_score = float(p.name_score)
                existing.dtype_score = float(p.dtype_score)
                existing.updated_at = datetime.utcnow()
    db.commit()

    # ---- Clarification questions ------------------------------------
    # Replace ALL "open" questions on a refresh; keep answered/dismissed
    # so we don't keep nagging the user about something they already
    # handled.
    (db.query(models.ProjectModelQuestion)
       .filter(models.ProjectModelQuestion.project_id == project_id,
               models.ProjectModelQuestion.status == "open")
       .delete(synchronize_session=False))

    # Use the freshly-rebuilt rel rows as the basis for question generation.
    refreshed_rels = (
        db.query(models.ProjectRelationship)
        .filter(models.ProjectRelationship.project_id == project_id)
        .all()
    )
    rel_payload_for_q = []
    for r in refreshed_rels:
        # Only unresolved proposals can still need clarification — a
        # confirmed/rejected join is the user's final word, so re-asking
        # about it would be noisy and violate the spec.
        if r.status != "proposed":
            continue
        rel_payload_for_q.append(sm.ProposedRelationship(
            left_table=name_by_id.get(r.left_dataset_id, str(r.left_dataset_id)),
            left_column=r.left_column,
            right_table=name_by_id.get(r.right_dataset_id, str(r.right_dataset_id)),
            right_column=r.right_column,
            cardinality=r.cardinality,
            confidence=float(r.confidence or 0.0),
            band=r.band,
            evidence=list(r.evidence or []),
            overlap_score=float(r.overlap_score or 0.0),
            name_score=float(r.name_score or 0.0),
            dtype_score=float(r.dtype_score or 0.0),
        ))
    questions = sm.generate_clarification_questions(profiles, rel_payload_for_q)
    for q in questions:
        db.add(models.ProjectModelQuestion(
            project_id=project_id,
            external_id=q.id,
            kind=q.kind, prompt=q.prompt,
            target=q.target, options=q.options,
            status="open",
        ))

    sem_row = (
        db.query(models.ProjectSemanticModel)
        .filter(models.ProjectSemanticModel.project_id == project_id)
        .first()
    )
    if sem_row is None:
        sem_row = models.ProjectSemanticModel(
            project_id=project_id, description=None,
            confirmed=False, last_refreshed_at=datetime.utcnow(),
        )
        db.add(sem_row)
    else:
        sem_row.last_refreshed_at = datetime.utcnow()
    db.commit()

    return _bundle(db, project_id, user_id)


@router.post("/api/projects/{project_id}/data-model/refresh")
async def post_refresh(
    project_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_project(db, project_id, user.id)
    return jsonify(refresh_project_model(db, project_id, user.id))


# --------------------------------------------------------------------------
# Table updates
# --------------------------------------------------------------------------

class TableUpdateRequest(BaseModel):
    role: str | None = None
    pk_columns: list[str] | None = None
    grain: dict[str, Any] | None = None
    confirmed: bool | None = None


@router.patch("/api/projects/{project_id}/data-model/tables/{dataset_id}")
async def patch_table(
    project_id: int,
    dataset_id: int,
    req: TableUpdateRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_project(db, project_id, user.id)
    row = (
        db.query(models.ProjectSemanticTable)
        .filter(models.ProjectSemanticTable.project_id == project_id,
                models.ProjectSemanticTable.dataset_id == dataset_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Semantic table row not found")
    if req.role is not None:
        if req.role not in ("fact", "dimension", "summary", "bridge"):
            raise HTTPException(400, "Invalid role")
        row.role = req.role
    if req.pk_columns is not None:
        row.pk_columns = list(req.pk_columns)
    if req.grain is not None:
        row.grain = dict(req.grain)
    if req.confirmed is not None:
        row.confirmed = bool(req.confirmed)
        row.confirmed_at = datetime.utcnow() if req.confirmed else None
    db.commit()
    return jsonify(_bundle(db, project_id, user.id))


# --------------------------------------------------------------------------
# Relationship updates
# --------------------------------------------------------------------------

class RelationshipUpdateRequest(BaseModel):
    status: str | None = None  # "confirmed" | "rejected" | "proposed"
    cardinality: str | None = None
    join_type: str | None = None
    left_column: str | None = None
    right_column: str | None = None
    user_locked: bool | None = None


@router.patch("/api/projects/{project_id}/data-model/relationships/{rel_id}")
async def patch_relationship(
    project_id: int,
    rel_id: int,
    req: RelationshipUpdateRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_project(db, project_id, user.id)
    row = (
        db.query(models.ProjectRelationship)
        .filter(models.ProjectRelationship.project_id == project_id,
                models.ProjectRelationship.id == rel_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, "Relationship not found")
    if req.status is not None:
        if req.status not in ("proposed", "confirmed", "rejected"):
            raise HTTPException(400, "Invalid status")
        row.status = req.status
        row.user_locked = req.status in ("confirmed", "rejected")
    if req.cardinality is not None:
        row.cardinality = req.cardinality
    if req.join_type is not None:
        row.join_type = req.join_type
    # Allow editing the actual join columns. Validate against the
    # column metadata persisted on the semantic-table side so the
    # user can't point a join at a column that doesn't exist.
    if req.left_column is not None or req.right_column is not None:
        def _cols_for(dataset_id: int) -> set[str]:
            t = (db.query(models.ProjectSemanticTable)
                   .filter(models.ProjectSemanticTable.project_id == project_id,
                           models.ProjectSemanticTable.dataset_id == dataset_id)
                   .first())
            if not t or not t.columns_meta:
                return set()
            return {c.get("name") for c in (t.columns_meta or []) if c.get("name")}
        if req.left_column is not None:
            allowed = _cols_for(row.left_dataset_id)
            if allowed and req.left_column not in allowed:
                raise HTTPException(400, f"Unknown left column: {req.left_column}")
            row.left_column = req.left_column
        if req.right_column is not None:
            allowed = _cols_for(row.right_dataset_id)
            if allowed and req.right_column not in allowed:
                raise HTTPException(400, f"Unknown right column: {req.right_column}")
            row.right_column = req.right_column
        # Editing join columns is a strong user signal — lock it in.
        row.user_locked = True
    if req.user_locked is not None:
        row.user_locked = bool(req.user_locked)
    row.updated_at = datetime.utcnow()
    db.commit()
    return jsonify(_bundle(db, project_id, user.id))


class RelationshipCreateRequest(BaseModel):
    left_dataset_id: int
    left_column: str
    right_dataset_id: int
    right_column: str
    cardinality: str = "1:N"
    join_type: str = "left"


@router.post("/api/projects/{project_id}/data-model/relationships")
async def post_relationship(
    project_id: int,
    req: RelationshipCreateRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_project(db, project_id, user.id)
    # Make sure both datasets belong to the project + user.
    owned = (
        db.query(models.DatasetRecord.id)
        .filter(models.DatasetRecord.user_id == user.id,
                models.DatasetRecord.project_id == project_id,
                models.DatasetRecord.id.in_([req.left_dataset_id,
                                              req.right_dataset_id]))
        .all()
    )
    if len({row[0] for row in owned}) != 2:
        raise HTTPException(400, "Datasets must belong to this project")
    ldid, rdid = req.left_dataset_id, req.right_dataset_id
    lc, rc = req.left_column, req.right_column
    if ldid > rdid:
        ldid, rdid = rdid, ldid
        lc, rc = rc, lc
    row = models.ProjectRelationship(
        project_id=project_id,
        left_dataset_id=ldid, left_column=lc,
        right_dataset_id=rdid, right_column=rc,
        cardinality=req.cardinality, join_type=req.join_type,
        status="confirmed", band="high", confidence=1.0,
        evidence=["user-defined relationship"],
        user_locked=True,
    )
    db.add(row)
    db.commit()
    return jsonify(_bundle(db, project_id, user.id))


# --------------------------------------------------------------------------
# Description
# --------------------------------------------------------------------------

class DescriptionRequest(BaseModel):
    description: str
    confirmed: bool | None = None


_ROLE_PATTERN = re.compile(
    r"`?([A-Za-z_][\w]*)`?\s+(?:is|are|=|as)\s+(?:a|an|the)?\s*"
    r"(fact|dimension|summary|bridge)\b",
    re.IGNORECASE,
)
_JOIN_PATTERN = re.compile(
    r"`?([A-Za-z_][\w]*)`?\.`?([A-Za-z_][\w]*)`?\s*"
    r"(?:joins?|=|↔|<->|matches)\s*"
    r"`?([A-Za-z_][\w]*)`?\.`?([A-Za-z_][\w]*)`?",
    re.IGNORECASE,
)
_PK_PATTERN = re.compile(
    r"`?([A-Za-z_][\w]*)`?\s+uses?\s+`?([A-Za-z_][\w]*)`?\s+as\s+"
    r"(?:the\s+)?(?:primary\s+key|pk|id|identifier)",
    re.IGNORECASE,
)


def _apply_description_overrides(
    db, project_id: int, user_id: int, description: str
) -> list[str]:
    """Parse the user's free-text business description for explicit
    overrides ("X is a fact table", "A.col joins B.col", "T uses id
    as PK") and apply them to the persisted semantic model. Returns
    a list of human-readable change descriptions for telemetry.

    This is intentionally narrow: only confident, anchored phrasings
    are honored, so a free-form paragraph won't accidentally rewrite
    the model. Anything ambiguous is left alone for the user to
    confirm via the regular role/join controls.
    """
    if not description or not description.strip():
        return []
    text = description.strip()
    records = _project_datasets(db, project_id, user_id)
    name_to_id = {(r.dataset_name or r.filename or f"dataset_{r.id}"): r.id
                  for r in records}
    name_lookup = {n.lower(): n for n in name_to_id}

    def _resolve(name: str | None) -> str | None:
        if not name:
            return None
        n = name.strip().lower()
        return name_lookup.get(n)

    changes: list[str] = []

    # --- Role overrides -----------------------------------------------
    for m in _ROLE_PATTERN.finditer(text):
        tname = _resolve(m.group(1))
        role = m.group(2).lower()
        if not tname or role not in ("fact", "dimension", "summary", "bridge"):
            continue
        did = name_to_id[tname]
        row = (db.query(models.ProjectSemanticTable)
                 .filter(models.ProjectSemanticTable.project_id == project_id,
                         models.ProjectSemanticTable.dataset_id == did)
                 .first())
        if row and row.role != role:
            row.role = role
            row.confirmed = True
            row.confirmed_at = datetime.utcnow()
            changes.append(f"role[{tname}]={role}")

    # --- Primary-key overrides ----------------------------------------
    for m in _PK_PATTERN.finditer(text):
        tname = _resolve(m.group(1))
        col = m.group(2)
        if not tname or not col:
            continue
        did = name_to_id[tname]
        row = (db.query(models.ProjectSemanticTable)
                 .filter(models.ProjectSemanticTable.project_id == project_id,
                         models.ProjectSemanticTable.dataset_id == did)
                 .first())
        if not row:
            continue
        cols = [c.get("name") for c in (row.columns_meta or [])]
        if col not in cols:
            continue
        pk_now = list(row.pk_columns or [])
        if pk_now[:1] != [col]:
            row.pk_columns = [col] + [c for c in pk_now if c != col]
            row.confirmed = True
            row.confirmed_at = datetime.utcnow()
            changes.append(f"pk[{tname}]={col}")

    # --- Join confirmations / additions -------------------------------
    for m in _JOIN_PATTERN.finditer(text):
        lt = _resolve(m.group(1)); lc = m.group(2)
        rt = _resolve(m.group(3)); rc = m.group(4)
        if not (lt and rt and lc and rc and lt != rt):
            continue
        ldid, rdid = name_to_id[lt], name_to_id[rt]
        # Normalize so left_dataset_id < right_dataset_id.
        if ldid > rdid:
            ldid, rdid = rdid, ldid
            lc, rc = rc, lc
        existing = (db.query(models.ProjectRelationship)
                      .filter(models.ProjectRelationship.project_id == project_id,
                              models.ProjectRelationship.left_dataset_id == ldid,
                              models.ProjectRelationship.left_column == lc,
                              models.ProjectRelationship.right_dataset_id == rdid,
                              models.ProjectRelationship.right_column == rc)
                      .first())
        if existing:
            if existing.status != "confirmed":
                existing.status = "confirmed"
                existing.user_locked = True
                existing.updated_at = datetime.utcnow()
                changes.append(f"confirm[{lt}.{lc}↔{rt}.{rc}]")
        else:
            new = models.ProjectRelationship(
                project_id=project_id,
                left_dataset_id=ldid, left_column=lc,
                right_dataset_id=rdid, right_column=rc,
                cardinality="1:N", join_type="left",
                status="confirmed", band="user",
                confidence=1.0, evidence=["from business description"],
                overlap_score=1.0, user_locked=True,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(new)
            changes.append(f"add[{lt}.{lc}↔{rt}.{rc}]")
    return changes


@router.put("/api/projects/{project_id}/data-model/description")
async def put_description(
    project_id: int,
    req: DescriptionRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_project(db, project_id, user.id)
    sem = (
        db.query(models.ProjectSemanticModel)
        .filter(models.ProjectSemanticModel.project_id == project_id)
        .first()
    )
    desc_text = (req.description or "").strip()
    if sem is None:
        sem = models.ProjectSemanticModel(
            project_id=project_id,
            description=desc_text,
            confirmed=bool(req.confirmed) if req.confirmed is not None else False,
        )
        db.add(sem)
    else:
        sem.description = desc_text
        if req.confirmed is not None:
            sem.confirmed = bool(req.confirmed)
            sem.confirmed_at = datetime.utcnow() if req.confirmed else None

    # Apply explicit overrides found in the description (role, PK,
    # joins). Any change here is user-locked so a future refresh
    # won't overwrite it.
    _apply_description_overrides(db, project_id, user.id, desc_text)
    db.commit()
    return jsonify(_bundle(db, project_id, user.id))


# --------------------------------------------------------------------------
# Question answers
# --------------------------------------------------------------------------

class QuestionAnswerRequest(BaseModel):
    answer: dict[str, Any] | None = None
    status: str = "answered"  # "answered" | "dismissed"


@router.patch("/api/projects/{project_id}/data-model/questions/{q_id}")
async def patch_question(
    project_id: int,
    q_id: int,
    req: QuestionAnswerRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    _require_project(db, project_id, user.id)
    q = (
        db.query(models.ProjectModelQuestion)
        .filter(models.ProjectModelQuestion.project_id == project_id,
                models.ProjectModelQuestion.id == q_id)
        .first()
    )
    if q is None:
        raise HTTPException(404, "Question not found")
    if req.status not in ("answered", "dismissed", "open"):
        raise HTTPException(400, "Invalid status")
    q.status = req.status
    q.answer = req.answer
    q.answered_at = datetime.utcnow() if req.status != "open" else None

    # If the answer flips a join's confirmation, propagate to the
    # ProjectRelationship row so the chat picks it up immediately.
    if q.kind in ("weak_join", "summary_link") and req.answer:
        choice = (req.answer or {}).get("value")
        target = q.target or {}
        if choice in ("confirm", "reject", "keep_separate", "inferred_join"):
            ldid = (db.query(models.DatasetRecord.id)
                      .filter(models.DatasetRecord.project_id == project_id,
                              models.DatasetRecord.dataset_name == target.get("left_table"))
                      .first())
            rdid = (db.query(models.DatasetRecord.id)
                      .filter(models.DatasetRecord.project_id == project_id,
                              models.DatasetRecord.dataset_name == target.get("right_table"))
                      .first())
            if ldid and rdid:
                lid, rid = ldid[0], rdid[0]
                if lid > rid:
                    lid, rid = rid, lid
                    lc, rc = target.get("right_column"), target.get("left_column")
                else:
                    lc, rc = target.get("left_column"), target.get("right_column")
                rel = (
                    db.query(models.ProjectRelationship)
                    .filter(models.ProjectRelationship.project_id == project_id,
                            models.ProjectRelationship.left_dataset_id == lid,
                            models.ProjectRelationship.left_column == lc,
                            models.ProjectRelationship.right_dataset_id == rid,
                            models.ProjectRelationship.right_column == rc)
                    .first()
                )
                if rel:
                    if choice in ("confirm", "inferred_join"):
                        rel.status = "confirmed"
                    elif choice in ("reject", "keep_separate"):
                        rel.status = "rejected"
                    rel.user_locked = True
                    rel.updated_at = datetime.utcnow()

    # Role-pick answers update the table's role + confirm it.
    if q.kind == "role_pick" and req.answer:
        choice = (req.answer or {}).get("value")
        target = q.target or {}
        tname = target.get("table")
        if choice in ("fact", "dimension", "summary", "bridge") and tname:
            row = (db.query(models.ProjectSemanticTable)
                    .join(models.DatasetRecord,
                          models.DatasetRecord.id ==
                          models.ProjectSemanticTable.dataset_id)
                    .filter(models.ProjectSemanticTable.project_id == project_id,
                            models.DatasetRecord.dataset_name == tname)
                    .first())
            if row:
                row.role = choice
                row.confirmed = True
                row.confirmed_at = datetime.utcnow()
    db.commit()

    # Re-score relationships that touch the affected table(s) so the
    # confidence/cardinality the user sees reflects the new state. We
    # scope this to the impacted pair (or pairs containing the role-
    # picked table) rather than re-running the full project refresh,
    # which would be expensive and could overwrite unrelated edits.
    try:
        affected: set[str] = set()
        target = q.target or {}
        if q.kind in ("weak_join", "summary_link"):
            for k in ("left_table", "right_table"):
                if target.get(k):
                    affected.add(target[k])
        elif q.kind == "role_pick" and target.get("table"):
            affected.add(target["table"])
        if affected:
            _rescore_pairs_touching(db, project_id, user.id, affected)
            db.commit()
    except Exception:
        db.rollback()

    # Re-generate the open-question list so any clarification that's
    # been resolved (a join now confirmed, a role now overridden, …)
    # disappears and any newly-relevant question (e.g. a low-band
    # join that surfaced after the user's answer) shows up. We only
    # touch *open* rows; user-answered/dismissed history is preserved.
    try:
        _regenerate_open_questions(db, project_id, user.id)
        db.commit()
    except Exception:
        db.rollback()

    return jsonify(_bundle(db, project_id, user.id))


def _rescore_pairs_touching(
    db, project_id: int, user_id: int, table_names: set[str]
) -> None:
    """Re-run pair scoring for every pair of project tables where at
    least one side is in ``table_names``. Updates non-user-locked
    relationship rows in place; never touches user-locked / confirmed
    / rejected rows.
    """
    import semantic_model as sm

    records = _project_datasets(db, project_id, user_id)
    name_by_id = {r.id: (r.dataset_name or r.filename or f"dataset_{r.id}")
                  for r in records}
    id_by_name = {v: k for k, v in name_by_id.items()}

    # Load frames + profiles for the affected tables and any of their
    # current neighbors so cross-pair scoring covers what the user
    # might be impacting.
    relevant_names: set[str] = set(table_names)
    for r in (db.query(models.ProjectRelationship)
                .filter(models.ProjectRelationship.project_id == project_id)
                .all()):
        ln = name_by_id.get(r.left_dataset_id)
        rn = name_by_id.get(r.right_dataset_id)
        if ln in table_names and rn:
            relevant_names.add(rn)
        if rn in table_names and ln:
            relevant_names.add(ln)

    frames: dict[str, pd.DataFrame] = {}
    profiles: list[dict] = []
    for rec in records:
        nm = name_by_id.get(rec.id)
        if nm not in relevant_names:
            continue
        try:
            df = pd.read_parquet(io.BytesIO(rec.source_parquet)) \
                if rec.source_parquet else None
        except Exception:
            df = None
        if df is None or df.empty:
            continue
        frames[nm] = df
        profiles.append(sm.profile_table(nm, df))

    if len(profiles) < 2:
        return

    fresh = sm.propose_relationships_for_project(profiles, frames)

    # Index existing rows so we can update in place.
    existing_rows = (db.query(models.ProjectRelationship)
                       .filter(models.ProjectRelationship.project_id == project_id)
                       .all())
    by_key: dict[tuple, models.ProjectRelationship] = {}
    for er in existing_rows:
        ln = name_by_id.get(er.left_dataset_id)
        rn = name_by_id.get(er.right_dataset_id)
        if not ln or not rn:
            continue
        by_key[(ln, er.left_column, rn, er.right_column)] = er

    for p in fresh:
        # Only act on pairs that include at least one affected table.
        if (p.left_table not in table_names
                and p.right_table not in table_names):
            continue
        ldid = id_by_name.get(p.left_table)
        rdid = id_by_name.get(p.right_table)
        if ldid is None or rdid is None:
            continue
        # Normalize order so left < right
        lcol, rcol = p.left_column, p.right_column
        if ldid > rdid:
            ldid, rdid = rdid, ldid
            lcol, rcol = rcol, lcol
            ln, rn = p.right_table, p.left_table
        else:
            ln, rn = p.left_table, p.right_table
        existing = by_key.get((ln, lcol, rn, rcol))
        if existing is None:
            db.add(models.ProjectRelationship(
                project_id=project_id,
                left_dataset_id=ldid, left_column=lcol,
                right_dataset_id=rdid, right_column=rcol,
                cardinality=p.cardinality, join_type="left",
                status="proposed", band=p.band,
                confidence=float(p.confidence), evidence=p.evidence,
                overlap_score=float(p.overlap_score),
                name_score=float(p.name_score),
                dtype_score=float(p.dtype_score),
                user_locked=False,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ))
        elif not existing.user_locked:
            existing.cardinality = p.cardinality
            existing.band = p.band
            existing.confidence = float(p.confidence)
            existing.evidence = p.evidence
            existing.overlap_score = float(p.overlap_score)
            existing.name_score = float(p.name_score)
            existing.dtype_score = float(p.dtype_score)
            existing.updated_at = datetime.utcnow()


def _regenerate_open_questions(db, project_id: int, user_id: int) -> None:
    """Drop currently-open clarification questions and recompute them
    from the latest model state. Answered/dismissed rows are kept as
    audit history.
    """
    import semantic_model as sm  # local import to avoid module cycle

    # Collect current model state
    records = _project_datasets(db, project_id, user_id)
    name_by_id = {r.id: (r.dataset_name or r.filename or f"dataset_{r.id}")
                  for r in records}
    table_rows = (db.query(models.ProjectSemanticTable)
                    .filter(models.ProjectSemanticTable.project_id == project_id)
                    .all())
    profiles = []
    for row in table_rows:
        if row.dataset_id not in name_by_id:
            continue
        profiles.append({
            "name": name_by_id[row.dataset_id],
            "role": row.role,
            "rows": next((r.row_count or 0 for r in records
                          if r.id == row.dataset_id), 0),
            "cols": next((r.column_count or 0 for r in records
                          if r.id == row.dataset_id), 0),
            "grain": row.grain or {},
            "pk_candidates": row.pk_columns or [],
            "role_signals": row.role_signals or [],
            "suspicious": row.suspicious or [],
        })

    rel_rows = (db.query(models.ProjectRelationship)
                  .filter(models.ProjectRelationship.project_id == project_id)
                  .all())
    proposals = []
    for r in rel_rows:
        if r.left_dataset_id not in name_by_id or r.right_dataset_id not in name_by_id:
            continue
        # Skip resolved (confirmed/rejected) when generating questions
        # — only "proposed" rows can still need clarification.
        if r.status != "proposed":
            continue
        try:
            proposals.append(sm.ProposedRelationship(
                left_table=name_by_id[r.left_dataset_id],
                left_column=r.left_column,
                right_table=name_by_id[r.right_dataset_id],
                right_column=r.right_column,
                cardinality=r.cardinality,
                overlap_score=float(r.overlap_score or 0.0),
                confidence=float(r.confidence or 0.0),
                band=r.band,
                evidence=list(r.evidence or []),
            ))
        except Exception:
            continue

    fresh = sm.generate_clarification_questions(profiles, proposals)
    fresh_ids = {q.id for q in fresh}

    # Delete currently-open questions whose external id no longer
    # appears in the recomputed set.
    open_rows = (db.query(models.ProjectModelQuestion)
                   .filter(models.ProjectModelQuestion.project_id == project_id,
                           models.ProjectModelQuestion.status == "open")
                   .all())
    existing_ids = set()
    for row in open_rows:
        if row.external_id not in fresh_ids:
            db.delete(row)
        else:
            existing_ids.add(row.external_id)

    # Insert any newly-generated questions that aren't already present.
    for q in fresh:
        if q.id in existing_ids:
            continue
        # If a row with this external_id already exists in any status,
        # skip — we don't want to resurrect dismissed questions.
        already = (db.query(models.ProjectModelQuestion)
                     .filter(models.ProjectModelQuestion.project_id == project_id,
                             models.ProjectModelQuestion.external_id == q.id)
                     .first())
        if already:
            continue
        db.add(models.ProjectModelQuestion(
            project_id=project_id,
            external_id=q.id,
            kind=q.kind,
            prompt=q.prompt,
            target=q.target, options=q.options,
            status="open",
            created_at=datetime.utcnow(),
        ))
