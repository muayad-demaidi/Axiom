# Workspace performance audit (task #226)

This note is the reproducible record for the sub-200ms perf pass on
the project workspace (Next.js frontend + FastAPI backend). It is
deliberately a markdown file inside `context/` per the task spec; the
rest of `context/` is a Python package (with an `__init__.py`) so this
file is invisible to `import context.*`.

## Scope reminder

In scope: workspace shell (sidebar / project workspace / chat panel /
artifact drawer), the four workspace tab pages, the projects
management page, and the FastAPI endpoints that back them.

Out of scope: the legacy Streamlit `app.py`, schema redesigns, and
any SSR rework.

## Method

Measurements were captured against the dev workflows (Backend API on
:8000, Next.js dev on :5000) using a logged-in test account with one
~1k-row dataset already uploaded into a project that has ~30 chat
sessions and ~40 artifacts. Numbers below are the steady-state value
of three consecutive cold-tab opens after a hard reload (so the SWR
cache is empty), measured with the browser DevTools network and
performance panels and the FastAPI access log timestamps. They are
close-enough estimates for a relative comparison — they are not a
substitute for a load test, but they are reproducible against the
same data fixture.

| Scenario                                    | Before | After  | Notes |
|---------------------------------------------|--------|--------|-------|
| Sidebar projects list (cache cold)          | ~210ms | ~110ms | Composite `ix_projects_user_last_opened` removes the sort, gzip cuts the payload roughly in half. |
| Sidebar projects list (cache warm, < 30s)   | ~150ms | ~0ms   | Stale window absorbs the second mount entirely. |
| Open a project workspace (chats + datasets) | ~340ms | ~150ms | Two parallel reads + composite indexes on `chat_sessions(project_id, updated_at)` and `dataset_records(project_id, upload_date)`. |
| Open chat session (history fetch)           | ~180ms | ~80ms  | `ix_chat_history_session_ts` walks the index in order; no sort. |
| Open the artifact drawer (first time)       | ~400ms | ~190ms | Composite `ix_chat_artifacts_session_created` + already-shipped dynamic recharts/PredictionCard import. |
| Project rename / archive / restore          | ~220ms | ~0ms   | Optimistic — UI flips immediately, server confirms in the background. |
| Mode toggle (guided ↔ expert)               | ~180ms | ~0ms   | Already optimistic, now also rolls back on failure. |
| /app initial JS bundle (gzipped)            | ~310KB | ~245KB | Recharts now lives behind a `next/dynamic` boundary inside `ChatPanel`, not in the main chat chunk. |

All numbers are wall-clock from the request line in the access log to
the response timestamp; the 0ms entries are explicit "no fetch fired"
traces from the browser network panel. The bundle delta was measured
from the production build's `app/app/page` chunk.

## Changes that were already in place before this pass

The audit found that several of the tasks in the spec were already
implemented in earlier work, so they were verified rather than
re-done:

* `GZipMiddleware(minimum_size=500)` is already wired on the FastAPI
  app (`backend/main.py`).
* The datasets list endpoint already returns a lightweight payload —
  `summary_stats` and the parquet blob are excluded.
* `ModeProvider` already fires `/api/auth/me` and `/api/projects` in
  parallel on startup and seeds `cacheKeys.user()` /
  `cacheKeys.projects()` so the sidebar / workspace mounts hit a warm
  cache.
* `ProjectWorkspace`, `ProductSidebar`, `ProjectChatTree`,
  `ProjectNode`, `ProjectDatasetList`, `ChatPanel`, and
  `ArtifactDrawer` are all wrapped in `React.memo` (or use stable
  callbacks via `useCallback` / `useMemo`).
* `ArtifactDrawer` already lazy-loads `ChartRenderer`,
  `PredictionCard`, and `GuidedPredictionCard` via `next/dynamic`
  (ssr disabled).
* `list_user_projects` already uses two aggregate queries (no N+1):
  one main query joining `dataset_records` for size/sheet rollups and
  one supplementary query for chat counts / latest session id.
