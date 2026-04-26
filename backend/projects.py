"""Project routes — list, create, update, delete, archive, switch mode."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

import models  # type: ignore

from .auth import get_current_user, get_db_session

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    mode: str | None = None  # "guided" | "expert"


class BulkProjectAction(BaseModel):
    action: Literal["delete", "archive", "restore"]
    project_ids: list[int] = Field(default_factory=list)


def _project_mode(value) -> str | None:
    """Normalize the stored project mode (guided/expert) for the API."""
    if value is None:
        return None
    cleaned = (str(value or "")).strip().lower()
    if cleaned in ("guided", "expert"):
        return cleaned
    return None


def _iso(value) -> str | None:
    """Best-effort ISO8601 for a datetime/None field."""
    if value is None:
        return None
    try:
        return value.isoformat()
    except Exception:
        return None


def _project_view(p, *, archived_at=None) -> dict:
    """Single-row view used by create/update endpoints."""
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "mode": _project_mode(getattr(p, "mode", None)),
        "sheet_count": getattr(p, "sheet_count", None),
        "is_archived": getattr(p, "archived_at", archived_at) is not None,
        "archived_at": _iso(getattr(p, "archived_at", archived_at)),
    }


@router.get("")
async def list_projects(
    include_archived: bool = Query(False),
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    items = models.list_user_projects(
        db, user.id, include_archived=include_archived,
    )
    for it in items:
        for k in ("created_at", "updated_at", "last_opened_at",
                  "last_active_at", "archived_at"):
            it[k] = _iso(it.get(k))
        it["mode"] = _project_mode(it.get("mode"))
    return items


@router.post("")
async def create_project(req: ProjectCreate, user=Depends(get_current_user), db=Depends(get_db_session)):
    p = models.create_project(db, user_id=user.id, name=req.name, description=req.description)
    if not p:
        raise HTTPException(500, "Could not create project")
    return _project_view(p)


@router.post("/bulk")
async def bulk_action(
    req: BulkProjectAction,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Apply the same action to several projects in one round-trip."""
    if not req.project_ids:
        return {"action": req.action, "processed": []}
    try:
        done = models.bulk_project_action(
            db, user.id, req.project_ids, req.action,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"action": req.action, "processed": done}


@router.patch("/{project_id}")
async def update_project(project_id: int, req: ProjectUpdate, user=Depends(get_current_user), db=Depends(get_db_session)):
    if req.name is not None:
        cleaned = req.name.strip()
        if not cleaned:
            raise HTTPException(400, "Project name cannot be empty.")
        # Case-insensitive per-user uniqueness check, ignoring self.
        existing = (
            db.query(models.Project)
              .filter(models.Project.user_id == user.id,
                      models.Project.id != project_id)
              .all()
        )
        for other in existing:
            if (other.name or "").strip().lower() == cleaned.lower():
                raise HTTPException(
                    409, "Another project already uses that name."
                )
        req = ProjectUpdate(
            name=cleaned, description=req.description, mode=req.mode
        )
    p = models.update_project(
        db,
        project_id=project_id,
        user_id=user.id,
        name=req.name,
        description=req.description,
        mode=req.mode,
    )
    if not p:
        raise HTTPException(404, "Project not found")
    return _project_view(p)


@router.delete("/{project_id}")
async def delete_project(project_id: int, user=Depends(get_current_user), db=Depends(get_db_session)):
    ok = models.delete_project(db, project_id=project_id, user_id=user.id)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"ok": True}


@router.post("/{project_id}/archive")
async def archive_project(project_id: int, user=Depends(get_current_user), db=Depends(get_db_session)):
    p = models.archive_project(db, project_id=project_id, user_id=user.id)
    if not p:
        raise HTTPException(404, "Project not found")
    return _project_view(p)


@router.post("/{project_id}/restore")
async def restore_project(project_id: int, user=Depends(get_current_user), db=Depends(get_db_session)):
    p = models.restore_project(db, project_id=project_id, user_id=user.id)
    if not p:
        raise HTTPException(404, "Project not found")
    return _project_view(p)
