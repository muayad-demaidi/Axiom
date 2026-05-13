"""FastAPI router for the guided predictive flow (Task #212).

Exposes two endpoints used by the wizard inside the Predictions tab of
the Artifact Drawer:

  * ``POST /api/predict/guided/analyze`` — profile a dataset and
    return the detected target, candidate drivers, and Arabic
    clarifying questions for the wizard's "Questioning" phase.
  * ``POST /api/predict/guided/run`` — fit the model with the user's
    answers, persist the result as an artifact (kind ``prediction``,
    payload-discriminated by ``flow="guided"``), and return the full
    result payload so the wizard can render its "Result" phase
    immediately.

Persistence reuses ``models.save_chat_artifact`` so the new flow
shows up in the Predictions tab and the Final Report exactly like the
legacy ``predict_column`` artifacts.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import models  # type: ignore

from ._json import jsonify
from .auth import get_current_user, get_db_session
from .datasets import load_dataset_dataframe
from . import predict_guided_service as svc

router = APIRouter(prefix="/api/predict/guided", tags=["predict-guided"])


class AnalyzeRequest(BaseModel):
    dataset_id: int


class RunRequest(BaseModel):
    dataset_id: int
    target: str
    time_column: str | None = None
    drivers: list[str] = []
    answers: dict[str, Any] = {}
    periods: int = 30
    session_id: int | None = None


def _require_dataset(db, dataset_id: int, user_id: int):
    record = models.get_dataset_record_strict(db, dataset_id, user_id=user_id)
    if not record:
        raise HTTPException(404, "Dataset not found")
    return record


def _artifact_view(a) -> dict:
    return {
        "id": a.id,
        "session_id": a.session_id,
        "project_id": a.project_id,
        "dataset_id": a.dataset_id,
        "kind": a.kind,
        "title": a.title,
        "params": a.params or {},
        "result": a.result or {},
        "pinned": bool(a.pinned),
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


@router.post("/analyze")
async def analyze(
    req: AnalyzeRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record = _require_dataset(db, req.dataset_id, user.id)
    df = load_dataset_dataframe(record)
    payload = svc.analyze_dataset(df)
    payload["dataset_id"] = record.id
    payload["dataset_name"] = record.dataset_name or record.filename
    return jsonify(payload)


@router.post("/run")
async def run(
    req: RunRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    record = _require_dataset(db, req.dataset_id, user.id)
    df = load_dataset_dataframe(record)
    try:
        result = svc.run_prediction(
            df,
            target=req.target,
            time_column=req.time_column,
            drivers=req.drivers or [],
            answers=req.answers or {},
            periods=req.periods,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))

    session_id = req.session_id
    project_id = record.project_id
    if session_id:
        sess = models.get_chat_session(db, session_id, user.id)
        if not sess or sess.project_id != project_id:
            session_id = None

    artifact_view: dict | None = None
    if session_id:
        title = (
            f"تنبؤ — {req.target} · "
            f"{record.dataset_name or record.filename}"
        )
        artifact = models.save_chat_artifact(
            db,
            session_id=session_id,
            user_id=user.id,
            project_id=project_id,
            kind="prediction",
            title=title,
            params={
                "dataset_id": record.id,
                "target": req.target,
                "time_column": req.time_column,
                "drivers": req.drivers,
                "answers": req.answers,
                "flow": svc.GUIDED_FLOW_TAG,
            },
            result=result,
            dataset_id=record.id,
            pinned=True,
        )
        artifact_view = _artifact_view(artifact)

    return jsonify({"result": result, "artifact": artifact_view})
