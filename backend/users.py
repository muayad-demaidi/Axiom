"""User-scoped routes that complement /api/auth/me.

Adds the dedicated locale-update endpoint the frontend expects
(`PATCH /api/users/me/locale`). The legacy `PATCH /api/auth/me` still
works for the bundled assistant_mode + locale update; this route is the
single-purpose contract Settings + MSW handlers + e2e tests already
agree on.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import models  # type: ignore

from .auth import get_current_user, get_db_session
from .auth_routes import _user_view


router = APIRouter(prefix="/api/users", tags=["users"])


class UpdateLocaleRequest(BaseModel):
    locale: str = Field(min_length=2, max_length=8)


@router.patch("/me/locale")
async def update_locale(
    req: UpdateLocaleRequest,
    user=Depends(get_current_user),
    db=Depends(get_db_session),
):
    updated = models.set_user_locale(db, user.id, req.locale)
    if updated is None:
        raise HTTPException(404, "User not found")
    return _user_view(updated)
