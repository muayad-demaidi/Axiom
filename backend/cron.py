"""Scheduled-job HTTP endpoints, triggered by an external cron.

The Render free tier spins the web service down when idle, so the
in-process APScheduler can't be relied on to fire. Instead an external
scheduler (a GitHub Actions weekly workflow) hits these endpoints, which
are guarded by a shared secret (``PULSE_CRON_SECRET``) rather than a user
JWT. Everything degrades to a safe no-op when the secret or the Resend
key is absent, so this is dormant until the owner wires both.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException

import models  # type: ignore

from . import scheduler as _sched

router = APIRouter(prefix="/api/cron", tags=["cron"])
log = logging.getLogger("axiom.cron")

# Cap per run so a misfire can never fan out into a mass send.
MAX_EMAILS_PER_RUN = 50


def _authorized(secret: str | None) -> bool:
    expected = os.environ.get("PULSE_CRON_SECRET")
    return bool(expected) and secret == expected


@router.post("/weekly-pulse")
async def weekly_pulse(x_cron_secret: str | None = Header(default=None)):
    """Email each active user a Pulse digest for their most-relevant project.

    Auth: the ``X-Cron-Secret`` header must match ``PULSE_CRON_SECRET``.
    One email per user per run (deduped), capped at ``MAX_EMAILS_PER_RUN``.
    """
    if not _authorized(x_cron_secret):
        raise HTTPException(401, "unauthorized")

    from email_service import send_pulse_email  # type: ignore

    db = models.get_db()
    sent = 0
    skipped = 0
    errors = 0
    emailed_users: set[int] = set()
    try:
        try:
            project_ids = _sched._list_active_project_ids(db)
        except Exception as exc:
            log.warning("could not list active projects: %s", exc)
            project_ids = []

        for pid in project_ids:
            if sent >= MAX_EMAILS_PER_RUN:
                break
            project = (
                db.query(models.Project).filter(models.Project.id == pid).first()
            )
            if project is None or project.user_id in emailed_users:
                continue
            user = (
                db.query(models.User).filter(models.User.id == project.user_id).first()
            )
            if not user or not user.email:
                continue
            try:
                payload = _sched.build_pulse_snapshot(db, pid)
            except Exception:
                skipped += 1
                continue
            ok = send_pulse_email(
                user.email, user.username or "there",
                project.name or "your project", payload,
            )
            if ok:
                emailed_users.add(project.user_id)
                sent += 1
            else:
                errors += 1
    finally:
        try:
            db.close()
        except Exception:
            pass

    return {"ok": True, "sent": sent, "skipped": skipped, "errors": errors}
