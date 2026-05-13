"""Passive notifications surfaced after background pipelines (Task #260).

Currently the only writer is :func:`backend.cross_predict.discover_relationships_after_upload`,
which posts a single ``UploadNotification`` whenever an upload's
post-sweep auto-persists at least one high-confidence cross-dataset
join. The frontend polls ``GET /api/projects/{project_id}/upload-notifications``
right after an upload to surface a passive toast/inbox card linking
into the data-model drawer with the new relationship highlighted.

A notification is "active" until the user dismisses it; the dismiss
endpoint stamps ``dismissed_at`` so the polled list naturally hides it
on the next refresh without losing the audit trail.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

import models  # type: ignore

from ._json import jsonify
from .auth import get_current_user, get_db_session


router = APIRouter(tags=["notifications"])


def _require_project(db, project_id: int, user_id: int) -> models.Project:
    """Reject access to projects the caller does not own."""
    proj = (
        db.query(models.Project)
        .filter(models.Project.id == project_id,
                models.Project.user_id == user_id)
        .first()
    )
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


def _serialize(n: models.UploadNotification) -> dict:
    return {
        "id": int(n.id),
        "project_id": int(n.project_id),
        "kind": n.kind,
        "summary": n.summary,
        "payload": n.payload or {},
        "dismissed": n.dismissed_at is not None,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


@router.get("/api/projects/{project_id}/upload-notifications")
def list_upload_notifications(
    project_id: int,
    include_dismissed: bool = False,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """List notifications for a project, newest-first.

    By default returns only active (non-dismissed) rows so the upload
    page and workspace banner show a clean inbox. Pass
    ``include_dismissed=true`` for the full history.
    """
    _require_project(db, project_id, user.id)
    q = (
        db.query(models.UploadNotification)
        .filter(models.UploadNotification.project_id == project_id,
                models.UploadNotification.user_id == user.id)
    )
    if not include_dismissed:
        q = q.filter(models.UploadNotification.dismissed_at.is_(None))
    rows = q.order_by(models.UploadNotification.created_at.desc(),
                      models.UploadNotification.id.desc()).all()
    return jsonify({"items": [_serialize(n) for n in rows]})


@router.post(
    "/api/projects/{project_id}/upload-notifications/{notification_id}/dismiss"
)
def dismiss_upload_notification(
    project_id: int,
    notification_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Stamp a notification as dismissed.

    Idempotent: re-dismissing an already-dismissed row is a no-op and
    still returns the serialised notification so the frontend can keep
    its local state in sync.
    """
    _require_project(db, project_id, user.id)
    n = (
        db.query(models.UploadNotification)
        .filter(models.UploadNotification.id == notification_id,
                models.UploadNotification.project_id == project_id,
                models.UploadNotification.user_id == user.id)
        .first()
    )
    if not n:
        raise HTTPException(status_code=404, detail="Notification not found")
    if n.dismissed_at is None:
        n.dismissed_at = datetime.utcnow()
        db.commit()
        db.refresh(n)
    return jsonify(_serialize(n))
