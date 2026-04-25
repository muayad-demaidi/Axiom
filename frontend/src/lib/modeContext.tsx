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
  useState,
} from "react";
import { api, ApiError, getToken } from "@/lib/api";
import type { AxiomProject, AxiomUser } from "@/lib/types";

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
  const [userMode, setUserModeState] = useState<Mode>(() => readCachedUserMode());
  const [projectModes, setProjectModes] = useState<Record<number, Mode | null>>(
    {}
  );
  const [ready, setReady] = useState(false);

  // Initial load — pulls the user mode from the API (so a fresh tab on
  // another device picks up the right default) and a single round of
  // project modes so per-project pills don't flash on first paint.
  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const me = await api<AxiomUser>("/api/auth/me");
        if (cancelled) return;
        const m: Mode = me.assistant_mode === "expert" ? "expert" : "guided";
        setUserModeState(m);
        writeCachedUserMode(m);
      } catch (e: unknown) {
        if (e instanceof ApiError && e.status === 401) {
          // Soft-fail: chrome will route to /login on its own.
        }
      }
      try {
        const projects = await api<AxiomProject[]>("/api/projects");
        if (cancelled) return;
        const next: Record<number, Mode | null> = {};
        for (const p of projects) {
          const m = p.mode === "expert" ? "expert" : p.mode === "guided" ? "guided" : null;
          next[p.id] = m;
          writeCachedProjectMode(p.id, m);
        }
        setProjectModes(next);
      } catch {
        /* ignore */
      }
      if (!cancelled) setReady(true);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setUserMode = useCallback(async (m: Mode) => {
    setUserModeState(m);
    writeCachedUserMode(m);
    try {
      await api<AxiomUser>("/api/auth/me", {
        method: "PATCH",
        json: { assistant_mode: m },
      });
    } catch {
      /* keep local state — next reload will reconcile */
    }
  }, []);

  const setProjectMode = useCallback(async (projectId: number, m: Mode) => {
    setProjectModes((cur) => ({ ...cur, [projectId]: m }));
    writeCachedProjectMode(projectId, m);
    try {
      await api<AxiomProject>(`/api/projects/${projectId}`, {
        method: "PATCH",
        json: { mode: m },
      });
    } catch {
      /* keep local state */
    }
  }, []);

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

  return <ModeContext.Provider value={value}>{children}</ModeContext.Provider>;
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
    // still render in stories / outside the app.
    return {
      mode: readCachedUserMode(),
      setMode: async () => {},
      isProjectScoped: false,
      ready: false,
    };
  }
  if (projectId != null) {
    const override = ctx.projectModes[projectId];
    const cached = override ?? readCachedProjectMode(projectId);
    const resolved = cached ?? ctx.userMode;
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
