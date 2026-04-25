"use client";
/**
 * Lightweight in-memory client cache for the workspace shell.
 *
 * The unified left sidebar and the project workspace both need to read
 * the same lists (projects, chats per project, datasets per project,
 * recent chats, dataset previews). Without sharing, switching back to a
 * recently-visited project would re-trigger network requests and flash
 * a loading state, which makes navigation feel sluggish.
 *
 * This module exposes a tiny stale-while-revalidate primitive:
 *   - `getCached(key)` returns whatever is currently cached or undefined.
 *   - `setCached(key, value)` stores a value and notifies subscribers.
 *   - `useCachedList(key, fetcher)` returns cached data immediately and
 *     revalidates in the background.
 *
 * Cache lifetime is the lifetime of the JS module (i.e. the tab). We
 * intentionally do NOT persist anything to localStorage so we can't
 * leak data between accounts on a shared machine.
 */
import { useCallback, useEffect, useState } from "react";

type Listener = () => void;

const store = new Map<string, unknown>();
const subs = new Map<string, Set<Listener>>();
const inflight = new Map<string, Promise<unknown>>();

export function getCached<T>(key: string): T | undefined {
  return store.get(key) as T | undefined;
}

export function setCached<T>(key: string, value: T): void {
  store.set(key, value);
  subs.get(key)?.forEach((fn) => {
    try {
      fn();
    } catch {
      /* listener errors must not block other subscribers */
    }
  });
}

export function patchCached<T>(key: string, updater: (cur: T | undefined) => T): void {
  const cur = store.get(key) as T | undefined;
  setCached(key, updater(cur));
}

export function clearCached(key: string): void {
  store.delete(key);
  subs.get(key)?.forEach((fn) => fn());
}

/** Drops every cached entry — call on logout so a second user logging
 *  in on the same tab can't peek at the previous user's lists. */
export function clearAllCached(): void {
  const keys = Array.from(store.keys());
  store.clear();
  for (const k of keys) {
    subs.get(k)?.forEach((fn) => fn());
  }
}

export function subscribeCached(key: string, fn: Listener): () => void {
  let s = subs.get(key);
  if (!s) {
    s = new Set();
    subs.set(key, s);
  }
  s.add(fn);
  return () => {
    s!.delete(fn);
  };
}

/**
 * Stale-while-revalidate hook for a single keyed list.
 *
 * Returns the cached value immediately if one exists (so navigation
 * back to a previously-visited screen feels instant) and kicks off a
 * background revalidate. The fetcher is de-duplicated per key so
 * concurrent mounts don't fan out into multiple requests.
 *
 * Pass `enabled: false` (or a null key) to skip the fetch entirely —
 * useful when the screen is auth-gated and we haven't decided yet.
 */
export function useCachedList<T>(
  key: string | null,
  fetcher: () => Promise<T>,
  opts: { enabled?: boolean } = {}
): {
  data: T | undefined;
  loading: boolean;
  error: unknown;
  refresh: () => Promise<T | undefined>;
} {
  const enabled = opts.enabled !== false && !!key;
  const [, force] = useState(0);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    if (!key) return;
    return subscribeCached(key, () => force((n) => n + 1));
  }, [key]);

  const refresh = useCallback(async (): Promise<T | undefined> => {
    if (!key) return undefined;
    let p = inflight.get(key) as Promise<T> | undefined;
    if (!p) {
      p = fetcher();
      inflight.set(key, p);
      p.finally(() => {
        if (inflight.get(key) === p) inflight.delete(key);
      });
    }
    try {
      const v = await p;
      setCached(key, v);
      setError(null);
      return v;
    } catch (e) {
      setError(e);
      return undefined;
    }
    // We deliberately exclude `fetcher` from the dep list — callers are
    // expected to pass a stable closure (e.g. via useCallback). Folding
    // an unstable fetcher in here would cause an infinite refetch loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    if (!enabled) return;
    void refresh();
  }, [enabled, refresh]);

  const data = key ? (store.get(key) as T | undefined) : undefined;
  return {
    data,
    loading: enabled && data === undefined && error == null,
    error,
    refresh,
  };
}

// ----------------- Cache key factories -----------------
// Centralised so both the sidebar and the workspace agree on the key
// shape; rename safely from one place.

export const cacheKeys = {
  projects: () => "projects",
  recentChats: (limit: number) => `recent_chats:${limit}`,
  projectChats: (projectId: number) => `project:${projectId}:chats`,
  projectDatasets: (projectId: number) => `project:${projectId}:datasets`,
  allDatasets: () => "datasets:all",
  datasetPreview: (datasetId: number, rows: number) =>
    `dataset:${datasetId}:preview:${rows}`,
};
