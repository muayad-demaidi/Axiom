"""Background queue that rebuilds + redeploys the marketing site.

When a draft is approved we don't want to block the admin UI on a multi-
minute Astro build, and we never want to silently lose an approval if the
build crashes. So approval just appends a row to ``seo_agent_build_jobs``
and a single daemon thread inside the Streamlit process drains the queue:

  1. Pick the oldest job whose ``next_attempt_at`` is due.
  2. Run ``npm run build`` inside ``marketing-site/``.
  3. If ``SEO_AGENT_DEPLOY_HOOK_URL`` is set, POST a small JSON payload to
     it (this is the integration point for Replit Static Deployments or any
     other "redeploy" webhook the operator wires up).
  4. On any failure, bump ``attempts`` and reschedule with exponential
     backoff (1m, 5m, 20m). After ``max_attempts`` the job is marked
     ``failed`` and surfaces in the admin panel for manual retry.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from .config import CONTENT_DIR
from .db import get_session, AgentBuildJob, init_agent_db

SITE_DIR: Path = CONTENT_DIR.parent.parent  # marketing-site/
DEFAULT_BUILD_CMD = "npm run build"
POLL_INTERVAL_SEC = 5
LOG_TAIL_BYTES = 4096
BACKOFF_SCHEDULE = [60, 300, 1200]  # seconds between attempts 1→2, 2→3, 3→…

_worker_started = False
_worker_lock = threading.Lock()


# ---------------------------------------------------------------- public API


def enqueue_build(reason: str, draft_id: Optional[int] = None,
                  max_attempts: int = 3) -> AgentBuildJob:
    """Append a build+deploy job. Coalesces with any pending job for the
    same draft so rapid approvals don't pile up duplicate builds."""
    sess = get_session()
    try:
        if draft_id is not None:
            existing = (sess.query(AgentBuildJob)
                        .filter(AgentBuildJob.draft_id == draft_id,
                                AgentBuildJob.status.in_(("queued", "running")))
                        .first())
            if existing:
                return existing
        job = AgentBuildJob(
            draft_id=draft_id, reason=reason, status="queued",
            attempts=0, max_attempts=max_attempts,
            queued_at=datetime.utcnow(),
            next_attempt_at=datetime.utcnow(),
        )
        sess.add(job)
        sess.commit()
        sess.refresh(job)
        # Detach so callers can read attributes after the session closes.
        sess.expunge(job)
        ensure_worker_running()
        return job
    finally:
        sess.close()


def list_build_jobs(limit: int = 20) -> List[AgentBuildJob]:
    sess = get_session()
    try:
        return (sess.query(AgentBuildJob)
                .order_by(AgentBuildJob.queued_at.desc())
                .limit(limit).all())
    finally:
        sess.close()


def retry_build_job(job_id: int) -> bool:
    sess = get_session()
    try:
        j = sess.query(AgentBuildJob).filter(AgentBuildJob.id == job_id).first()
        if not j:
            return False
        j.status = "queued"
        j.attempts = 0
        j.next_attempt_at = datetime.utcnow()
        j.error = None
        sess.commit()
        ensure_worker_running()
        return True
    finally:
        sess.close()


def ensure_worker_running() -> None:
    """Start the background drainer if it isn't already. Safe to call
    repeatedly from any thread / Streamlit rerun."""
    global _worker_started
    if _worker_started:
        return
    with _worker_lock:
        if _worker_started:
            return
        if os.environ.get("SEO_AGENT_DISABLE_BUILD_WORKER"):
            _worker_started = True  # pretend, so we stop trying
            return
        init_agent_db()
        t = threading.Thread(target=_worker_loop, name="seo-build-worker",
                             daemon=True)
        t.start()
        _worker_started = True


# ---------------------------------------------------------------- internals


def _worker_loop() -> None:
    while True:
        try:
            job_id = _claim_next_job()
            if job_id is None:
                time.sleep(POLL_INTERVAL_SEC)
                continue
            _run_job(job_id)
        except Exception as ex:  # never let the daemon die
            try:
                import logging
                logging.getLogger(__name__).exception("build worker tick failed: %s", ex)
            except Exception:
                pass
            time.sleep(POLL_INTERVAL_SEC)


