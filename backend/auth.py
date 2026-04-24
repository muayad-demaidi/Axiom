"""JWT auth helpers for the AXIOM FastAPI backend.

Wraps the existing ``models.create_user`` / ``models.authenticate_user`` so
PostgreSQL persistence and bcrypt hashing remain the single source of truth.

Security notes:
- ``JWT_SECRET`` is mandatory in production. We refuse to start in
  production if it is missing. In development we fall back to a per-process
  random secret (so tokens are invalidated on every restart) and log a
  loud warning — this avoids the previous foot-gun where a hardcoded
  default could be reused across environments.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

import models  # type: ignore

log = logging.getLogger("axiom.auth")


def _resolve_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET") or os.environ.get("SESSION_SECRET")
    if secret:
        return secret
    env = (os.environ.get("AXIOM_ENV") or os.environ.get("REPLIT_DEPLOYMENT") or "").lower()
    if env in {"prod", "production", "1", "true"}:
        raise RuntimeError(
            "JWT_SECRET (or SESSION_SECRET) must be set when AXIOM_ENV/REPLIT_DEPLOYMENT "
            "indicates production. Refusing to start with a default."
        )
    log.warning(
        "JWT_SECRET is not set; generating a per-process random secret. "
        "Tokens will be invalidated on every restart. Set JWT_SECRET in your environment."
    )
    return secrets.token_urlsafe(48)


JWT_SECRET = _resolve_jwt_secret()
JWT_ALG = "HS256"
JWT_EXP_DAYS = 30

_security = HTTPBearer(auto_error=False)


def issue_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": int(time.time()),
        "exp": int((datetime.utcnow() + timedelta(days=JWT_EXP_DAYS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except JWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {e}")


def get_db_session():
    db = models.get_db()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:
            pass


async def get_current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    db=Depends(get_db_session),
):
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Missing bearer token")
    payload = decode_token(creds.credentials)
    user_id = int(payload["sub"])
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")
    return user


async def get_current_user_optional(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_security),
    db=Depends(get_db_session),
):
    """Same as get_current_user but returns None instead of raising."""
    if not creds or not creds.credentials:
        return None
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload["sub"])
        return db.query(models.User).filter(models.User.id == user_id).first()
    except HTTPException:
        return None
