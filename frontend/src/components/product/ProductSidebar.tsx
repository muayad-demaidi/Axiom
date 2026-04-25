"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { api, getToken } from "@/lib/api";
import type { AxiomProject, AxiomUser } from "@/lib/types";

type RecentChat = {
  id: number;
  project_id: number;
  project_name?: string | null;
  title: string;
  updated_at: string | null;
};

type QuickStartResponse = {
  project_id: number;
  session_id: number;
};

const TOOL_LINKS: { href: string; label: string }[] = [
  { href: "/app/upload", label: "Files" },
  { href: "/app/connectors", label: "Data Connectors" },
];

export function ProductSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [chats, setChats] = useState<RecentChat[] | null>(null);
  const [projects, setProjects] = useState<AxiomProject[] | null>(null);
  const [isAdmin, setIsAdmin] = useState(false);
  const [busy, setBusy] = useState(false);
  const [refreshTick, setRefreshTick] = useState(0);

  // Refetch when route changes (so newly-created chats show up immediately
  // after navigation) plus an explicit tick we bump after quick-start.
  useEffect(() => {
    if (!getToken()) return;
    let cancelled = false;
    Promise.all([
      api<RecentChat[]>("/api/chats/recent?limit=10").catch(() => []),
      api<AxiomProject[]>("/api/projects").catch(() => []),
      api<AxiomUser>("/api/auth/me").catch(() => null),
    ]).then(([c, p, u]) => {
      if (cancelled) return;
      setChats(c as RecentChat[]);
      // Hide the auto-managed Quick Chats bucket from the user-visible
      // Projects list; it still backs the home-screen chats.
      setProjects((p as AxiomProject[]).filter((proj) => proj.name !== "Quick Chats"));
      setIsAdmin(Boolean((u as AxiomUser | null)?.is_admin));
    });
    return () => {
      cancelled = true;
    };
  }, [pathname, refreshTick]);

  const newChat = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api<QuickStartResponse>("/api/chats/quick", {
        method: "POST",
        json: {},
      });
      setRefreshTick((t) => t + 1);
      router.push(`/app/project/${res.project_id}?session=${res.session_id}`);
    } catch {
      router.push("/app");
    } finally {
      setBusy(false);
    }
  }, [busy, router]);

  return (
    <aside className="border-r border-[var(--border)] bg-[var(--surface-alt)] p-4 text-sm flex flex-col gap-4 overflow-y-auto">
      <button
        onClick={newChat}
        disabled={busy}
        className="btn btn-primary text-sm justify-center w-full"
      >
        + New chat
      </button>

      <Section label="Chats">
        {chats === null ? (
          <Hint>Loading…</Hint>
        ) : chats.length === 0 ? (
          <Hint>No chats yet.</Hint>
        ) : (
          <ul className="space-y-0.5">
            {chats.map((c) => {
              const href = `/app/project/${c.project_id}?session=${c.id}`;
              const active = pathname?.startsWith(`/app/project/${c.project_id}`);
              return (
                <li key={c.id}>
                  <Link
                    href={href}
                    className={`group block rounded px-2 py-1.5 leading-tight ${
                      active
                        ? "bg-[var(--surface)] text-[var(--text)]"
                        : "text-[var(--text)] hover:bg-[var(--surface)]"
                    }`}
                  >
                    <div className="text-xs truncate">{c.title || "Untitled"}</div>
                    {c.project_name && (
                      <div className="text-[10px] font-mono text-[var(--text-muted)] truncate">
                        {c.project_name}
                      </div>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section
        label="Projects"
        action={
          <Link
            href="/app/projects"
            className="text-[10px] font-mono text-[var(--text-muted)] hover:text-[var(--accent)]"
          >
            All
          </Link>
        }
      >
        {projects === null ? (
          <Hint>Loading…</Hint>
        ) : projects.length === 0 ? (
          <Hint>No projects yet.</Hint>
        ) : (
          <ul className="space-y-0.5">
            {projects.slice(0, 8).map((p) => {
              const href = `/app/project/${p.id}`;
              const active = pathname === href || pathname?.startsWith(href + "?") || pathname?.startsWith(href + "/");
              return (
                <li key={p.id}>
                  <Link
                    href={href}
                    className={`block rounded px-2 py-1.5 text-xs truncate ${
                      active
                        ? "bg-[var(--accent)] text-white"
                        : "text-[var(--text)] hover:bg-[var(--surface)]"
                    }`}
                    title={p.name}
                  >
                    {p.name}
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </Section>

      <Section label="Workspace">
        <ul className="space-y-0.5">
          {TOOL_LINKS.map((it) => {
            const active = pathname === it.href;
            return (
              <li key={it.href}>
                <Link
                  href={it.href}
                  className={`block rounded px-2 py-1.5 text-xs ${
                    active
                      ? "bg-[var(--accent)] text-white"
                      : "text-[var(--text)] hover:bg-[var(--surface)]"
                  }`}
                >
                  {it.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </Section>

      {isAdmin && (
        <Section label="Admin">
          <ul className="space-y-0.5">
            <li>
              <Link
                href="/app/admin/support"
                className={`block rounded px-2 py-1.5 text-xs ${
                  pathname?.startsWith("/app/admin/support")
                    ? "bg-[var(--accent)] text-white"
                    : "text-[var(--text)] hover:bg-[var(--surface)]"
                }`}
              >
                Support inbox
              </Link>
            </li>
          </ul>
        </Section>
      )}
    </aside>
  );
}

function Section({
  label,
  action,
  children,
}: {
  label: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)]">
          {label}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="text-[var(--text-muted)] text-xs px-2 py-1">{children}</div>;
}