def _claim_next_job() -> Optional[int]:
    """Atomically move the oldest due queued job to ``running``."""
    sess = get_session()
    try:
        now = datetime.utcnow()
        j = (sess.query(AgentBuildJob)
             .filter(AgentBuildJob.status == "queued")
             .filter((AgentBuildJob.next_attempt_at.is_(None))
                     | (AgentBuildJob.next_attempt_at <= now))
             .order_by(AgentBuildJob.queued_at.asc())
             .with_for_update(skip_locked=True)
             .first())
        if not j:
            return None
        j.status = "running"
        j.started_at = now
        j.attempts = (j.attempts or 0) + 1
        sess.commit()
        return j.id
    except Exception:
        sess.rollback()
        # Postgres SKIP LOCKED unsupported? fall back to non-locking claim
        # (still honoring next_attempt_at so backoff is respected).
        try:
            now2 = datetime.utcnow()
            j = (sess.query(AgentBuildJob)
                 .filter(AgentBuildJob.status == "queued")
                 .filter((AgentBuildJob.next_attempt_at.is_(None))
                         | (AgentBuildJob.next_attempt_at <= now2))
                 .order_by(AgentBuildJob.queued_at.asc())
                 .first())
            if not j:
                return None
            j.status = "running"
            j.started_at = datetime.utcnow()
            j.attempts = (j.attempts or 0) + 1
            sess.commit()
            return j.id
        except Exception:
            sess.rollback()
            return None
    finally:
        sess.close()


