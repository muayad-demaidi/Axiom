#!/usr/bin/env bash
# Production launcher for AXIOM on Replit autoscale (Cloud Run).
#
# We need to keep two processes alive in one instance:
#   1. uvicorn (FastAPI backend) — internal, 127.0.0.1:8000
#   2. next start  (Next.js prod) — public,   0.0.0.0:${PORT:-5000}
#
# Cloud Run only watches PID 1. The previous run command
#     uvicorn ... & cd frontend && npm run start ...
# silently swallowed any uvicorn startup error (because of `&`), and if
# uvicorn died there was nothing to surface the failure — every
# /api/* request from the frontend then 502'd with
#     "Failed to proxy http://localhost:8000/api/auth/login
#      Error: connect ECONNREFUSED 127.0.0.1:8000"
# which is exactly what the user reported. This script fixes that by:
#   - logging uvicorn stdout/stderr to the deployment log,
#   - probing /api/health before starting Next.js (so we never serve
#     pages while the backend is still booting),
#   - exiting non-zero if either child dies, so Cloud Run restarts the
#     instance instead of leaving a half-broken deployment up,
#   - forwarding SIGTERM/SIGINT to both children for clean shutdown.

set -uo pipefail

log() { echo "[start-prod] $*" >&2; }

log "cwd=$(pwd)  python=$(command -v python || echo MISSING)  node=$(command -v node || echo MISSING)  uvicorn=$(command -v uvicorn || echo MISSING)"

if ! command -v uvicorn >/dev/null 2>&1; then
  log "FATAL: uvicorn not on PATH. Python deps did not install in the deployment image."
  log "Add 'uv sync' or 'pip install -e .' to the build command in .replit."
  exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  log "received signal — terminating children"
  [[ -n "$BACKEND_PID"  ]] && kill -TERM "$BACKEND_PID"  2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill -TERM "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup TERM INT

log "starting uvicorn on 127.0.0.1:8000"
# Run in foreground of its own subshell so its output streams directly
# to the deployment log instead of being lost.
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --log-level info &
BACKEND_PID=$!

# Wait for the backend to answer /api/health before we hand traffic to
# Next.js. Time out after 60s — long enough for cold-start dependency
# imports (pandas, sklearn, prophet) but short enough that a true
# failure is reported quickly.
for i in $(seq 1 60); do
  if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
    log "FATAL: uvicorn died during startup (after ${i}s)"
    wait "$BACKEND_PID" 2>/dev/null || true
    exit 1
  fi
  if curl -sf -o /dev/null http://127.0.0.1:8000/api/health; then
    log "backend healthy after ${i}s"
    break
  fi
  sleep 1
done

if ! curl -sf -o /dev/null http://127.0.0.1:8000/api/health; then
  log "FATAL: backend never answered /api/health within 60s"
  cleanup
  exit 1
fi

PORT="${PORT:-5000}"
log "starting next start on 0.0.0.0:${PORT}"
(
  cd frontend
  BACKEND_URL="http://127.0.0.1:8000" exec npx --no-install next start -p "$PORT" -H 0.0.0.0
) &
FRONTEND_PID=$!

# Block on whichever child exits first. If either dies we kill the
# other and exit non-zero so Cloud Run restarts the instance.
wait -n "$BACKEND_PID" "$FRONTEND_PID"
EXITED_PID=$?
log "a child exited (status=${EXITED_PID}) — shutting down the other"
cleanup
exit 1
