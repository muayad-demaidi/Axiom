"""Auth routes: register, login, current user, forgot/reset password."""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

import models  # type: ignore

from .auth import get_current_user, get_db_session, issue_token

router = APIRouter(prefix="/api/auth", tags=["auth"])
log = logging.getLogger("axiom.auth_routes")


def _strip_str(value):
    """Pydantic pre-validator: trim leading/trailing whitespace.

    Applied to identifier fields so direct API callers (curl, mobile
    autocomplete) don't get a 422 from the strict email regex just
    because of a trailing space iOS Safari pasted in.
    """
    if isinstance(value, str):
        return value.strip()
    return value


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    full_name: str | None = None

    @field_validator("email", "username", mode="before")
    @classmethod
    def _trim_identifier(cls, v):
        return _strip_str(v)


class LoginRequest(BaseModel):
    email_or_username: str
    password: str

    @field_validator("email_or_username", mode="before")
    @classmethod
    def _trim_identifier(cls, v):
        return _strip_str(v)


class TokenResponse(BaseModel):
    token: str
    user: dict


def _api_mode(stored: str | None) -> str:
    """Translate the DB-stored assistant_mode to the API/UI vocabulary.

    The legacy storage value ``"simple"`` is the same thing as the new
    ``"guided"`` label; everything else falls through unchanged. We
    default to ``"guided"`` so first-time users land in Guided per the
    product spec.
    """
    cleaned = (str(stored or "")).strip().lower()
    if cleaned == "expert":
        return "expert"
    return "guided"


def _api_locale(stored: str | None) -> str:
    """Coerce the DB-stored locale to one of the supported values.

    Defaults to ``"en"`` so brand-new accounts (or rows from older
    deployments without the column) hit the English catalogue first.
    """
    cleaned = (str(stored or "")).strip().lower()
    if cleaned == "ar":
        return "ar"
    return "en"


def _user_view(user) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "subscription_type": getattr(user, "subscription_type", None),
        "trial_end": str(user.trial_end) if getattr(user, "trial_end", None) else None,
        "assistant_mode": _api_mode(getattr(user, "assistant_mode", None)),
        "locale": _api_locale(getattr(user, "locale", None)),
        "is_admin": bool(getattr(user, "is_admin", False)),
    }


class UpdateMeRequest(BaseModel):
    assistant_mode: str | None = Field(default=None, max_length=16)
    locale: str | None = Field(default=None, max_length=8)


@router.post("/register", response_model=TokenResponse)
async def register(req: RegisterRequest, db=Depends(get_db_session)):
    from sqlalchemy import func
    canonical_email = models.normalize_identifier(req.email)
    canonical_username = models.normalize_identifier(req.username)
    existing = db.query(models.User).filter(
        (func.lower(models.User.email) == canonical_email)
        | (func.lower(models.User.username) == canonical_username)
    ).first()
    if existing:
        raise HTTPException(409, "User with this email or username already exists")
    user = models.create_user(
        db, email=req.email, username=req.username, password=req.password, full_name=req.full_name
    )
    if not user:
        raise HTTPException(500, "Could not create user")
    # Best-effort welcome email (no-op if RESEND_API_KEY isn't set). Never
    # let an email hiccup fail the signup the user just completed.
    try:
        from email_service import send_welcome_email  # type: ignore
        send_welcome_email(user.email, user.username, getattr(user, "trial_end", None))
    except Exception as exc:  # pragma: no cover - best effort
        log.warning("welcome email skipped: %s", exc)
    return {"token": issue_token(user.id, user.email), "user": _user_view(user)}


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db=Depends(get_db_session)):
    user = models.authenticate_user(db, req.email_or_username, req.password)
    if not user:
        raise HTTPException(401, "Invalid credentials")
    return {"token": issue_token(user.id, user.email), "user": _user_view(user)}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return _user_view(user)


@router.patch("/me")
async def update_me(
    req: UpdateMeRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    """Update mutable fields on the current user (currently just the
    Guided/Expert assistant mode preference).

    The ``assistant_mode`` field accepts the API vocabulary
    (``"guided"`` / ``"expert"``); the helper translates ``"guided"`` back
    to the legacy ``"simple"`` storage value.
    """
    if req.assistant_mode is not None:
        updated = models.set_user_assistant_mode(db, user.id, req.assistant_mode)
        if updated is None:
            raise HTTPException(404, "User not found")
        user = updated
    if req.locale is not None:
        updated = models.set_user_locale(db, user.id, req.locale)
        if updated is None:
            raise HTTPException(404, "User not found")
        user = updated
    return _user_view(user)


class ForgotRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    @field_validator("email", mode="before")
    @classmethod
    def _trim_identifier(cls, v):
        return _strip_str(v)


class ResetRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    new_password: str = Field(min_length=6, max_length=128)


def _send_reset_email(email: str, raw_token: str) -> None:
    """Best-effort delivery via Resend; never raise upstream.

    The /forgot endpoint always returns 200 to avoid leaking which emails
    are registered, so failures here are logged and swallowed.
    """
    public_url = os.environ.get("PUBLIC_APP_URL", "http://localhost:5000")
    reset_url = f"{public_url.rstrip('/')}/reset-password?token={raw_token}"
    try:
        import resend  # type: ignore

        api_key = os.environ.get("RESEND_API_KEY")
        if not api_key:
            log.warning("RESEND_API_KEY not set; reset link for %s: %s", email, reset_url)
            return
        resend.api_key = api_key
        resend.Emails.send({
            "from": os.environ.get("RESEND_FROM", "AXIOM <onboarding@resend.dev>"),
            "to": [email],
            "subject": "Reset your AXIOM password",
            "html": (
                f"<p>Hi,</p>"
                f"<p>You requested a password reset. This link expires in 1 hour:</p>"
                f"<p><a href=\"{reset_url}\">{reset_url}</a></p>"
                f"<p>If you didn't request this, you can safely ignore this email.</p>"
            ),
        })
    except Exception as exc:  # pragma: no cover - best effort
        log.warning("Reset email delivery failed for %s: %s", email, exc)


@router.post("/forgot")
async def forgot_password(req: ForgotRequest, db=Depends(get_db_session)):
    from sqlalchemy import func
    needle = models.normalize_identifier(req.email)
    user = (
        db.query(models.User)
          .filter(func.lower(models.User.email) == needle)
          .first()
        if needle else None
    )
    if user:
        raw_token = models.create_password_reset_token(db, user)
        if raw_token:
            _send_reset_email(user.email, raw_token)
    # Always return 200 — don't leak account existence.
    return {"ok": True}


@router.post("/reset")
async def reset_password(req: ResetRequest, db=Depends(get_db_session)):
    token, _user = models.get_valid_password_reset_token(db, req.token)
    if not token:
        raise HTTPException(400, "Invalid or expired reset token")
    user = models.consume_password_reset_token(db, token, req.new_password)
    if not user:
        raise HTTPException(400, "Could not reset password")
    return {"token": issue_token(user.id, user.email), "user": _user_view(user)}
