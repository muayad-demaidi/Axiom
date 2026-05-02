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
 * Mutations (new/rename/delete chat, new/rename/delete project,
 * dataset upload) update the cache via `setCached` / `patchCached`
 * so the UI reflects the change immediately without waiting for a
 * network round-trip.
 */
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ChevronRight,
  Database,
  FileText,
  MessageSquarePlus,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import { api, getToken } from "@/lib/api";
import { errMessage, type AxiomDataset, type AxiomProject, type AxiomUser } from "@/lib/types";
import { setActiveDatasetId, setChatSessionDatasetId } from "@/lib/projectContext";
import {
  cacheKeys,
  getCached,
  patchCached,
  setCached,
  useCachedItem,
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
  { href: "/app/join", label: "Join Datasets" },
  { href: "/app/fields", label: "Field Settings" },
];

function ProductSidebarBase() {
  const pathname = usePathname() || "";
  const searchParams = useSearchParams();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [authed, setAuthed] = useState<boolean | null>(null);
  // Section-level error surfaced under the Projects list when a
  // create/rename/delete request actually fails on the server. We keep
  // it inline (instead of an alert) so the user can keep working.
  const [projectError, setProjectError] = useState<string | null>(null);
  // The "+ New" split menu, plus its inline sub-flows.
  const [newMenuOpen, setNewMenuOpen] = useState(false);
  const [newProjectFormOpen, setNewProjectFormOpen] = useState(false);

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
  // the "+ New → Chat" menu still drops into it.
  const projects = useMemo(
    () => (projectsRaw || []).filter((p) => p.name !== "Quick Chats"),
    [projectsRaw]
  );

  // Read the user from the shared cache. ModeProvider fetches
  // `/api/auth/me` once at startup and stores it under
  // `cacheKeys.user()`, so the sidebar's mount no longer issues a second
  // request for the same payload.
  const me = useCachedItem<AxiomUser>(cacheKeys.user()) ?? null;
  const isAdmin = !!me?.is_admin;

  // Track which non-active projects the user has manually expanded.
  const [openIds, setOpenIds] = useState<Set<number>>(new Set());
  const toggleProject = useCallback((id: number) => {
    setOpenIds((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);
  // Stable `(id) => toggleProject(id)` reference passed to memoized
  // ProjectNode children so they can short-circuit re-renders on
  // unrelated state changes (e.g. the user typing in the chat composer).
  const handleToggle = useCallback(
    (id: number) => toggleProject(id),
    [toggleProject]
  );

  const newChat = useCallback(async () => {
    if (busy) return;
    setBusy(true);
    setProjectError(null);
    try {
      const res = await api<QuickStartResponse>("/api/chats/quick", {
        method: "POST",
        json: {},
      });
      // The new chat is in the auto-managed Quick Chats project; refresh
      // both the projects list (in case it's brand new) and recent chats.
      await fetchProjects().then((p) => setCached(cacheKeys.projects(), p));
      router.push(`/app/project/${res.project_id}?session=${res.session_id}`);
    } catch (e) {
      setProjectError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }, [busy, router, fetchProjects]);

  const newProject = useCallback(
    async (name: string, description: string) => {
      if (busy) return;
      const cleaned = name.trim();
      if (!cleaned) {
        setProjectError("Project name cannot be empty.");
        return;
      }
      setBusy(true);
      setProjectError(null);
      try {
        const created = await api<AxiomProject>("/api/projects", {
          method: "POST",
          json: { name: cleaned, description: description.trim() || null },
        });
        // Optimistically prepend to the cached list so the sidebar
        // reflects the new project before the next revalidate.
        patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
          [created, ...((cur || []).filter((p) => p.id !== created.id))]
        );
        setOpenIds((cur) => {
          const next = new Set(cur);
          next.add(created.id);
          return next;
        });
        setNewProjectFormOpen(false);
        setNewMenuOpen(false);
        router.push(`/app/project/${created.id}`);
      } catch (e) {
        setProjectError(errMessage(e));
      } finally {
        setBusy(false);
      }
    },
    [busy, router]
  );

  // Project rename + delete — these run from inside ProjectNode but
  // need to mutate the shared cache and (for delete) navigate the user
  // away if they're currently sitting on that project. Centralising
  // them here keeps the per-row component dumb.
  const renameProject = useCallback(
    async (project: AxiomProject, nextName: string): Promise<boolean> => {
      const cleaned = nextName.trim();
      if (!cleaned || cleaned === project.name) return true;
      setProjectError(null);
      try {
        const updated = await api<AxiomProject>(
          `/api/projects/${project.id}`,
          { method: "PATCH", json: { name: cleaned } }
        );
        patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
          (cur || []).map((p) =>
            p.id === project.id ? { ...p, ...updated, name: updated.name } : p
          )
        );
        return true;
      } catch (e) {
        setProjectError(errMessage(e));
        return false;
      }
    },
    []
  );

  const deleteProject = useCallback(
    async (project: AxiomProject): Promise<boolean> => {
      setProjectError(null);
      try {
        // Capture the chats *before* the delete so we can also tidy up
        // each session's `axiom_chat_dataset_<id>` localStorage entry.
        // The backend won't reuse those session ids, but clearing them
        // now stops the user's storage from accumulating dead keys
        // across many delete cycles.
        const cachedChats =
          getCached<ChatSession[]>(cacheKeys.projectChats(project.id)) ?? [];
        await api(`/api/projects/${project.id}`, { method: "DELETE" });
        patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
          (cur || []).filter((p) => p.id !== project.id)
        );
        // Any cached per-project lists must go too, otherwise stale
        // chats / datasets would resurrect the project on the next
        // workspace mount.
        setCached(cacheKeys.projectChats(project.id), []);
        setCached(cacheKeys.projectDatasets(project.id), []);
        for (const c of cachedChats) setChatSessionDatasetId(c.id, null);
        if (activeProjectId === project.id) {
          // Currently sitting on the project we just deleted — pop to
          // a safe destination instead of letting the workspace try
          // to render a 404'd id.
          router.replace("/app/projects");
        }
        return true;
      } catch (e) {
        setProjectError(errMessage(e));
        return false;
      }
    },
    [activeProjectId, router]
  );

  if (authed === false) {
    // No token yet — render the static frame so layout doesn't jump.
    return (
      <SidebarFrame
        newMenuOpen={false}
        onToggleNewMenu={() => {}}
        onPickNewChat={() => {}}
        onPickNewProject={() => {}}
        newProjectFormOpen={false}
        onCancelNewProject={() => {}}
        onSubmitNewProject={() => {}}
        busy={false}
      />
    );
  }

  return (
    <SidebarFrame
      newMenuOpen={newMenuOpen}
      onToggleNewMenu={() => {
        setNewMenuOpen((cur) => !cur);
        // Closing the menu also dismisses any half-filled inline form.
        if (newMenuOpen) setNewProjectFormOpen(false);
      }}
      onPickNewChat={() => {
        setNewMenuOpen(false);
        setNewProjectFormOpen(false);
        void newChat();
      }}
      onPickNewProject={() => {
        setNewProjectFormOpen(true);
        setNewMenuOpen(false);
      }}
      newProjectFormOpen={newProjectFormOpen}
      onCancelNewProject={() => {
        setNewProjectFormOpen(false);
        setProjectError(null);
      }}
      onSubmitNewProject={(name, desc) => void newProject(name, desc)}
      busy={busy}
    >
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
                onToggle={handleToggle}
                onRename={renameProject}
                onDelete={deleteProject}
                activeSessionId={activeProjectId === p.id ? activeSessionId : null}
              />
            ))}
          </ul>
        )}
        {projectError && (
          <div className="text-[10px] text-red-500 px-2 py-1 mt-1">
            {projectError}{" "}
            <button
              type="button"
              onClick={() => setProjectError(null)}
              className="underline ml-1"
            >
              dismiss
            </button>
          </div>
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
 *  before auth resolves without running any data hooks. The split
 *  "+ New" button lives here because the dropdown + inline create-
 *  project form are part of the persistent header, even when the
 *  child sections aren't rendered yet. */
function SidebarFrame({
  newMenuOpen,
  onToggleNewMenu,
  onPickNewChat,
  onPickNewProject,
  newProjectFormOpen,
  onCancelNewProject,
  onSubmitNewProject,
  busy,
  children,
}: {
  newMenuOpen: boolean;
  onToggleNewMenu: () => void;
  onPickNewChat: () => void;
  onPickNewProject: () => void;
  newProjectFormOpen: boolean;
  onCancelNewProject: () => void;
  onSubmitNewProject: (name: string, description: string) => void;
  busy: boolean;
  children?: React.ReactNode;
}) {
  return (
    <aside className="border-r border-[var(--border)] bg-[var(--surface-alt)] p-4 text-sm flex flex-col gap-4 overflow-y-auto">
      <NewSplitButton
        open={newMenuOpen}
        onToggle={onToggleNewMenu}
        onPickChat={onPickNewChat}
        onPickProject={onPickNewProject}
        busy={busy}
      />
      {newProjectFormOpen && (
        <NewProjectForm
          busy={busy}
          onCancel={onCancelNewProject}
          onSubmit={onSubmitNewProject}
        />
      )}
      {children}
    </aside>
  );
}

/** "+ New" split button + dropdown menu. Closes on outside click and on
 *  Escape. Designed to feel like part of the dark sidebar — small,
 *  accent-coloured, and quiet. */
function NewSplitButton({
  open,
  onToggle,
  onPickChat,
  onPickProject,
  busy,
}: {
  open: boolean;
  onToggle: () => void;
  onPickChat: () => void;
  onPickProject: () => void;
  busy: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) onToggle();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onToggle();
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onToggle]);

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={onToggle}
        disabled={busy}
        className="btn btn-primary text-sm justify-center w-full inline-flex items-center gap-1.5"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Plus className="h-3.5 w-3.5" />
        New
      </button>
      {open && (
        <div
          role="menu"
          className="absolute left-0 right-0 top-full mt-1 z-30 rounded-md border border-[var(--border)] bg-[var(--surface)] shadow-lg overflow-hidden"
        >
          <button
            type="button"
            role="menuitem"
            onClick={onPickProject}
            className="w-full text-left px-3 py-2 text-xs text-[var(--text)] hover:bg-[var(--surface-alt)] inline-flex items-center gap-2"
          >
            <FileText className="h-3 w-3 text-[var(--text-muted)]" />
            <div className="flex-1">
              <div className="font-medium">Project</div>
              <div className="text-[10px] text-[var(--text-muted)]">
                Group of chats with their own data
              </div>
            </div>
          </button>
          <div className="h-px bg-[var(--border)]" />
          <button
            type="button"
            role="menuitem"
            onClick={onPickChat}
            className="w-full text-left px-3 py-2 text-xs text-[var(--text)] hover:bg-[var(--surface-alt)] inline-flex items-center gap-2"
          >
            <MessageSquarePlus className="h-3 w-3 text-[var(--text-muted)]" />
            <div className="flex-1">
              <div className="font-medium">Chat</div>
              <div className="text-[10px] text-[var(--text-muted)]">
                Quick conversation in Quick Chats
              </div>
            </div>
          </button>
        </div>
      )}
    </div>
  );
}

