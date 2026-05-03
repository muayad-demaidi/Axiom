"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import type { AxiomUser } from "@/lib/types";
import { errMessage } from "@/lib/types";

type SupportMessage = {
  id: number;
  name: string | null;
  email: string;
  message: string;
  created_at: string | null;
  handled: boolean;
};

type ListResponse = {
  messages: SupportMessage[];
  total: number;
  offset: number;
  limit: number;
};

const PAGE_SIZE = 100;

function formatTimestamp(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}

export default function AdminSupportPage() {
  const router = useRouter();
  const [me, setMe] = useState<AxiomUser | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [messages, setMessages] = useState<SupportMessage[] | null>(null);
  const [total, setTotal] = useState<number>(0);
  const [error, setError] = useState<string | null>(null);
  const [onlyUnhandled, setOnlyUnhandled] = useState(true);
  const [pendingId, setPendingId] = useState<number | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  // Gate the page client-side: redirect anonymous users to login and
  // non-admins back to the workspace home. The backend re-checks the gate
  // on every request, so this is purely a UX fast-path.
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<AxiomUser>("/api/auth/me")
      .then((u) => {
        setMe(u);
        setAuthChecked(true);
        if (!u.is_admin) router.push("/app");
      })
      .catch((e: ApiError) => {
        if (e.status === 401) router.push("/login");
        else {
          setError(e.message);
          setAuthChecked(true);
        }
      });
  }, [router]);

  const load = useCallback(() => {
    setError(null);
    const qs = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: "0",
    });
    if (onlyUnhandled) qs.set("only_unhandled", "true");
    api<ListResponse>(`/api/support/messages?${qs.toString()}`)
      .then((r) => {
        setMessages(r.messages);
        setTotal(r.total);
      })
      .catch((e: ApiError) => setError(e.message));
  }, [onlyUnhandled]);

  useEffect(() => {
    if (!me?.is_admin) return;
    load();
  }, [me, load]);

  async function loadMore() {
    if (loadingMore || messages === null) return;
    setLoadingMore(true);
    setError(null);
    try {
      const qs = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(messages.length),
      });
      if (onlyUnhandled) qs.set("only_unhandled", "true");
      const r = await api<ListResponse>(`/api/support/messages?${qs.toString()}`);
      setMessages((arr) => {
        const existing = arr ?? [];
        const seen = new Set(existing.map((m) => m.id));
        const next = r.messages.filter((m) => !seen.has(m.id));
        return [...existing, ...next];
      });
      setTotal(r.total);
    } catch (e: unknown) {
      setError(errMessage(e));
    } finally {
      setLoadingMore(false);
    }
  }

  async function toggleHandled(msg: SupportMessage) {
    setPendingId(msg.id);
    try {
      const updated = await api<SupportMessage>(
        `/api/support/messages/${msg.id}`,
        { method: "PATCH", json: { handled: !msg.handled } },
      );
      setMessages((arr) => {
        if (!arr) return arr;
        // When viewing only unhandled, drop rows that just got handled.
        if (onlyUnhandled && updated.handled) {
          setTotal((t) => Math.max(0, t - 1));
          return arr.filter((m) => m.id !== updated.id);
        }
        return arr.map((m) => (m.id === updated.id ? updated : m));
      });
    } catch (e: unknown) {
      setError(errMessage(e));
    } finally {
      setPendingId(null);
    }
  }

  if (!authChecked) {
    return (
      <div className="text-[var(--text-muted)] text-sm inline-flex items-center gap-2" role="status" aria-live="polite" dir="rtl">
        <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]" aria-hidden="true" />
        Loading…
      </div>
    );
  }
  if (!me?.is_admin) {
    return null; // redirect already in flight
  }

  const shown = messages?.length ?? 0;
  const hasMore = messages !== null && shown < total;

  return (
    <div className="max-w-4xl" dir="rtl">
      <span className="eyebrow">Admin</span>
      <h1 className="text-2xl md:text-3xl font-bold mt-2">Support inbox</h1>
      <p className="text-[var(--text-muted)] mt-2 text-sm">
        Every message sent through the contact form is saved here so you can follow up even if email delivery fails.
      </p>

      <div className="mt-6 flex items-center justify-between gap-3 flex-wrap">
        <label className="inline-flex items-center gap-2 text-sm" style={{ minHeight: 32 }}>
          <input
            type="checkbox"
            className="h-4 w-4"
            checked={onlyUnhandled}
            onChange={(e) => setOnlyUnhandled(e.target.checked)}
          />
          Show unresolved only
        </label>
        <div className="flex items-center gap-3">
          {messages && (
            <span className="text-[12px] font-mono text-[var(--text-muted)]">
              Showing {shown} from {total}
            </span>
          )}
          <button onClick={load} className="btn text-sm" style={{ minHeight: 44 }}>
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="text-red-600 text-sm mt-4 rounded border border-red-500/30 bg-red-500/10 px-3 py-2" role="alert">
          {error}
        </div>
      )}

      <div className="mt-6 space-y-3">
        {messages === null ? (
          <div className="text-[var(--text-muted)] text-sm inline-flex items-center gap-2" role="status" aria-live="polite">
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]" aria-hidden="true" />
            Loading…
          </div>
        ) : messages.length === 0 ? (
          <div className="text-[var(--text-muted)] text-sm border border-[var(--border)] rounded p-6 text-center">
            <div className="text-2xl mb-2" aria-hidden="true">📭</div>
            {onlyUnhandled
              ? "Inbox is empty — no open messages."
              : "No support messages yet."}
          </div>
        ) : (
          messages.map((m) => (
            <article
              key={m.id}
              className="border border-[var(--border)] bg-[var(--surface)] rounded p-4"
            >
              <header className="flex items-start justify-between gap-3 flex-wrap">
                <div className="min-w-0">
                  <div className="font-semibold truncate">
                    {m.name?.trim() || "(no name)"}
                  </div>
                  <a
                    href={`mailto:${m.email}`}
                    className="text-[12px] font-mono text-[var(--text-muted)] hover:text-[var(--accent)] break-all"
                  >
                    {m.email}
                  </a>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-[12px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
                    {formatTimestamp(m.created_at)}
                  </span>
                  {m.handled && (
                    <span className="text-[12px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded bg-[var(--surface-alt)] text-[var(--text-muted)]">
                      Resolved
                    </span>
                  )}
                </div>
              </header>
              <p className="mt-3 whitespace-pre-wrap text-sm">{m.message}</p>
              <div className="mt-3 flex justify-start">
                <button
                  onClick={() => toggleHandled(m)}
                  disabled={pendingId === m.id}
                  className={m.handled ? "btn text-sm" : "btn btn-primary text-sm"}
                  style={{ minHeight: 44 }}
                >
                  {pendingId === m.id
                    ? "Saving…"
                    : m.handled
                      ? "Reopen"
                      : "Mark resolved"}
                </button>
              </div>
            </article>
          ))
        )}
      </div>

      {hasMore && (
        <div className="mt-4 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="btn text-sm"
            style={{ minHeight: 44 }}
          >
            {loadingMore ? "Loading…" : `Load more (${total - shown} remaining)`}
          </button>
        </div>
      )}
    </div>
  );
}
