"""Daily Pulse HTTP surface (Task #248).

Single read endpoint that returns the most recent persisted snapshot
for a project. When no snapshot exists yet (e.g. the cron hasn't run
since the project was created), we synthesise one synchronously so
the first load is never a 404.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

import models  # type: ignore

from . import scheduler as sched
from .auth import get_current_user, get_db_session

router = APIRouter(tags=["daily-pulse"])


def _envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the strict daily-pulse response shape.

    The contract is fixed at five keys — ``generated_at``,
    ``top_changes``, ``anomalies``, ``predictions``,
    ``recommendations`` — so frontend consumers can rely on the same
    schema regardless of whether the snapshot was served from cache
    or built on demand. Additional snapshot context (date, dataset
    metadata, full profile) lives inside the predictions/anomalies
    payloads or in the persisted ``snapshot_json`` for callers that
    need it.
    """
    return {
        "generated_at": payload.get("generated_at"),
        "top_changes": payload.get("top_changes") or [],
        "anomalies": payload.get("anomalies") or [],
        "predictions": payload.get("predictions") or {},
        "recommendations": payload.get("recommendations") or [],
    }


@router.get("/api/projects/{project_id}/daily-pulse")
async def get_daily_pulse(
    project_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Return the most recent Daily Pulse snapshot for a project.

    When no snapshot exists yet, synthesise one synchronously so the
    first request never 404s. The endpoint is read-only beyond that
    one bootstrap path — the heavy lifting normally happens on the
    nightly schedule.
    """
    project = models.get_project(db, project_id, user.id)
    if project is None:
        raise HTTPException(404, "Project not found")

    row = sched.latest_snapshot(db, project_id)
    if row is not None:
        payload = row.snapshot_json or {}
        return _envelope(payload)

    try:
        payload = sched.build_pulse_snapshot(db, project_id)
    except sched.SkipProject as exc:
        raise HTTPException(
            409,
            f"Daily Pulse cannot run yet for this project: {exc}",
        )
    return _envelope(payload)
