"""Resolve the effective Guided/Expert mode for a request.

Today every backend endpoint outside ``POST /api/chat/stream`` is
mode-blind, and the only place that resolved the effective Guided/
Expert mode was a 24-line block inside :mod:`backend.chat`. Subsequent
features (predictions engine, recommendations, joins, daily pulse,
expert features) all need to know the active mode, and we don't want
each of them re-implementing the four-step priority logic.

This module centralises that logic so any router can call
:func:`resolve_mode` directly or grab a FastAPI dependency from
:func:`mode_dependency`.

Resolution priority (first non-empty wins):

  1. **Per-project override** — ``projects.mode`` (when ``project_id``
     is supplied and the project belongs to the caller).
  2. **Request-supplied mode** — e.g. the chat stream request body's
     ``assistant_mode`` field.
  3. **User preference** — ``users.assistant_mode`` (legacy storage
     uses ``"simple"`` as an alias for ``"guided"``).
  4. **Default** — ``"guided"`` so first-time users land in Guided per
     the product spec.

Input normalisation matches the legacy chat behaviour:

  * ``"simple"`` (the legacy DB alias) maps to ``"guided"``.
  * Case and surrounding whitespace are tolerated.
  * Anything outside ``{guided, expert, simple}`` is ignored at that
    priority level — the resolver falls through to the next layer
    instead of returning a garbage value.

The function always returns the literal string ``"guided"`` or
``"expert"``.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import Depends, Request

import models  # type: ignore

from .auth import get_current_user, get_db_session


_VALID_API_MODES = ("guided", "expert")


def _normalize(value: Any) -> Optional[str]:
    """Coerce a raw mode value to ``"guided"`` / ``"expert"`` or None.

    ``"simple"`` is the legacy DB alias for ``"guided"`` and is kept
    intentionally so we don't have to migrate ``users.assistant_mode``.
    Empty / unknown values return ``None`` so the caller can fall
    through to the next priority level.
    """
    if value is None:
        return None
    cleaned = str(value).strip().lower()
    if not cleaned:
        return None
    if cleaned in ("guided", "simple"):
        return "guided"
    if cleaned == "expert":
        return "expert"
    return None


def resolve_mode(
    db,
    user,
    project_id: Optional[int] = None,
    request_mode: Optional[str] = None,
) -> str:
    """Resolve the effective Guided/Expert mode for a request.

    Parameters
    ----------
    db
        Active SQLAlchemy session — used only to look up the project
        when ``project_id`` is supplied.
    user
        Authenticated user object (or ``None``). Must expose the
        ``id`` and ``assistant_mode`` attributes when present.
    project_id
        Optional project id. When set, the project's ``mode`` column
        wins over every other layer.
    request_mode
        Optional caller-supplied override (e.g. the chat stream's
        ``assistant_mode`` field).

    Returns
    -------
    str
        Either ``"guided"`` or ``"expert"`` — never ``None``.
    """
    # 1. Per-project override. ``models.get_project`` already returns
    # None for both "missing" and "owned by someone else", so we don't
    # need a broad try/except here — we want real DB/auth errors to
    # surface instead of being silently swallowed into the default.
    if project_id is not None and user is not None:
        proj = models.get_project(db, project_id, getattr(user, "id", None))
        if proj is not None:
            mode = _normalize(getattr(proj, "mode", None))
            if mode is not None:
                return mode

    # 2. Caller-supplied request override.
    mode = _normalize(request_mode)
    if mode is not None:
        return mode

    # 3. User-level preference.
    if user is not None:
        mode = _normalize(getattr(user, "assistant_mode", None))
        if mode is not None:
            return mode

    # 4. Default per product spec.
    return "guided"


def mode_dependency(
    request_mode_field: Optional[str] = None,
) -> Callable[..., str]:
    """Build a FastAPI dependency that returns the resolved mode.

    Routers can use this to get a ``str`` of ``"guided"`` / ``"expert"``
    without writing the resolution logic themselves::

        @router.get("/something")
        async def handler(
            project_id: int,
            mode: str = Depends(mode_dependency()),
        ):
            ...

    The dependency reads ``project_id`` from path or query parameters
    automatically (FastAPI populates ``request.path_params`` and
    ``request.query_params``). When ``request_mode_field`` is supplied,
    the dependency also peeks at the request body for that field name
    and uses it as the request-level override — useful when an existing
    Pydantic body already carries an ``assistant_mode`` string.

    Parameters
    ----------
    request_mode_field
        Optional name of a body field (e.g. ``"assistant_mode"``) that
        should be honoured as the request-level mode override. When the
        body cannot be parsed as JSON, the field is silently ignored
        and we fall through to the user / default layers.
    """

    async def _dep(
        request: Request,
        user=Depends(get_current_user),
        db=Depends(get_db_session),
    ) -> str:
        # Pull project_id from path or query params (FastAPI fills both
        # when present). We accept either an int or the stringified
        # version FastAPI hands us; anything we can't parse falls back
        # to None which simply skips the per-project layer.
        project_id: Optional[int] = None
        raw_pid = (
            request.path_params.get("project_id")
            if hasattr(request, "path_params")
            else None
        )
        if raw_pid is None:
            raw_pid = request.query_params.get("project_id")
        if raw_pid is not None:
            try:
                project_id = int(raw_pid)
            except (TypeError, ValueError):
                project_id = None

        # Optionally peek at the JSON body for an explicit mode override.
        request_mode: Optional[str] = None
        if request_mode_field:
            try:
                body = await request.json()
                if isinstance(body, dict):
                    val = body.get(request_mode_field)
                    if isinstance(val, str):
                        request_mode = val
            except Exception:
                request_mode = None

        return resolve_mode(
            db, user, project_id=project_id, request_mode=request_mode
        )

    return _dep


__all__ = ["resolve_mode", "mode_dependency"]