/** Inline form rendered under the "+ New" button when the user picks
 *  the Project option. Submits via Enter, closes on Escape. */
function NewProjectForm({
  busy,
  onCancel,
  onSubmit,
}: {
  busy: boolean;
  onCancel: () => void;
  onSubmit: (name: string, description: string) => void;
}) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    inputRef.current?.focus();
  }, []);
  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    onSubmit(name, description);
  }
  return (
    <form
      onSubmit={submit}
      className="rounded-md border border-[var(--border)] bg-[var(--surface)] p-2.5 space-y-1.5"
    >
      <div className="font-mono text-[9px] uppercase tracking-widest text-[var(--text-muted)]">
        New project
      </div>
      <input
        ref={inputRef}
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
        }}
        placeholder="Project name…"
        className="w-full px-2 py-1.5 text-xs rounded border border-[var(--border)] bg-[var(--surface-alt)] text-[var(--text)]"
      />
      <input
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            e.preventDefault();
            onCancel();
          }
        }}
        placeholder="Description (optional)"
        className="w-full px-2 py-1.5 text-[11px] rounded border border-[var(--border)] bg-[var(--surface-alt)] text-[var(--text)]"
      />
      <div className="flex items-center gap-1.5 justify-end pt-0.5">
        <button
          type="button"
          onClick={onCancel}
          className="text-[11px] px-2 py-1 rounded text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-alt)]"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy || !name.trim()}
          className="btn btn-primary text-[11px] px-2 py-1 disabled:opacity-50"
        >
          Create
        </button>
      </div>
    </form>
  );
}