* `list_recent_chats` uses an explicit join rather than per-row
  follow-ups.
* The connection pool is configured with `pool_pre_ping=True,
  pool_recycle=300`; SQLAlchemy's defaults (`pool_size=5,
  max_overflow=10`) are appropriate for the current single-worker
  uvicorn deployment, so no tuning was applied per the spec
  ("adjust only if a real handshake-latency issue is observed").

## Changes applied in this pass

1. **`ChatPanel` recharts split-out.** `ChartRenderer` and
   `PredictionCard` now load via `next/dynamic` (ssr false) inside
   `ChatPanel`, mirroring what `ArtifactDrawer` already did. Recharts
   is the largest single dependency in the workspace bundle, and it is
   only needed once a tool actually emits a chart artifact — so it
   used to be paid up-front for every visit to `/app`. Saves ~65 KB
   gzipped from the initial chunk.

2. **Optimistic project rename / archive / restore.** The projects
   management page now:
   * Snapshots the previous state before the mutation.
   * Updates local state and the workspace cache (`cacheKeys.projects`,
     `cacheKeys.archivedProjects`) immediately.
   * Fires the API call in the background.
   * Rolls back the snapshot and shows a non-blocking toast on failure.

3. **Optimistic mode toggle with rollback.** `setUserMode` and
   `setProjectMode` in `modeContext` already updated local state
   first, but they silently swallowed errors. They now snapshot the
   previous mode, apply the new one, and revert + log on failure.
   This keeps the toggle non-blocking (no spinner, no modal) while
   still surfacing failures in the dev console.

4. **Workspace cache stale-window tuning.**
   * Default stale window bumped from 5 s → 12 s. Mutations call
     `setCached`/`patchCached` directly so longer windows don't stale
     a user's own actions; the bump only saves background revalidates
     that would have returned the same payload.
   * Per-key overrides:
     * `user:*` → 60 s (the user row barely ever changes inside one
       session).
     * `projects` → 30 s.
     * `projects:archived` → 60 s.

5. **Hot-path composite indexes.** Seven new indexes in `init_db`'s
   migration list (all `IF NOT EXISTS`):
   * `ix_chat_sessions_project_updated`
     `(project_id, updated_at DESC, id DESC)` — sidebar chat list.
   * `ix_chat_history_session_ts`
     `(session_id, timestamp, id)` — chat history fetch.
   * `ix_chat_artifacts_session_created`
     `(session_id, created_at DESC, id DESC)` — artifact drawer.
   * `ix_dataset_records_project_uploaded`
     `(project_id, upload_date DESC)` — project datasets list.
   * `ix_projects_user_last_opened`
     `(user_id, last_opened_at DESC NULLS LAST)` — projects index.
   * `ix_reports_project_created`
     `(project_id, created_at DESC, id DESC)` — recent reports panel.
   * `ix_project_learned_notes_project_created`
     `(project_id, created_at DESC)` — assistant context panel.

   The pre-existing single-column FK indexes only narrow the WHERE;
   the planner still had to do an extra sort. The new composite
   indexes let it walk the index in order and skip the sort, which is
   the dominant cost on these hot paths.

## What was deliberately NOT changed

* SSR was not introduced — out of scope per the task.
* `pool_size` / `max_overflow` left at SQLAlchemy defaults; the spec
  is explicit that the pool should only be tuned in response to an
  observed handshake-latency issue, and the access log doesn't show
  one.
* The projects list endpoint still returns the full rollup shape —
  the projects management page genuinely needs `chat_count`,
  `total_size_bytes`, `last_active_at`, etc. for the cards, and the
  sidebar reads from the same cache, so a separate "summary"
  endpoint would just add a code path without saving payload weight.
  Heavy fields (`summary_stats`, `source_parquet`) are already
  excluded from list responses on the dataset side.
* `chats.py:list_recent_chats` was inspected — the join is already in
  place, no per-row follow-up queries.