def _run_job(job_id: int) -> None:
    build_cmd = os.environ.get("SEO_AGENT_BUILD_CMD", DEFAULT_BUILD_CMD)
    deploy_url = os.environ.get("SEO_AGENT_DEPLOY_HOOK_URL", "").strip()
    log_chunks: List[str] = []

    if not build_cmd.strip():
        _finish(job_id, build_ok=True, deploy_ok=True,
                deploy_target="skipped", log_tail="(SEO_AGENT_BUILD_CMD empty — skipped)",
                error=None, success=True)
        return

    # 1. Build
    build_ok = False
    try:
        proc = subprocess.run(
            build_cmd, shell=True, cwd=str(SITE_DIR), timeout=900,
            capture_output=True, text=True,
        )
        log_chunks.append(f"$ {build_cmd}\n{proc.stdout}\n{proc.stderr}")
        build_ok = proc.returncode == 0
        if not build_ok:
            _maybe_retry(job_id, build_ok=False, deploy_ok=None,
                         deploy_target=deploy_url or "build-only",
                         log_tail=_tail("\n".join(log_chunks)),
                         error=f"build exited {proc.returncode}")
            return
    except subprocess.TimeoutExpired:
        _maybe_retry(job_id, build_ok=False, deploy_ok=None,
                     deploy_target=deploy_url or "build-only",
                     log_tail=_tail("\n".join(log_chunks) + "\nTIMEOUT"),
                     error="build timed out after 900s")
        return
    except Exception as ex:
        _maybe_retry(job_id, build_ok=False, deploy_ok=None,
                     deploy_target=deploy_url or "build-only",
                     log_tail=_tail("\n".join(log_chunks)),
                     error=f"build crashed: {ex}")
        return

    # 2. Deploy (optional webhook)
    deploy_ok: Optional[bool] = None
    if deploy_url:
        try:
            import json as _json
            import urllib.request

            payload = _json.dumps({
                "event": "marketing_site_rebuilt",
                "job_id": job_id,
                "at": datetime.utcnow().isoformat() + "Z",
            }).encode("utf-8")
            req = urllib.request.Request(
                deploy_url, data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            token = os.environ.get("SEO_AGENT_DEPLOY_HOOK_TOKEN", "").strip()
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read(2048).decode("utf-8", errors="replace")
                log_chunks.append(f"\nPOST {deploy_url} → {resp.status}\n{body}")
                deploy_ok = 200 <= resp.status < 300
        except Exception as ex:
            log_chunks.append(f"\nPOST {deploy_url} failed: {ex}")
            _maybe_retry(job_id, build_ok=True, deploy_ok=False,
                         deploy_target=deploy_url,
                         log_tail=_tail("\n".join(log_chunks)),
                         error=f"deploy hook failed: {ex}")
            return
        if not deploy_ok:
            _maybe_retry(job_id, build_ok=True, deploy_ok=False,
                         deploy_target=deploy_url,
                         log_tail=_tail("\n".join(log_chunks)),
                         error="deploy hook returned non-2xx")
            return
    else:
        # No webhook configured. By default we treat this as an
        # incomplete deploy: status `success` is reserved for cases
        # where the new content is provably live in production. The
        # job is parked in `needs_publish` so the admin sees a clear
        # signal and can either wire a hook or confirm the manual
        # republish via `confirm_publish`. For live-file deployment
        # models where rebuilding dist/ IS the publish (Reserved VM,
        # dev preview), set SEO_AGENT_ALLOW_BUILD_ONLY=1 to make the
        # job complete as `success` with deploy_target=`build-only`.
        if os.environ.get("SEO_AGENT_ALLOW_BUILD_ONLY", "").lower() in ("1", "true", "yes"):
            log_chunks.append(
                "\nBuild OK. SEO_AGENT_ALLOW_BUILD_ONLY=1 → treating "
                "the refreshed dist/ as the publish (Reserved VM / dev "
                "preview / any live-file deployment)."
            )
            deploy_ok = True
        else:
            log_chunks.append(
                "\nBuild OK but no SEO_AGENT_DEPLOY_HOOK_URL is "
                "configured. Job parked in needs_publish — set the hook "
                "to automate redeploy, or republish the marketing site "
                "manually and mark this job published. (Set "
                "SEO_AGENT_ALLOW_BUILD_ONLY=1 if your deployment serves "
                "dist/ live and no separate publish is required.)"
            )
            _finish_needs_publish(job_id, log_tail=_tail("\n".join(log_chunks)))
            return

    _finish(job_id, build_ok=True, deploy_ok=deploy_ok,
            deploy_target=deploy_url or "build-only",
            log_tail=_tail("\n".join(log_chunks)), error=None, success=True)


def _tail(s: str) -> str:
    if not s:
        return s
    if len(s) <= LOG_TAIL_BYTES:
        return s
    return "…(truncated)…\n" + s[-LOG_TAIL_BYTES:]


def _finish_needs_publish(job_id: int, *, log_tail: Optional[str]) -> None:
    """Build succeeded but no automated redeploy is configured. Park the
    job so an operator can confirm the manual republish."""
    sess = get_session()
    try:
        j = sess.query(AgentBuildJob).filter(AgentBuildJob.id == job_id).first()
        if not j:
            return
        j.status = "needs_publish"
        j.finished_at = datetime.utcnow()
        j.build_ok = True
        j.deploy_ok = False
        j.deploy_target = "manual-publish"
        j.log_tail = log_tail
        j.error = "Build OK; awaiting manual republish (no SEO_AGENT_DEPLOY_HOOK_URL)"
        j.next_attempt_at = None
        sess.commit()
    finally:
        sess.close()


def confirm_publish(job_id: int, reviewer: str) -> bool:
    """Operator marks a ``needs_publish`` job as published after manually
    redeploying the marketing site."""
    sess = get_session()
    try:
        j = sess.query(AgentBuildJob).filter(AgentBuildJob.id == job_id).first()
        if not j or j.status != "needs_publish":
            return False
        j.status = "success"
        j.deploy_ok = True
        j.deploy_target = f"manual-publish:{reviewer}"
        j.error = None
        sess.commit()
        return True
    finally:
        sess.close()


def _finish(job_id: int, *, build_ok: bool, deploy_ok: Optional[bool],
            deploy_target: str, log_tail: Optional[str], error: Optional[str],
            success: bool) -> None:
    sess = get_session()
    try:
        j = sess.query(AgentBuildJob).filter(AgentBuildJob.id == job_id).first()
        if not j:
            return
        j.status = "success" if success else "failed"
        j.finished_at = datetime.utcnow()
        j.build_ok = build_ok
        j.deploy_ok = deploy_ok
        j.deploy_target = deploy_target
        j.log_tail = log_tail
        j.error = error
        j.next_attempt_at = None
        sess.commit()
    finally:
        sess.close()


def _maybe_retry(job_id: int, *, build_ok: bool, deploy_ok: Optional[bool],
                 deploy_target: str, log_tail: Optional[str],
                 error: Optional[str]) -> None:
    sess = get_session()
    try:
        j = sess.query(AgentBuildJob).filter(AgentBuildJob.id == job_id).first()
        if not j:
            return
        j.build_ok = build_ok
        j.deploy_ok = deploy_ok
        j.deploy_target = deploy_target
        j.log_tail = log_tail
        j.error = error
        j.finished_at = datetime.utcnow()
        if (j.attempts or 0) >= (j.max_attempts or 3):
            j.status = "failed"
            j.next_attempt_at = None
        else:
            idx = min((j.attempts or 1) - 1, len(BACKOFF_SCHEDULE) - 1)
            delay = BACKOFF_SCHEDULE[idx]
            j.status = "queued"
            j.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay)
        sess.commit()
    finally:
        sess.close()
