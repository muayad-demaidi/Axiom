"""Chat session routes — multi-conversation history per project.

Each project owns N chat sessions. The model still gets the whole
project's data context (all datasets) on every turn so the
conversations stay project-aware while remaining independent threads.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import models  # type: ignore

from .auth import get_current_user, get_db_session

router = APIRouter(tags=["chats"])


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)


class ChatSessionUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=255)


def _session_view(s) -> dict:
    return {
        "id": s.id,
        "project_id": s.project_id,
        "title": s.title,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
    }


def _message_view(m) -> dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "user_message": m.user_message,
        "ai_response": m.ai_response,
        "timestamp": m.timestamp.isoformat() if m.timestamp else None,
    }


@router.get("/api/projects/{project_id}/chats")
async def list_project_chats(
    project_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    proj = models.get_project(db, project_id, user.id)
    if not proj:
        raise HTTPException(404, "Project not found")
    sessions = models.list_chat_sessions(db, project_id, user.id)
    return [_session_view(s) for s in sessions]


@router.post("/api/projects/{project_id}/chats")
async def create_project_chat(
    project_id: int,
    req: ChatSessionCreate,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    sess = models.create_chat_session(
        db, project_id=project_id, user_id=user.id,
        title=(req.title or "New chat").strip() or "New chat",
    )
    if not sess:
        raise HTTPException(404, "Project not found")
    return _session_view(sess)


@router.get("/api/chats/{session_id}/messages")
async def get_chat_messages(
    session_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    sess = models.get_chat_session(db, session_id, user.id)
    if not sess:
        raise HTTPException(404, "Chat not found")
    msgs = models.get_session_messages(db, session_id)
    return {
        "session": _session_view(sess),
        "messages": [_message_view(m) for m in msgs],
    }


@router.patch("/api/chats/{session_id}")
async def rename_chat(
    session_id: int,
    req: ChatSessionUpdate,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    sess = models.rename_chat_session(db, session_id, user.id, req.title.strip())
    if not sess:
        raise HTTPException(404, "Chat not found")
    return _session_view(sess)


@router.delete("/api/chats/{session_id}")
async def delete_chat(
    session_id: int,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    ok = models.delete_chat_session(db, session_id, user.id)
    if not ok:
        raise HTTPException(404, "Chat not found")
    return {"ok": True}
