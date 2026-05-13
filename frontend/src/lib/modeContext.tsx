"use client";
/**
 * Guided/Expert mode context.
 *
 * Tracks two things:
 *   * the user-level preferred mode (loaded from /api/auth/me, persisted
 *     via PATCH /api/auth/me)
 *   * a per-project override map keyed by project id (loaded lazily from
 *     /api/projects, persisted via PATCH /api/projects/:id)
 *
 * Consumers call ``useMode(projectId?)`` and get back the *resolved*
 * mode for that scope plus a one-call setter that does the right thing:
 * inside a project workspace it edits the project's mode; on the home /
 * landing pages it edits the user-level preference.
 *
 * Defaults to Guided per the product spec when nothing is loaded yet.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { api, ApiError, getToken } from "@/lib/api";
import type { AxiomProject, AxiomUser } from "@/lib/types";
import { cacheKeys, getCached, patchCached, setCached } from "@/lib/workspaceCache";

export type Mode = "guided" | "expert";

const USER_CACHE_KEY = "axiom_user_mode";
const PROJECT_CACHE_PREFIX = "axiom_project_mode_";

function readCachedUserMode(): Mode {
  if (typeof window === "undefined") return "guided";
  const v = window.localStorage.getItem(USER_CACHE_KEY);
  return v === "expert" ? "expert" : "guided";
}
function writeCachedUserMode(m: Mode) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(USER_CACHE_KEY, m);
}
function readCachedProjectMode(id: number): Mode | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(PROJECT_CACHE_PREFIX + id);
  if (v === "expert" || v === "guided") return v;
  return null;
}
function writeCachedProjectMode(id: number, m: Mode | null) {
  if (typeof window === "undefined") return;
  if (m == null) window.localStorage.removeItem(PROJECT_CACHE_PREFIX + id);
  else window.localStorage.setItem(PROJECT_CACHE_PREFIX + id, m);
}


type ModeContextValue = {
  /** User-level preferred mode (Guided by default). */
  userMode: Mode;
  /** Map of project_id -> per-project mode override (null = not set). */
  projectModes: Record<number, Mode | null>;
  /** True once the initial /api/auth/me load has settled. */
  ready: boolean;
  /** Set the user-level mode (also persists to backend). */
  setUserMode: (m: Mode) => Promise<void>;
  /** Set a per-project mode override (also persists to backend). */
  setProjectMode: (projectId: number, m: Mode) => Promise<void>;
  /** Locally seed a project's mode (e.g. after fetching a project list). */
  seedProjectMode: (projectId: number, m: Mode | null) => void;
};

const ModeContext = createContext<ModeContextValue | null>(null);

