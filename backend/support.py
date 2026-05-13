"""Support routes — contact form submission.

Persists the inbound message to PostgreSQL via `models.save_support_message`
and best-effort relays it to the support inbox via Resend
(`email_service.send_support_notification`). Email failures do not fail the
request — the message is still durably stored.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

import models  # type: ignore

from .auth import get_current_admin, get_db_session

router = APIRouter(prefix="/api/support", tags=["support"])
log = logging.getLogger("axiom.support")


class ContactRequest(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(
        max_length=254,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )
    message: str = Field(max_length=5000)

    # Trim-then-validate so whitespace-only payloads (e.g. "    ") cannot
    # pass `min_length` checks and end up persisted as empty strings.
    @field_validator("name", "email", "message", mode="before")
    @classmethod
    def _strip(cls, v):
        return v.strip() if isinstance(v, str) else v

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("message")
    @classmethod
    def _message_minlen(cls, v: str) -> str:
        if len(v) < 5:
            raise ValueError("Message must be at least 5 characters")
        return v


@router.post("/contact")
async def contact(req: ContactRequest, db=Depends(get_db_session)):
    name = req.name
    email = req.email
    message = req.message

    try:
        record = models.save_support_message(db, email, name, message)
    except Exception as exc:
        log.exception("Failed to persist support message: %s", exc)
        raise HTTPException(500, "Could not save your message — please try again")

    email_sent = False
    try:
        from email_service import send_support_notification  # type: ignore

        email_sent = bool(send_support_notification(email, name, message))
    except Exception as exc:  # pragma: no cover - best effort
        log.warning("Support notification email failed: %s", exc)

    return {
        "ok": True,
        "id": getattr(record, "id", None),
        "email_sent": email_sent,
    }


def _serialize_message(msg) -> dict:
    return {
        "id": msg.id,
        "name": msg.name,
        "email": msg.email,
        "message": msg.message,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
        "handled": bool(msg.is_read),
    }


@router.get("/messages")
async def list_messages(
    only_unhandled: bool = Query(False, description="Only return un-handled messages"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _admin=Depends(get_current_admin),
    db=Depends(get_db_session),
):
    """List contact-form submissions for the in-app admin queue.

    Newest-first. Admin only — non-admins receive 403, unauthenticated
    callers receive 401 (handled by the dependency chain).

    Pagination: pass ``offset`` to walk further into the queue; ``total``
    in the response is the unpaginated count (respecting ``only_unhandled``)
    so the UI can show "showing N of M" and a Load-more affordance.
    """
    rows, total = models.list_support_messages(
        db, only_unhandled=only_unhandled, limit=limit, offset=offset
    )
    return {
        "messages": [_serialize_message(m) for m in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


class UpdateMessageRequest(BaseModel):
    handled: bool


@router.patch("/messages/{message_id}")
async def update_message(
    message_id: int,
    req: UpdateMessageRequest,
    _admin=Depends(get_current_admin),
    db=Depends(get_db_session),
):
    """Mark a support message handled (or un-handled).

    Reuses the existing ``is_read`` column on ``SupportMessage`` as the
    queue status flag — no schema change needed.
    """
    msg = models.set_support_message_handled(db, message_id, req.handled)
    if msg is None:
        raise HTTPException(404, "Support message not found")
    return _serialize_message(msg)
