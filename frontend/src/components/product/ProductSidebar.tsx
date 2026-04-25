"use client";
/**
 * Unified left sidebar for the Axiom workspace shell.
 *
 * This is the single primary navigation surface for the product:
 *   - On any page, it lists every project as a collapsible accordion
 *     node. Clicking a project navigates to that project. Each project
 *     node expands inline to reveal its sub-chats.
 *   - On a project workspace page (`/app/project/<id>`), the active
 *     project node is auto-expanded, its chats are highlighted on
 *     hover/active, and a Datasets section surfaces under the project
 *     so the user can switch between datasets attached to the project
 *     without leaving the chat.
 *   - The component is memoized at the export so chat composer typing
 *     and streaming responses inside `ChatPanel` don't trigger sidebar
 *     re-renders. It owns its own fetches via `useCachedList`, which
 *     means switching back to a previously-visited project is instant
 *     (cached) and only triggers a quiet background revalidate.
 *
 * Mutations (new/rename/delete chat, dataset upload) update the cache
 * via `setCached` / `patchCached` so the UI reflects the change
 * immediately without waiting for a network round-trip.
 */
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import { ChevronRight, Database, FileText, MessageSquarePlus, Pencil, Plus, Trash2 } from "lucide-react";
import { api, getToken } from "@/lib/api";
import { errMessage, type AxiomDataset, type AxiomProject, type AxiomUser } from "@/lib/types";
import { setActiveDatasetId } from "@/lib/projectContext";
import {
  cacheKeys,
  patchCached,
  setCached,
  useCachedList,
} from "@/lib/workspaceCache";

type ChatSession = {
  id: number;
  project_id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
};

type QuickStartResponse = {
  project_id: number;
  session_id: number;
};

const TOOL_LINKS: { href: string; label: string }[] = [
  { href: "/app/upload", label: "Files" },
  { href: "/app/connectors", label: "Data Connectors" },
  { href: "/app/dashboard", label: "Dashboard" },
  { href: "/app/pivot", label: "Pivot" },
  { href: "/app/fields", label: "Field Settings" },
];