export function ModeProvider({ children }: { children: React.ReactNode }) {
  // Always initialize with the spec default ("guided") so the server
  // render and the very first client render agree. The cached value
  // (and then the API value) are layered on inside an effect below,
  // after hydration has completed.
  const [userMode, setUserModeState] = useState<Mode>("guided");
  const [projectModes, setProjectModes] = useState<Record<number, Mode | null>>(
    {}
  );
  const [ready, setReady] = useState(false);
  // Lightweight rollback notice rendered inside the provider tree so it
  // shares the React lifecycle with the rest of the app instead of
  // being injected ad-hoc into document.body. Only used by the two
  // mode-toggle failure paths below.
  const [rollbackToast, setRollbackToast] = useState<string | null>(null);
  const rollbackTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notifyRollback = useCallback((text: string) => {
    setRollbackToast(text);
    if (rollbackTimer.current) clearTimeout(rollbackTimer.current);
    rollbackTimer.current = setTimeout(() => setRollbackToast(null), 3500);
  }, []);
  useEffect(() => {
    return () => {
      if (rollbackTimer.current) clearTimeout(rollbackTimer.current);
    };
  }, []);

  // Refs mirror the latest state so the optimistic mutators below can
  // capture the *current* value synchronously at function-entry — rather
  // than relying on the closure-assignment trick inside a setState
  // updater, which is sound but timing-sensitive under React 18
  // concurrent rendering. Refs are written in a passive effect (post-
  // commit), which is fine here: the mutators are fired from user-event
  // handlers (clicks, key presses), and any commit triggered by an
  // earlier toggle has already run by the time the next handler fires.
  const userModeRef = useRef(userMode);
  const projectModesRef = useRef(projectModes);
  useEffect(() => {
    userModeRef.current = userMode;
  }, [userMode]);
  useEffect(() => {
    projectModesRef.current = projectModes;
  }, [projectModes]);

  // Initial load — first synchronously rehydrate from localStorage so
  // the toggle doesn't flash "Guided" before snapping to the user's
  // remembered choice, then fetch the canonical value from the API
  // (so a fresh tab on another device picks up the right default) plus
  // a single round of project modes so per-project pills don't flash
  // on first paint.
  useEffect(() => {
    const cached = readCachedUserMode();
    if (cached !== "guided") setUserModeState(cached);

    if (!getToken()) {
      setReady(true);
      return;
    }
    let cancelled = false;
    (async () => {
      // Kick both startup requests off in parallel — they're independent
      // and previously serialized, paying the round-trip latency twice.
      // Settled (not all) so a 401 on one doesn't suppress the other,
      // and we still write whatever we got into the shared cache so the
      // sidebar's `useCachedItem(cacheKeys.user())` and the workspace's
      // `useCachedList(cacheKeys.projects())` both hit warm.
      const [meRes, projectsRes] = await Promise.allSettled([
        api<AxiomUser>("/api/auth/me"),
        api<AxiomProject[]>("/api/projects"),
      ]);
      if (cancelled) return;

      if (meRes.status === "fulfilled") {
        const me = meRes.value;
        const m: Mode = me.assistant_mode === "expert" ? "expert" : "guided";
        setUserModeState(m);
        writeCachedUserMode(m);
        setCached(cacheKeys.user(), me);
      } else {
        const e = meRes.reason;
        if (e instanceof ApiError && e.status === 401) {
          // Soft-fail: chrome will route to /login on its own.
        }
      }

      if (projectsRes.status === "fulfilled") {
        const projects = projectsRes.value;
        const next: Record<number, Mode | null> = {};
        for (const p of projects) {
          const m = p.mode === "expert" ? "expert" : p.mode === "guided" ? "guided" : null;
          next[p.id] = m;
          writeCachedProjectMode(p.id, m);
        }
        setProjectModes(next);
        setCached(cacheKeys.projects(), projects);
      }

      setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setUserMode = useCallback(async (m: Mode) => {
    // Optimistic flip: snap the toggle and persisted preference straight
    // away so the UI never has to wait for the round-trip. If the PATCH
    // fails (network blip, 401), roll back the local state and surface
    // a console hint — the next page load will reconcile from the
    // canonical /api/auth/me. We deliberately don't pop a modal here to
    // keep the toggle non-blocking.
    //
    // `prevMode` is captured from a ref-mirrored snapshot of current
    // state, so rollback always restores exactly what was on screen
    // when the user clicked — independent of any concurrent renders.
    const prevMode: Mode = userModeRef.current;
    setUserModeState(m);
    writeCachedUserMode(m);
    try {
      await api<AxiomUser>("/api/auth/me", {
        method: "PATCH",
        json: { assistant_mode: m },
      });
    } catch (e) {
      setUserModeState(prevMode);
      writeCachedUserMode(prevMode);
      notifyRollback("Couldn't save mode preference. Reverted.");
      if (typeof console !== "undefined") {
        console.warn("setUserMode failed; reverted local state", e);
      }
    }
  }, [notifyRollback]);

  const setProjectMode = useCallback(async (projectId: number, m: Mode) => {
    // Optimistic per-project mode flip with rollback on failure. Also
    // patches the cached projects list (`cacheKeys.projects()` /
    // `cacheKeys.archivedProjects()`) so the mode pill on the projects
    // index page snaps to the new value without a refetch.
    //
    // `prev` is read from `projectModesRef` (mirrors current state) so
    // rollback restores the exact value that was visible at click time.
    const prev: Mode | null | undefined = projectModesRef.current[projectId];
    setProjectModes((cur) => ({ ...cur, [projectId]: m }));
    writeCachedProjectMode(projectId, m);
    const applyMode = (mode: Mode | null) => (p: AxiomProject) =>
      p.id === projectId ? { ...p, mode } : p;
    // Only patch caches that already hold a value — writing `[]` into a
    // never-fetched key would mark it cached and suppress the consumer's
    // initial fetch for the stale window.
    const patchIfCached = (key: string, mode: Mode | null) => {
      if (getCached<AxiomProject[]>(key) === undefined) return;
      patchCached<AxiomProject[]>(key, (cur) => (cur || []).map(applyMode(mode)));
    };
    patchIfCached(cacheKeys.projects(), m);
    patchIfCached(cacheKeys.archivedProjects(), m);
    try {
      await api<AxiomProject>(`/api/projects/${projectId}`, {
        method: "PATCH",
        json: { mode: m },
      });
    } catch (e) {
      // Preserve `undefined` (never-seeded) vs explicit `null` (seeded
      // with no override) so future `seedProjectMode` calls — which
      // gate on `cur[projectId] !== undefined` — still hydrate a row
      // that the user toggled before any project list was loaded.
      setProjectModes((cur) => {
        if (prev === undefined) {
          const { [projectId]: _drop, ...rest } = cur;
          return rest;
        }
        return { ...cur, [projectId]: prev };
      });
      writeCachedProjectMode(projectId, prev ?? null);
      // Same guard as the optimistic path: don't materialize an empty
      // array into a cache key that wasn't there to begin with.
      patchIfCached(cacheKeys.projects(), prev ?? null);
      patchIfCached(cacheKeys.archivedProjects(), prev ?? null);
      notifyRollback("Couldn't update project mode. Reverted.");
      if (typeof console !== "undefined") {
        console.warn(
          `setProjectMode(${projectId}) failed; reverted local state`,
          e
        );
      }
    }
  }, [notifyRollback]);

  const seedProjectMode = useCallback(
    (projectId: number, m: Mode | null) => {
      setProjectModes((cur) => {
        // Don't clobber a user-set choice we already have in cache.
        if (cur[projectId] !== undefined) return cur;
        writeCachedProjectMode(projectId, m);
        return { ...cur, [projectId]: m };
      });
    },
    []
  );

  const value = useMemo<ModeContextValue>(
    () => ({
      userMode,
      projectModes,
      ready,
      setUserMode,
      setProjectMode,
      seedProjectMode,
    }),
    [userMode, projectModes, ready, setUserMode, setProjectMode, seedProjectMode]
  );

  return (
    <ModeContext.Provider value={value}>
      {children}
      {rollbackToast && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: "fixed",
            left: "50%",
            bottom: 24,
            transform: "translateX(-50%)",
            zIndex: 9999,
            padding: "10px 14px",
            borderRadius: 10,
            background: "rgba(20,20,24,0.92)",
            color: "#fff",
            font: "500 13px/1.4 system-ui,-apple-system,Segoe UI,Roboto,sans-serif",
            boxShadow: "0 6px 24px rgba(0,0,0,0.25)",
            maxWidth: "min(92vw, 420px)",
            pointerEvents: "none",
          }}
        >
          {rollbackToast}
        </div>
      )}
    </ModeContext.Provider>
  );
}

/**
 * Resolve the active mode for the given scope.
 *
 *   * No projectId  -> always returns the user-level mode.
 *   * With projectId -> returns the per-project override if set,
 *     otherwise the user-level mode.
 *
 * The returned ``setMode`` writes to the right place automatically.
 */
export function useMode(projectId?: number | null): {
  mode: Mode;
  setMode: (m: Mode) => Promise<void>;
  isProjectScoped: boolean;
  ready: boolean;
} {
  const ctx = useContext(ModeContext);
  if (!ctx) {
    // Provider missing — fall back to a read-only stub so components can
    // still render in stories / outside the app. Always returns the
    // spec default so server and first-client renders agree.
    return {
      mode: "guided",
      setMode: async () => {},
      isProjectScoped: false,
      ready: false,
    };
  }
  if (projectId != null) {
    // Read only from context state (which is itself hydrated inside an
    // effect). Reading localStorage here would diverge between server
    // and first-client renders and re-introduce a hydration warning.
    const override = ctx.projectModes[projectId];
    const resolved = override ?? ctx.userMode;
    return {
      mode: resolved,
      setMode: (m: Mode) => ctx.setProjectMode(projectId, m),
      isProjectScoped: true,
      ready: ctx.ready,
    };
  }
  return {
    mode: ctx.userMode,
    setMode: ctx.setUserMode,
    isProjectScoped: false,
    ready: ctx.ready,
  };
}

/** Pure helper for non-React callers. */
export function getActiveMode(projectId?: number | null): Mode {
  if (projectId != null) {
    const v = readCachedProjectMode(projectId);
    if (v) return v;
  }
  return readCachedUserMode();
}
