"""Project routes — list, create, update, delete, switch mode."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
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


def _project_view(p) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "description": p.description,
        "mode": getattr(p, "mode", None),
        "sheet_count": getattr(p, "sheet_count", None),
    }


@router.get("")
async def list_projects(user=Depends(get_current_user), db=Depends(get_db_session)):
    items = models.list_user_projects(db, user.id)
    return items


@router.post("")
async def create_project(req: ProjectCreate, user=Depends(get_current_user), db=Depends(get_db_session)):
    p = models.create_project(db, user_id=user.id, name=req.name, description=req.description)
    if not p:
        raise HTTPException(500, "Could not create project")
    return _project_view(p)


@router.patch("/{project_id}")
async def update_project(project_id: int, req: ProjectUpdate, user=Depends(get_current_user), db=Depends(get_db_session)):
    p = models.update_project(db, project_id=project_id, user_id=user.id, name=req.name, description=req.description)
    if not p:
        raise HTTPException(404, "Project not found")
    if req.mode in ("guided", "expert") and hasattr(p, "mode"):
        p.mode = req.mode
        db.commit()
    return _project_view(p)


@router.delete("/{project_id}")
async def delete_project(project_id: int, user=Depends(get_current_user), db=Depends(get_db_session)):
    ok = models.delete_project(db, project_id=project_id, user_id=user.id)
    if not ok:
        raise HTTPException(404, "Project not found")
    return {"ok": True}