/**
 * One row in the projects tree. Owns its own chat-list fetch so a
 * collapsed project pays nothing. The active project is rendered with
 * its expanded sub-tree of chats, plus a Datasets section underneath
 * (datasets only fetched when the project is the active one).
 *
 * Hover-revealed pencil + trash icons mirror the chat row pattern so
 * project rename and delete are reachable without leaving the sidebar.
 */
const ProjectNode = memo(function ProjectNode({
  project,
  isActive,
  isOpen,
  onToggle,
  onRename,
  onDelete,
  activeSessionId,
}: {
  project: AxiomProject;
  isActive: boolean;
  isOpen: boolean;
  // Receives the project id so the parent can pass a single stable
  // callback for every row instead of an inline arrow per row (which
  // would otherwise defeat React.memo here).
  onToggle: (id: number) => void;
  onRename: (project: AxiomProject, nextName: string) => Promise<boolean>;
  onDelete: (project: AxiomProject) => Promise<boolean>;
  activeSessionId: number | null;
}) {
  const router = useRouter();
  const pid = project.id;
  const headerActive = isActive;
  const handleClick = useCallback(() => onToggle(pid), [onToggle, pid]);

  const [renaming, setRenaming] = useState(false);
  const [renameValue, setRenameValue] = useState(project.name);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  async function commitRename() {
    const ok = await onRename(project, renameValue);
    if (ok) setRenaming(false);
  }

  async function commitDelete() {
    setDeleting(true);
    const ok = await onDelete(project);
    setDeleting(false);
    if (ok) setConfirmingDelete(false);
  }

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
          onClick={handleClick}
          className="p-1.5 text-[var(--text-muted)] hover:text-[var(--text)] shrink-0"
        >
          <ChevronRight
            className={`h-3 w-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
          />
        </button>
        {renaming ? (
          <input
            autoFocus
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            onBlur={() => void commitRename()}
            onKeyDown={(e) => {
              if (e.key === "Enter") void commitRename();
              if (e.key === "Escape") {
                setRenameValue(project.name);
                setRenaming(false);
              }
            }}
            onClick={(e) => e.stopPropagation()}
            className="flex-1 px-1.5 py-0.5 text-xs rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
          />
        ) : (
          <Link
            href={`/app/project/${pid}`}
            className={`flex-1 truncate text-xs py-1.5 pr-1 ${
              headerActive
                ? "font-semibold text-[var(--text)]"
                : "text-[var(--text)]"
            }`}
            title={project.name}
          >
            {project.name}
          </Link>
        )}
        {!renaming && (
          <>
            <button
              aria-label="Rename project"
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-[var(--text-muted)] hover:text-[var(--accent)]"
              onClick={(e) => {
                e.stopPropagation();
                setRenameValue(project.name);
                setRenaming(true);
              }}
            >
              <Pencil className="h-2.5 w-2.5" />
            </button>
            <button
              aria-label="Delete project"
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded text-[var(--text-muted)] hover:text-red-500 mr-1"
              onClick={(e) => {
                e.stopPropagation();
                setConfirmingDelete(true);
              }}
            >
              <Trash2 className="h-2.5 w-2.5" />
            </button>
          </>
        )}
      </div>
      {confirmingDelete && (
        <div className="ml-5 mt-1 mb-1 rounded-md border border-red-500/40 bg-red-500/5 p-2 text-[11px]">
          <div className="text-[var(--text)]">
            Delete <span className="font-semibold">{project.name}</span>?
          </div>
          <div className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug">
            This permanently removes the project, every chat inside it,
            and any data context attached to those chats. This cannot be
            undone.
          </div>
          <div className="flex items-center gap-1.5 justify-end mt-1.5">
            <button
              type="button"
              onClick={() => setConfirmingDelete(false)}
              className="text-[11px] px-2 py-0.5 rounded text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-alt)]"
              disabled={deleting}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => void commitDelete()}
              disabled={deleting}
              className="text-[11px] px-2 py-0.5 rounded bg-red-500 text-white hover:bg-red-600 disabled:opacity-60"
            >
              {deleting ? "Deleting…" : "Delete"}
            </button>
          </div>
        </div>
      )}
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
 *  expanded. Supports rename, delete (with confirm), and "+ new chat"
 *  inline. */
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
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function newChat() {
    if (busy) return;
    setBusy(true);
    setError(null);
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

  async function commitDelete(id: number) {
    setDeletingId(id);
    setError(null);
    try {
      await api(`/api/chats/${id}`, { method: "DELETE" });
      patchCached<ChatSession[]>(key, (cur) =>
        cur ? cur.filter((s) => s.id !== id) : []
      );
      // Drop the per-session dataset binding so we don't leave dead
      // axiom_chat_dataset_<id> keys behind.
      setChatSessionDatasetId(id, null);
      setConfirmDeleteId(null);
      if (activeSessionId === id) {
        // Pop to the project root; the workspace will pick the next
        // session (or auto-create a fresh one).
        router.replace(`/app/project/${projectId}`);
      }
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setDeletingId(null);
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
            const confirming = confirmDeleteId === s.id;
            return (
              <li key={s.id}>
                <div
                  className={`group flex items-center gap-1 rounded px-2 py-1 cursor-pointer ${
                    active
                      ? "bg-[var(--accent)] text-white"
                      : "hover:bg-[var(--surface)] text-[var(--text)]"
                  }`}
                  onClick={() =>
                    !renaming && !confirming && onPickSession(s.id)
                  }
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
                          setConfirmDeleteId(s.id);
                        }}
                      >
                        <Trash2 className="h-2.5 w-2.5" />
                      </button>
                    </>
                  )}
                </div>
                {confirming && (
                  <div
                    className="ml-2 mt-1 rounded-md border border-red-500/40 bg-red-500/5 p-1.5 text-[10px]"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="text-[var(--text)]">
                      Delete this chat? Messages and any artifacts will
                      be removed.
                    </div>
                    <div className="flex items-center gap-1.5 justify-end mt-1">
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteId(null)}
                        disabled={deletingId === s.id}
                        className="text-[10px] px-1.5 py-0.5 rounded text-[var(--text-muted)] hover:text-[var(--text)]"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        onClick={() => commitDelete(s.id)}
                        disabled={deletingId === s.id}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-red-500 text-white hover:bg-red-600 disabled:opacity-60"
                      >
                        {deletingId === s.id ? "Deleting…" : "Delete"}
                      </button>
                    </div>
                  </div>
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