function ProductSidebarBase() {
  const pathname = usePathname() || "";
  const searchParams = useSearchParams();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [authed, setAuthed] = useState<boolean | null>(null);

  useEffect(() => {
    setAuthed(!!getToken());
  }, []);

  // Active project / session deduced from the URL — single source of
  // truth, so the sidebar stays in sync with whatever the workspace is
  // showing without prop drilling. `useSearchParams()` is reactive to
  // `router.replace` / `router.push` calls, so when the workspace
  // mirrors the active session into `?session=…` the sidebar
  // re-renders with the correct highlight.
  const projectMatch = pathname.match(/^\/app\/project\/(\d+)/);
  const activeProjectId = projectMatch ? Number(projectMatch[1]) : null;
  const sessionParam = searchParams?.get("session") ?? null;
  const activeSessionId = sessionParam ? Number(sessionParam) : null;

  const fetchProjects = useCallback(
    () => api<AxiomProject[]>("/api/projects"),
    []
  );
  const { data: projectsRaw } = useCachedList<AxiomProject[]>(
    authed ? cacheKeys.projects() : null,
    fetchProjects
  );
  // Hide the auto-managed "Quick Chats" bucket from the visible tree —
  // the global "+ New chat" button still drops into it.
  const projects = useMemo(
    () => (projectsRaw || []).filter((p) => p.name !== "Quick Chats"),
    [projectsRaw]
  );

  const [me, setMe] = useState<AxiomUser | null>(null);
  useEffect(() => {
    if (!authed) return;
    api<AxiomUser>("/api/auth/me").then(setMe).catch(() => setMe(null));
  }, [authed]);
  const isAdmin = !!me?.is_admin;

  // Track which non-active projects the user has manually expanded.
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
  function toggleProject(id: number) {
    setOpenIds((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const newChat = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await api<QuickStartResponse>("/api/chats/quick", {
        method: "POST",
        json: {},
      });
      // The new chat is in the auto-managed Quick Chats project; refresh
      // both the projects list (in case it's brand new) and recent chats.
      await fetchProjects().then((p) => setCached(cacheKeys.projects(), p));
      router.push(`/app/project/${res.project_id}?session=${res.session_id}`);
    } catch {
      router.push("/app");
    } finally {
      setBusy(false);
    }
  }, [busy, router, fetchProjects]);

  if (authed === false) {
    // No token yet — render the static frame so layout doesn't jump.
    return <SidebarFrame onNewChat={newChat} busy={busy} />;
  }

  return (
    <SidebarFrame onNewChat={newChat} busy={busy}>
      <Section label="Projects">
        {projectsRaw === undefined ? (
          <Hint>Loading…</Hint>
        ) : projects.length === 0 ? (
          <Hint>No projects yet.</Hint>
        ) : (
          <ul className="space-y-0.5">
            {projects.map((p) => (
              <ProjectNode
                key={p.id}
                project={p}
                isActive={activeProjectId === p.id}
                isOpen={activeProjectId === p.id || openIds.has(p.id)}
                onToggle={() => toggleProject(p.id)}
                activeSessionId={activeProjectId === p.id ? activeSessionId : null}
              />
            ))}
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
    </SidebarFrame>
  );
}

/** Static layout shell — separated so we can render the same frame
 *  before auth resolves without running any data hooks. */
function SidebarFrame({
  onNewChat,
  busy,
  children,
}: {
  onNewChat: () => void;
  busy: boolean;
  children?: React.ReactNode;
}) {
  return (
    <aside className="border-r border-[var(--border)] bg-[var(--surface-alt)] p-4 text-sm flex flex-col gap-4 overflow-y-auto">
      <button
        onClick={onNewChat}
        disabled={busy}
        className="btn btn-primary text-sm justify-center w-full"
      >
        + New chat
      </button>
      {children}
    </aside>
  );
}

/**
 * One row in the projects tree. Owns its own chat-list fetch so a
 * collapsed project pays nothing. The active project is rendered with
 * its expanded sub-tree of chats, plus a Datasets section underneath
 * (datasets only fetched when the project is the active one).
 */
const ProjectNode = memo(function ProjectNode({
  project,
  isActive,
  isOpen,
  onToggle,
  activeSessionId,
}: {
  project: AxiomProject;
  isActive: boolean;
  isOpen: boolean;
  onToggle: () => void;
  activeSessionId: number | null;
}) {
  const router = useRouter();
  const pid = project.id;
  const headerActive = isActive;

  return (
    <li>
      <div
        className={`group flex items-center gap-1 rounded ${
          headerActive
            ? "bg-[var(--surface)]"
            : "hover:bg-[var(--surface)]"
        }`}
      >
        <button
          aria-label={isOpen ? "Collapse project" : "Expand project"}
          onClick={onToggle}
          className="p-1.5 text-[var(--text-muted)] hover:text-[var(--text)] shrink-0"
        >
          <ChevronRight
            className={`h-3 w-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
          />
        </button>
        <Link
          href={`/app/project/${pid}`}
          className={`flex-1 truncate text-xs py-1.5 pr-2 ${
            headerActive
              ? "font-semibold text-[var(--text)]"
              : "text-[var(--text)]"
          }`}
          title={project.name}
        >
          {project.name}
        </Link>
      </div>
      {isOpen && (
        <div className="ml-5 mt-0.5 mb-1 border-l border-[var(--border)] pl-2">
          <ProjectChatTree
            projectId={pid}
            activeSessionId={isActive ? activeSessionId : null}
            onPickSession={(sid) =>
              router.push(`/app/project/${pid}?session=${sid}`)
            }
          />
          {isActive && <ProjectDatasetList projectId={pid} />}
        </div>
      )}
    </li>
  );
});

/** Inline chat list for one project, fetched only when the project is
 *  expanded. Supports rename, delete, and "+ new chat" inline. */
const ProjectChatTree = memo(function ProjectChatTree({
  projectId,
  activeSessionId,
  onPickSession,
}: {
  projectId: number;
  activeSessionId: number | null;
  onPickSession: (sessionId: number) => void;
}) {
  const router = useRouter();
  const fetchChats = useCallback(
    () => api<ChatSession[]>(`/api/projects/${projectId}/chats`),
    [projectId]
  );
  const key = cacheKeys.projectChats(projectId);
  const { data: chats } = useCachedList<ChatSession[]>(key, fetchChats);
  const [busy, setBusy] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function newChat() {
    if (busy) return;
    setBusy(true);
    try {
      const created = await api<ChatSession>(
        `/api/projects/${projectId}/chats`,
        { method: "POST", json: { title: "New chat" } }
      );
      patchCached<ChatSession[]>(key, (cur) =>
        cur ? [created, ...cur] : [created]
      );
      router.push(`/app/project/${projectId}?session=${created.id}`);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function commitRename(id: number) {
    const title = renameValue.trim();
    if (!title) {
      setRenamingId(null);
      return;
    }
    try {
      const updated = await api<ChatSession>(`/api/chats/${id}`, {
        method: "PATCH",
        json: { title },
      });
      patchCached<ChatSession[]>(key, (cur) =>
        cur ? cur.map((s) => (s.id === id ? updated : s)) : []
      );
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setRenamingId(null);
    }
  }

  async function deleteChat(id: number) {
    if (!confirm("Delete this chat?")) return;
    try {
      await api(`/api/chats/${id}`, { method: "DELETE" });
      patchCached<ChatSession[]>(key, (cur) =>
        cur ? cur.filter((s) => s.id !== id) : []
      );
      if (activeSessionId === id) {
        // Pop to the project root; the workspace will pick the next one.
        router.replace(`/app/project/${projectId}`);
      }
    } catch (e) {
      setError(errMessage(e));
    }
  }

  return (
    <div>
      <button
        onClick={newChat}
        disabled={busy}
        className="w-full text-left text-[11px] text-[var(--text-muted)] hover:text-[var(--accent)] inline-flex items-center gap-1 px-2 py-1 rounded hover:bg-[var(--surface)]"
      >
        <MessageSquarePlus className="h-3 w-3" />
        New chat
      </button>
      {chats === undefined ? (
        <div className="text-[10px] text-[var(--text-muted)] px-2 py-1">
          Loading…
        </div>
      ) : chats.length === 0 ? (
        <div className="text-[10px] text-[var(--text-muted)] px-2 py-1">
          No chats yet
        </div>
      ) : (
        <ul className="space-y-0.5">
          {chats.map((s) => {
            const active = s.id === activeSessionId;
            const renaming = renamingId === s.id;
            return (
              <li
                key={s.id}
                className={`group flex items-center gap-1 rounded px-2 py-1 cursor-pointer ${
                  active
                    ? "bg-[var(--accent)] text-white"
                    : "hover:bg-[var(--surface)] text-[var(--text)]"
                }`}
                onClick={() => !renaming && onPickSession(s.id)}
              >
                {renaming ? (
                  <input
                    autoFocus
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onBlur={() => commitRename(s.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename(s.id);
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className="flex-1 px-1.5 py-0.5 text-[11px] rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
                  />
                ) : (
                  <>
                    <span
                      className="flex-1 truncate text-[11px]"
                      title={s.title}
                    >
                      {s.title || "Untitled chat"}
                    </span>
                    <button
                      aria-label="Rename chat"
                      className={`opacity-0 group-hover:opacity-100 p-0.5 rounded ${
                        active
                          ? "text-white/80 hover:text-white"
                          : "text-[var(--text-muted)] hover:text-[var(--accent)]"
                      }`}
                      onClick={(e) => {
                        e.stopPropagation();
                        setRenamingId(s.id);
                        setRenameValue(s.title);
                      }}
                    >
                      <Pencil className="h-2.5 w-2.5" />
                    </button>
                    <button
                      aria-label="Delete chat"
                      className={`opacity-0 group-hover:opacity-100 p-0.5 rounded ${
                        active
                          ? "text-white/80 hover:text-white"
                          : "text-[var(--text-muted)] hover:text-red-500"
                      }`}
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteChat(s.id);
                      }}
                    >
                      <Trash2 className="h-2.5 w-2.5" />
                    </button>
                  </>
                )}
              </li>
            );
          })}
        </ul>
      )}
      {error && (
        <div className="text-[10px] text-red-500 px-2 py-1">{error}</div>
      )}
      <Link
        href={`/app/project/${projectId}/report${activeSessionId ? `?session=${activeSessionId}` : ""}`}
        className="block mt-1 px-2 py-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] inline-flex items-center gap-1"
      >
        <FileText className="h-2.5 w-2.5" />
        Final report
      </Link>
    </div>
  );
});

/** Datasets attached to the active project — surfaced under the
 *  expanded project node. Clicking a dataset selects it as the chat's
 *  active dataset (mirrored to localStorage + an event). */
const ProjectDatasetList = memo(function ProjectDatasetList({
  projectId,
}: {
  projectId: number;
}) {
  const fetchDatasets = useCallback(async () => {
    const all = await api<AxiomDataset[]>("/api/datasets");
    return all.filter((d) => d.project_id === projectId);
  }, [projectId]);
  const key = cacheKeys.projectDatasets(projectId);
  const { data: datasets } = useCachedList<AxiomDataset[]>(key, fetchDatasets);

  // Listen for upload events from the chat composer and revalidate so
  // the new file shows up without a manual refresh.
  useEffect(() => {
    function onUploaded() {
      fetchDatasets()
        .then((rows) => setCached(key, rows))
        .catch(() => {
          /* user can retry */
        });
    }
    window.addEventListener("axiom:dataset:uploaded", onUploaded);
    return () => window.removeEventListener("axiom:dataset:uploaded", onUploaded);
  }, [fetchDatasets, key]);

  function pick(id: number) {
    setActiveDatasetId(id);
    window.dispatchEvent(
      new CustomEvent("axiom:dataset:active", { detail: { datasetId: id } })
    );
  }

  return (
    <div className="mt-2 pt-2 border-t border-[var(--border)]/60">
      <div className="font-mono text-[9px] tracking-widest uppercase text-[var(--text-muted)] px-2 mb-1 flex items-center gap-1">
        <Database className="h-2.5 w-2.5" />
        Datasets
      </div>
      {datasets === undefined ? (
        <div className="text-[10px] text-[var(--text-muted)] px-2 py-1">
          Loading…
        </div>
      ) : datasets.length === 0 ? (
        <div className="text-[10px] text-[var(--text-muted)] px-2 py-1">
          No data yet —{" "}
          <Link href="/app/upload" className="text-[var(--accent)] hover:underline">
            upload
          </Link>
        </div>
      ) : (
        <ul className="space-y-0.5">
          {datasets.map((d) => (
            <li key={d.id}>
              <button
                onClick={() => pick(d.id)}
                className="text-left w-full rounded px-2 py-1 text-[11px] hover:bg-[var(--surface)] text-[var(--text)]"
                title={`${d.rows.toLocaleString()} rows × ${d.cols} cols`}
              >
                <span className="truncate block">{d.dataset_name}</span>
                <span className="text-[9px] text-[var(--text-muted)] font-mono">
                  {d.rows.toLocaleString()} × {d.cols}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <Link
        href="/app/upload"
        className="block mt-1 px-2 py-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] inline-flex items-center gap-1"
      >
        <Plus className="h-2.5 w-2.5" />
        Upload more
      </Link>
    </div>
  );
});

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

// Memoize the export so chat composer state changes inside the right
// pane don't force a sidebar re-render.
export const ProductSidebar = memo(ProductSidebarBase);
