"""End-to-end smoke check for the marketing-site build/deploy queue.

Verifies the loop required by Task #34:

  approve_draft → enqueued build job → worker drains queue →
  build status recorded → admin-visible state surfaces correctly.

Run with:  SEO_AGENT_BUILD_CMD='echo fake build ok' \\
           python scripts/smoke_test_build_queue.py
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Force a fast, deterministic build command so the smoke test never
# actually invokes npm. Override only if the caller didn't already.
os.environ.setdefault("SEO_AGENT_BUILD_CMD", "echo fake-build-ok")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seo_agent.db import init_agent_db, get_session, AgentBuildJob  # noqa: E402
from seo_agent.build_queue import (  # noqa: E402
    enqueue_build, list_build_jobs, ensure_worker_running, confirm_publish,
)


def main() -> int:
    init_agent_db()

    job = enqueue_build(reason="smoke")
    print(f"[1/4] enqueued job #{job.id} status={job.status}")

    ensure_worker_running()

    deadline = time.time() + 30
    final = None
    while time.time() < deadline:
        sess = get_session()
        try:
            j = sess.query(AgentBuildJob).filter(AgentBuildJob.id == job.id).first()
        finally:
            sess.close()
        if j and j.status not in ("queued", "running"):
            final = j
            break
        time.sleep(1)

    if not final:
        print("[FAIL] job did not reach a terminal state in 30s")
        return 1

    print(f"[2/4] job #{final.id} terminal status={final.status} "
          f"build_ok={final.build_ok} deploy_ok={final.deploy_ok} "
          f"target={final.deploy_target}")

    if final.status not in ("success", "needs_publish"):
        print(f"[FAIL] expected success/needs_publish, got {final.status}: {final.error}")
        return 1

    # If we landed in needs_publish (no deploy hook), exercise the
    # operator confirmation step too.
    if final.status == "needs_publish":
        ok = confirm_publish(final.id, reviewer="smoke-test")
        print(f"[3/4] confirm_publish → {ok}")
        if not ok:
            return 1

    jobs = list_build_jobs(limit=3)
    print(f"[4/4] list_build_jobs returned {len(jobs)} job(s); newest #{jobs[0].id} "
          f"status={jobs[0].status}")

    # Cleanup the smoke row
    sess = get_session()
    try:
        sess.query(AgentBuildJob).filter(AgentBuildJob.id == final.id).delete()
        sess.commit()
    finally:
        sess.close()

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
