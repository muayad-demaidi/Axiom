"use client";
/**
 * Projects management workspace: stats per card, hover kebab
 * (rename / archive / delete), multi-select bulk actions, search,
 * sort, and an Archived view. Active and archived lists live under
 * separate cache keys; mutations patch both so the sidebar and grid
 * stay in sync without a refetch.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Archive,
  ArchiveRestore,
  Check,
  CheckSquare,
  MoreVertical,
  Pencil,
  Search,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { api, ApiError, getToken } from "@/lib/api";
import type { AxiomProject } from "@/lib/types";
import { errMessage } from "@/lib/types";
import {
  setActiveProjectId,
  getActiveProjectId,
  setProjectMode,
  getProjectMode,
  type Mode,
} from "@/lib/projectContext";
import { cacheKeys, getCached, patchCached, setCached } from "@/lib/workspaceCache";

// ---- Helpers: formatting + filtering ----

type SortKey = "active" | "created" | "name" | "size";

const SORT_LABELS: Record<SortKey, string> = {
  active: "النشاط الأخير",
  created: "الإنشاء الأخير",
  name: "الاسم (أ–ي)",
  size: "إجمالي حجم البيانات",
};

function formatBytes(bytes: number | undefined | null): string {
  const n = Number(bytes ?? 0);
  if (!Number.isFinite(n) || n <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = n;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  // 1 decimal for KB+, integer for raw bytes.
  const formatted = i === 0 ? `${Math.round(value)}` : value.toFixed(1);
  return `${formatted} ${units[i]}`;
}

function formatRelative(iso: string | null | undefined): string {
  if (!iso) return "غير نشط بعد";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return "غير نشط بعد";
  const diff = Date.now() - t;
  if (diff < 0) return "الآن";
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return "الآن";
  const min = Math.floor(sec / 60);
  if (min < 60) return `قبل ${min} دقيقة`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `قبل ${hr} ساعة`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `قبل ${day} يوم`;
  const mo = Math.floor(day / 30);
  if (mo < 12) return `قبل ${mo} شهر`;
  const yr = Math.floor(day / 365);
  return `قبل ${yr} سنة`;
}

function statusColor(status: AxiomProject["status"]): string {
  switch (status) {
    case "processing":
      return "bg-amber-500";
    case "error":
      return "bg-red-500";
    default:
      return "bg-emerald-500";
  }
}

function statusLabel(status: AxiomProject["status"]): string {
  switch (status) {
    case "processing":
      return "قيد المعالجة";
    case "error":
      return "يوجد أخطاء";
    default:
      return "جاهز";
  }
}

function compareProjects(a: AxiomProject, b: AxiomProject, sort: SortKey): number {
  switch (sort) {
    case "name":
      return (a.name || "").localeCompare(b.name || "", undefined, {
        sensitivity: "base",
      });
    case "size":
      return (b.total_size_bytes ?? 0) - (a.total_size_bytes ?? 0);
    case "created": {
      const ta = a.created_at ? Date.parse(a.created_at) : 0;
      const tb = b.created_at ? Date.parse(b.created_at) : 0;
      return tb - ta;
    }
    case "active":
    default: {
      const ta = a.last_active_at ? Date.parse(a.last_active_at) : 0;
      const tb = b.last_active_at ? Date.parse(b.last_active_at) : 0;
      return tb - ta;
    }
  }
}

function isQuickChats(p: AxiomProject): boolean {
  return p.name === "Quick Chats";
}

// Toast surface — single transient banner shown above the grid for
// archive / restore actions so the user gets an "Undo" affordance.
type ToastSpec = {
  text: string;
  actionLabel?: string;
  onAction?: () => void;
};

// ---- Component ----

export default function ProjectsIndex() {
  const router = useRouter();
  const [active, setActive] = useState<AxiomProject[] | null>(null);
  const [archived, setArchived] = useState<AxiomProject[] | null>(null);
  const [view, setView] = useState<"active" | "archived">("active");
  const [error, setError] = useState<string | null>(null);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [modeTick, setModeTick] = useState(0);

  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<SortKey>("active");

  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [renameError, setRenameError] = useState<string | null>(null);
  const [openMenuId, setOpenMenuId] = useState<number | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<{
    project: AxiomProject;
    typed: string;
  } | null>(null);
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [toast, setToast] = useState<ToastSpec | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ---- Auth + initial load ----
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    setActiveId(getActiveProjectId());
    api<AxiomProject[]>("/api/projects")
      .then((arr) => {
        setCached(cacheKeys.projects(), arr);
        setActive(arr.filter((p) => !isQuickChats(p)));
      })
      .catch((e: ApiError) => {
        if (e.status === 401) router.push("/login");
        else setError(e.message);
      });
  }, [router]);

  // Lazy-load archived list the first time the user toggles to it; the
  // list is cached for the rest of the tab session so subsequent
  // toggles are instant.
  useEffect(() => {
    if (view !== "archived" || archived !== null) return;
    api<AxiomProject[]>("/api/projects?include_archived=true")
      .then((arr) => {
        const onlyArchived = arr.filter(
          (p) => p.is_archived && !isQuickChats(p)
        );
        setCached(cacheKeys.archivedProjects(), onlyArchived);
        setArchived(onlyArchived);
      })
      .catch((e: ApiError) => setError(e.message));
  }, [view, archived]);

  // Auto-dismiss toasts after 6s; long enough to reach for Undo.
  function showToast(spec: ToastSpec) {
    setToast(spec);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 6000);
  }

  // ---- Project rename + create ----
  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setBusy(true);
    try {
      const p = await api<AxiomProject>("/api/projects", {
        method: "POST",
        json: { name: newName.trim() },
      });
      setActive((arr) => [p, ...(arr ?? []).filter((x) => x.id !== p.id)]);
      patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) => [
        p,
        ...((cur || []).filter((x) => x.id !== p.id)),
      ]);
      setNewName("");
      pickActive(p.id);
      router.push(`/app/project/${p.id}`);
    } catch (e: unknown) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function commitRename(id: number) {
    const next = renameValue.trim();
    if (!next) {
      setRenameError("لا يمكن أن يكون الاسم فارغًا.");
      return;
    }
    // Snapshot the previous name so we can roll back if the API rejects
    // the rename (e.g. duplicate-name 409). Then optimistically update
    // local state + caches so the card reflects the new label
    // immediately — the round-trip just confirms it.
    const prevName = (() => {
      const fromActive = (active ?? []).find((p) => p.id === id);
      if (fromActive) return fromActive.name;
      const fromArchived = (archived ?? []).find((p) => p.id === id);
      return fromArchived ? fromArchived.name : null;
    })();
    const applyName = (name: string) => (p: AxiomProject) =>
      p.id === id ? { ...p, name } : p;
    // Local-helper: only patch a list cache that is already populated,
    // so a rename never materializes empty arrays into never-fetched
    // keys (which would suppress the consumer's first real fetch for
    // the stale window).
    const patchListIfCached = (
      key: string,
      fn: (p: AxiomProject) => AxiomProject
    ) => {
      if (getCached<AxiomProject[]>(key) === undefined) return;
      patchCached<AxiomProject[]>(key, (cur) => (cur || []).map(fn));
    };
    setActive((arr) => (arr ? arr.map(applyName(next)) : null));
    setArchived((arr) => (arr ? arr.map(applyName(next)) : null));
    patchListIfCached(cacheKeys.projects(), applyName(next));
    patchListIfCached(cacheKeys.archivedProjects(), applyName(next));
    setRenamingId(null);
    setRenameError(null);
    try {
      const updated = await api<AxiomProject>(`/api/projects/${id}`, {
        method: "PATCH",
        json: { name: next },
      });
      // Merge the server's authoritative response so any normalised
      // fields (trimmed name, updated_at) reflect on screen without
      // blanking the rollup stats we already had.
      const merge = (p: AxiomProject) =>
        p.id === id ? { ...p, ...updated, name: updated.name } : p;
      setActive((arr) => (arr ? arr.map(merge) : null));
      setArchived((arr) => (arr ? arr.map(merge) : null));
      patchListIfCached(cacheKeys.projects(), merge);
      patchListIfCached(cacheKeys.archivedProjects(), merge);
    } catch (e: unknown) {
      // Roll back the optimistic name and surface the error as a toast
      // so the cards don't lie about persisted state.
      if (prevName != null) {
        const restore = applyName(prevName);
        setActive((arr) => (arr ? arr.map(restore) : null));
        setArchived((arr) => (arr ? arr.map(restore) : null));
        patchListIfCached(cacheKeys.projects(), restore);
        patchListIfCached(cacheKeys.archivedProjects(), restore);
      }
      showToast({ text: `تعذّرت إعادة التسمية: ${errMessage(e)}` });
    }
  }

  // ---- Archive / restore / delete (single + bulk) ----
  function dropFromActiveCache(ids: number[]) {
    setActive((arr) => (arr ?? []).filter((p) => !ids.includes(p.id)));
    patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
      (cur || []).filter((p) => !ids.includes(p.id))
    );
    // If the user just removed (or archived) the project they're
    // actively working in, clear the breadcrumb so the rest of the app
    // doesn't keep pointing at a now-gone id.
    const cur = getActiveProjectId();
    if (cur != null && ids.includes(cur)) {
      setActiveProjectId(null);
      setActiveId(null);
    }
  }

  async function archiveOne(p: AxiomProject) {
    // Optimistic move: drop from the active grid + cache, drop into the
    // archived list + cache, then fire the POST in the background. If
    // the API rejects, restore the row to the active list and show the
    // error in a non-blocking toast. The rollup stats survive the
    // round-trip because the optimistic row is the existing object
    // marked `is_archived: true`; the server response only fills in
    // `archived_at`.
    const optimistic: AxiomProject = { ...p, is_archived: true };
    dropFromActiveCache([p.id]);
    setArchived((arr) =>
      arr ? [optimistic, ...arr.filter((x) => x.id !== p.id)] : null
    );
    // Only insert into the archived cache if it's already populated.
    // Materializing a one-row list into a never-fetched key would
    // suppress the consumer's first real fetch for the stale window.
    if (getCached<AxiomProject[]>(cacheKeys.archivedProjects()) !== undefined) {
      patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
        cur ? [optimistic, ...cur.filter((x) => x.id !== p.id)] : [optimistic]
      );
    }
    // Track the in-flight archive promise so a quick Undo doesn't
    // race ahead of the archive POST and accidentally call /restore
    // before the row is archived on the server (which would 4xx and
    // leave the UI inconsistent). The Undo handler awaits this before
    // firing restore.
    const inflight = (async (): Promise<"ok" | "fail"> => {
      try {
        const archivedRow = await api<AxiomProject>(
          `/api/projects/${p.id}/archive`,
          { method: "POST" }
        );
        const merged = { ...optimistic, ...archivedRow, is_archived: true };
        setArchived((arr) =>
          arr ? arr.map((x) => (x.id === p.id ? merged : x)) : null
        );
        if (getCached<AxiomProject[]>(cacheKeys.archivedProjects()) !== undefined) {
          patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
            (cur || []).map((x) => (x.id === p.id ? merged : x))
          );
        }
        return "ok";
      } catch (e: unknown) {
        // Roll back: yank the row from archived and put the original
        // back at the head of the active list / cache. Preserve the
        // tri-state (null = not-yet-loaded) on archived so the next
        // tab open still triggers the initial fetch.
        setArchived((arr) =>
          arr ? arr.filter((x) => x.id !== p.id) : null
        );
        if (getCached<AxiomProject[]>(cacheKeys.archivedProjects()) !== undefined) {
          patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
            (cur || []).filter((x) => x.id !== p.id)
          );
        }
        setActive((arr) =>
          arr ? [p, ...arr.filter((x) => x.id !== p.id)] : null
        );
        patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
          cur ? [p, ...cur.filter((x) => x.id !== p.id)] : [p]
        );
        showToast({ text: `تعذّرت الأرشفة: ${errMessage(e)}` });
        return "fail";
      }
    })();
    showToast({
      text: `تمّت أرشفة "${p.name}".`,
      actionLabel: "تراجع",
      onAction: async () => {
        // Wait for the archive POST to settle so /restore has something
        // to operate on; if archive itself failed, the rollback already
        // ran above so there's nothing left to undo.
        const result = await inflight;
        if (result === "ok") {
          void restoreOne(optimistic, { silent: true });
        }
      },
    });
    await inflight;
  }

  async function restoreOne(
    p: AxiomProject,
    opts: { silent?: boolean } = {}
  ) {
    const optimistic: AxiomProject = { ...p, is_archived: false, archived_at: null };
    // Preserve tri-state on archived: null means "not yet fetched" and
    // the next archived-tab open should still trigger the initial load.
    setArchived((arr) => (arr ? arr.filter((x) => x.id !== p.id) : null));
    if (getCached<AxiomProject[]>(cacheKeys.archivedProjects()) !== undefined) {
      patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
        (cur || []).filter((x) => x.id !== p.id)
      );
    }
    setActive((arr) =>
      arr ? [optimistic, ...arr.filter((x) => x.id !== p.id)] : null
    );
    patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
      cur ? [optimistic, ...cur.filter((x) => x.id !== p.id)] : [optimistic]
    );
    if (!opts.silent) {
      showToast({ text: `تمّ استعادة "${p.name}".` });
    } else {
      setToast(null);
    }
    try {
      const restored = await api<AxiomProject>(
        `/api/projects/${p.id}/restore`,
        { method: "POST" }
      );
      const merged = { ...optimistic, ...restored, is_archived: false };
      setActive((arr) =>
        arr ? arr.map((x) => (x.id === p.id ? merged : x)) : null
      );
      patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
        (cur || []).map((x) => (x.id === p.id ? merged : x))
      );
    } catch (e: unknown) {
      // Roll back: re-archive the row and remove it from the active
      // list / cache. Same tri-state preservation as the optimistic
      // path — never materialize null lists into empty arrays.
      setActive((arr) => (arr ? arr.filter((x) => x.id !== p.id) : null));
      if (getCached<AxiomProject[]>(cacheKeys.projects()) !== undefined) {
        patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) =>
          (cur || []).filter((x) => x.id !== p.id)
        );
      }
      setArchived((arr) =>
        arr ? [p, ...arr.filter((x) => x.id !== p.id)] : null
      );
      if (getCached<AxiomProject[]>(cacheKeys.archivedProjects()) !== undefined) {
        patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
          cur ? [p, ...cur.filter((x) => x.id !== p.id)] : [p]
        );
      }
      showToast({ text: `تعذّر الاستعادة: ${errMessage(e)}` });
    }
  }

  async function deleteOne(p: AxiomProject) {
    try {
      await api(`/api/projects/${p.id}`, { method: "DELETE" });
      dropFromActiveCache([p.id]);
      setArchived((arr) => (arr ?? []).filter((x) => x.id !== p.id));
      patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
        (cur || []).filter((x) => x.id !== p.id)
      );
      setSelected((cur) => {
        if (!cur.has(p.id)) return cur;
        const next = new Set(cur);
        next.delete(p.id);
        return next;
      });
      setConfirmDelete(null);
      showToast({ text: `تمّ حذف "${p.name}".` });
    } catch (e: unknown) {
      setError(errMessage(e));
    }
  }

  type BulkAction = "delete" | "archive" | "restore";
  async function bulkAction(action: BulkAction) {
    const ids = Array.from(selected);
    if (ids.length === 0) return;
    try {
      const res = await api<{ action: string; processed: number[] }>(
        "/api/projects/bulk",
        { method: "POST", json: { action, project_ids: ids } }
      );
      const done = new Set(res.processed);
      if (action === "delete") {
        dropFromActiveCache(res.processed);
        setArchived((arr) => (arr ?? []).filter((p) => !done.has(p.id)));
        patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
          (cur || []).filter((p) => !done.has(p.id))
        );
        showToast({ text: `تمّ حذف ${res.processed.length} مشروع.` });
      } else if (action === "archive") {
        // Move acted-on rows from active → archived list.
        const moving = (active ?? []).filter((p) => done.has(p.id));
        dropFromActiveCache(res.processed);
        const merged = moving.map((p) => ({ ...p, is_archived: true }));
        setArchived((arr) =>
          arr
            ? [
                ...merged,
                ...arr.filter((x) => !merged.some((m) => m.id === x.id)),
              ]
            : null
        );
        patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) => {
          const base = cur || [];
          return [
            ...merged,
            ...base.filter((x) => !merged.some((m) => m.id === x.id)),
          ];
        });
        showToast({ text: `تمّت أرشفة ${res.processed.length} مشروع.` });
      } else if (action === "restore") {
        const moving = (archived ?? []).filter((p) => done.has(p.id));
        const merged = moving.map((p) => ({ ...p, is_archived: false }));
        setArchived((arr) => (arr ?? []).filter((p) => !done.has(p.id)));
        patchCached<AxiomProject[]>(cacheKeys.archivedProjects(), (cur) =>
          (cur || []).filter((p) => !done.has(p.id))
        );
        setActive((arr) =>
          arr
            ? [
                ...merged,
                ...arr.filter((x) => !merged.some((m) => m.id === x.id)),
              ]
            : null
        );
        patchCached<AxiomProject[]>(cacheKeys.projects(), (cur) => {
          const base = cur || [];
          return [
            ...merged,
            ...base.filter((x) => !merged.some((m) => m.id === x.id)),
          ];
        });
        showToast({ text: `تمّ استعادة ${res.processed.length} مشروع.` });
      }
      setSelected(new Set());
      setConfirmBulkDelete(false);
    } catch (e: unknown) {
      setError(errMessage(e));
    }
  }

  // ---- Active project + mode ----
  function pickActive(id: number) {
    setActiveProjectId(id);
    setActiveId(id);
  }

  function chooseMode(id: number, m: Mode) {
    pickActive(id);
    setProjectMode(id, m);
    setModeTick((t) => t + 1);
  }

  function openProject(p: AxiomProject) {
    pickActive(p.id);
    if (p.last_session_id) {
      router.push(`/app/project/${p.id}?session=${p.last_session_id}`);
    } else {
      router.push(`/app/project/${p.id}`);
    }
  }

  // ---- Derived list (search + sort + view) ----
  const visible = useMemo(() => {
    const base = view === "archived" ? archived ?? [] : active ?? [];
    const q = search.trim().toLowerCase();
    const filtered = q
      ? base.filter((p) => (p.name || "").toLowerCase().includes(q))
      : base;
    return [...filtered].sort((a, b) => compareProjects(a, b, sort));
  }, [active, archived, view, search, sort]);

  const selectedCount = selected.size;

  function toggleSelect(id: number) {
    setSelected((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function clearSelection() {
    setSelected(new Set());
  }

  // Close kebab menus on global click — simpler than juggling refs per
  // card. The button itself stops propagation when toggling.
  useEffect(() => {
    function onClick() {
      setOpenMenuId(null);
    }
    if (openMenuId == null) return;
    window.addEventListener("click", onClick);
    return () => window.removeEventListener("click", onClick);
  }, [openMenuId]);

  return (
    <div className="max-w-5xl" dir="rtl">
      <span className="eyebrow">مساحة العمل</span>
      <h1 className="text-2xl md:text-3xl font-bold mt-2">مشاريعك</h1>
      <p className="text-[var(--text-muted)] mt-2 text-sm">
        كل مشروع يحتفظ ببياناته وسجلّ محادثاته. مرّر فوق البطاقة لإظهار
        إعادة التسمية والأرشفة والحذف. استخدم مربّعات الاختيار لأداء عمليات
        على عدة مشاريع دفعة واحدة.
      </p>

      <form onSubmit={createProject} className="mt-6 flex gap-2">
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="اسم مشروع جديد…"
          aria-label="اسم المشروع"
          className="flex-1 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          style={{ minHeight: 44 }}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={busy || !newName.trim()}
          style={{ minHeight: 44 }}
        >
          إنشاء
        </button>
      </form>

      {error && (
        <div className="text-red-600 text-sm mt-4 flex items-center gap-2 rounded border border-red-500/30 bg-red-500/10 px-3 py-2" role="alert">
          {error}
          <button
            onClick={() => setError(null)}
            className="text-[var(--text-muted)] hover:text-[var(--text)] inline-flex items-center justify-center"
            style={{ minHeight: 32, minWidth: 32 }}
            aria-label="إخفاء الخطأ"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      {/* Toolbar: search, sort, view toggle */}
      <div className="mt-6 flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-[var(--text-muted)]" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="ابحث في المشاريع…"
            aria-label="البحث في المشاريع"
            className="w-full pl-7 pr-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
            style={{ minHeight: 44 }}
          />
        </div>
        <label className="text-[12px] text-[var(--text-muted)]">
          <span className="sr-only">الترتيب حسب</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="px-2 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          >
            {(Object.keys(SORT_LABELS) as SortKey[]).map((k) => (
              <option key={k} value={k}>
                {SORT_LABELS[k]}
              </option>
            ))}
          </select>
        </label>
        <div className="inline-flex rounded border border-[var(--border)] overflow-hidden">
          <button
            type="button"
            onClick={() => {
              setView("active");
              setSelected(new Set());
            }}
            data-active={view === "active"}
            className="mode-seg !rounded-none !border-0 px-3 py-2"
            aria-pressed={view === "active"}
            style={{ minHeight: 44 }}
          >
            النشطة
          </button>
          <button
            type="button"
            onClick={() => {
              setView("archived");
              setSelected(new Set());
            }}
            data-active={view === "archived"}
            className="mode-seg !rounded-none !border-0 px-3 py-2"
            aria-pressed={view === "archived"}
            style={{ minHeight: 44 }}
          >
            المؤرشفة
          </button>
        </div>
      </div>

      {/* Bulk action bar */}
      {selectedCount > 0 && (
        <div className="mt-4 sticky top-2 z-10 card flex flex-wrap items-center gap-2 px-3 py-2 border-[var(--accent)]/40 ring-1 ring-[var(--accent)]/30">
          <span className="text-sm font-semibold">
            {selectedCount} محدَّد
          </span>
          {view === "active" ? (
            <>
              <button
                type="button"
                onClick={() => bulkAction("archive")}
                className="btn btn-ghost text-[12px]"
                style={{ minHeight: 44 }}
              >
                <Archive className="h-3 w-3" /> أرشفة
              </button>
              <button
                type="button"
                onClick={() => setConfirmBulkDelete(true)}
                className="btn btn-ghost text-[12px] text-red-500 hover:text-red-600"
                style={{ minHeight: 44 }}
              >
                <Trash2 className="h-3 w-3" /> حذف
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={() => bulkAction("restore")}
                className="btn btn-ghost text-[12px]"
                style={{ minHeight: 44 }}
              >
                <ArchiveRestore className="h-3 w-3" /> استعادة
              </button>
              <button
                type="button"
                onClick={() => setConfirmBulkDelete(true)}
                className="btn btn-ghost text-[12px] text-red-500 hover:text-red-600"
                style={{ minHeight: 44 }}
              >
                <Trash2 className="h-3 w-3" /> حذف
              </button>
            </>
          )}
          <button
            type="button"
            onClick={clearSelection}
            className="btn btn-ghost text-[12px] ml-auto"
            style={{ minHeight: 44 }}
          >
            مسح التحديد
          </button>
        </div>
      )}

      {/* Toast banner */}
      {toast && (
        <div className="mt-4 card flex items-center gap-3 px-3 py-2 text-sm">
          <span className="flex-1">{toast.text}</span>
          {toast.actionLabel && toast.onAction && (
            <button
              type="button"
              onClick={() => {
                toast.onAction?.();
                setToast(null);
              }}
              className="text-[var(--accent)] hover:underline text-xs font-semibold"
            >
              {toast.actionLabel}
            </button>
          )}
          <button
            type="button"
            onClick={() => setToast(null)}
            className="text-[var(--text-muted)] hover:text-[var(--text)] inline-flex items-center justify-center"
            style={{ minHeight: 32, minWidth: 32 }}
            aria-label="إخفاء"
          >
            <X className="h-3 w-3" />
          </button>
        </div>
      )}

      <section className="mt-6">
        {visible === null || (view === "archived" && archived === null) || (view === "active" && active === null) ? (
          <div className="card text-[var(--text-muted)] text-sm inline-flex items-center gap-2" role="status" aria-live="polite">
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]" aria-hidden="true" />
            جاري التحميل…
          </div>
        ) : visible.length === 0 ? (
          <div className="card text-[var(--text-muted)] text-sm text-center p-6" role="status">
            <div className="text-2xl mb-2" aria-hidden="true">📁</div>
            {view === "archived"
              ? "لا توجد مشاريع مؤرشفة."
              : search
              ? `لا توجد مشاريع تطابق "${search}".`
              : "لا توجد مشاريع بعد. أنشئ مشروعًا أعلاه للبدء."}
          </div>
        ) : (
          <ul className="grid gap-3 md:grid-cols-2">
            {visible.map((p) => {
              const mode = getProjectMode(p.id);
              const cardActive = activeId === p.id && view === "active";
              const isSelected = selected.has(p.id);
              const renaming = renamingId === p.id;
              const handleBodyClick = (e: React.MouseEvent) => {
                if (renaming) return;
                if (view === "archived") return;
                // Anything explicitly opted out of body navigation (the
                // kebab menu, checkbox, mode picker, action buttons,
                // inline rename input) flags itself with
                // ``data-noopen="true"`` so we can ignore clicks that
                // originate inside it. This keeps the spec promise of
                // "click the body anywhere to resume the project"
                // without us having to stopPropagation on every leaf.
                const target = e.target as HTMLElement | null;
                if (target?.closest("[data-noopen='true']")) return;
                openProject(p);
              };
              return (
                <li
                  key={`${p.id}-${modeTick}`}
                  onClick={handleBodyClick}
                  className={`card group relative ${
                    view === "archived" || renaming
                      ? ""
                      : "cursor-pointer hover:border-[var(--accent)]/40"
                  } ${cardActive ? "ring-2 ring-[var(--accent)]" : ""} ${
                    isSelected ? "ring-1 ring-[var(--accent)]/60" : ""
                  }`}
                >
                  {/* Selection checkbox + kebab menu — both sit in the
                      top-right corner. The checkbox is always visible
                      so multi-select discoverability doesn't depend on
                      hover (especially on touch). */}
                  <div
                    data-noopen="true"
                    className="absolute top-3 right-3 flex items-center gap-1"
                  >
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        toggleSelect(p.id);
                      }}
                      aria-label={
                        isSelected ? "إلغاء تحديد المشروع" : "تحديد المشروع"
                      }
                      className={`p-1 rounded ${
                        isSelected
                          ? "text-[var(--accent)]"
                          : "text-[var(--text-muted)] opacity-60 group-hover:opacity-100 hover:text-[var(--text)]"
                      }`}
                    >
                      {isSelected ? (
                        <CheckSquare className="h-4 w-4" />
                      ) : (
                        <Square className="h-4 w-4" />
                      )}
                    </button>
                    <div className="relative">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpenMenuId((cur) => (cur === p.id ? null : p.id));
                        }}
                        aria-label="إجراءات المشروع"
                        className="p-1 rounded text-[var(--text-muted)] opacity-60 group-hover:opacity-100 hover:text-[var(--text)] hover:bg-[var(--surface)]"
                      >
                        <MoreVertical className="h-4 w-4" />
                      </button>
                      {openMenuId === p.id && (
                        <div
                          className="absolute right-0 top-7 z-20 min-w-[160px] rounded-md border border-[var(--border)] bg-[var(--surface)] shadow-lg text-sm py-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            onClick={() => {
                              setRenamingId(p.id);
                              setRenameValue(p.name);
                              setRenameError(null);
                              setOpenMenuId(null);
                            }}
                            className="flex w-full items-center gap-2 px-3 py-1.5 hover:bg-[var(--surface-alt)]"
                          >
                            <Pencil className="h-3 w-3" /> إعادة تسمية
                          </button>
                          {p.is_archived ? (
                            <button
                              type="button"
                              onClick={() => {
                                setOpenMenuId(null);
                                restoreOne(p);
                              }}
                              className="flex w-full items-center gap-2 px-3 py-1.5 hover:bg-[var(--surface-alt)]"
                            >
                              <ArchiveRestore className="h-3 w-3" /> استعادة
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => {
                                setOpenMenuId(null);
                                archiveOne(p);
                              }}
                              className="flex w-full items-center gap-2 px-3 py-1.5 hover:bg-[var(--surface-alt)]"
                            >
                              <Archive className="h-3 w-3" /> أرشفة
                            </button>
                          )}
                          <button
                            type="button"
                            onClick={() => {
                              setOpenMenuId(null);
                              setConfirmDelete({ project: p, typed: "" });
                            }}
                            className="flex w-full items-center gap-2 px-3 py-1.5 text-red-500 hover:bg-[var(--surface-alt)]"
                          >
                            <Trash2 className="h-3 w-3" /> حذف
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Card body */}
                  <div className="pr-16">
                    <div className="flex items-start gap-2">
                      <span
                        className={`mt-1.5 inline-block h-2 w-2 rounded-full ${statusColor(
                          p.status
                        )}`}
                        title={statusLabel(p.status)}
                        aria-label={statusLabel(p.status)}
                      />
                      <div className="flex-1 min-w-0">
                        {renaming ? (
                          <input
                            data-noopen="true"
                            autoFocus
                            value={renameValue}
                            onChange={(e) => {
                              setRenameValue(e.target.value);
                              setRenameError(null);
                            }}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") commitRename(p.id);
                              if (e.key === "Escape") {
                                setRenamingId(null);
                                setRenameError(null);
                              }
                            }}
                            className="w-full px-2 py-1 text-sm rounded border border-[var(--accent)] bg-[var(--surface)]"
                          />
                        ) : (
                          <h3 className="truncate" title={p.name}>
                            {p.name}
                          </h3>
                        )}
                        <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
                          {p.sheet_count ?? 0} مجموعة بيانات
                          {" · "}
                          {p.chat_count ?? 0} محادثة
                          {" · "}
                          {formatBytes(p.total_size_bytes)}
                        </p>
                        <p className="text-[12px] text-[var(--text-muted)] mt-0.5">
                          {p.is_archived
                            ? `أُرشف ${formatRelative(p.archived_at)}`
                            : `آخر نشاط ${formatRelative(p.last_active_at)}`}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Inline rename actions */}
                  {renaming && (
                    <div
                      data-noopen="true"
                      className="mt-2 flex items-center gap-2 pr-16"
                    >
                      <button
                        type="button"
                        onClick={() => commitRename(p.id)}
                        className="btn btn-primary text-[12px]"
                        style={{ minHeight: 44 }}
                      >
                        <Check className="h-3 w-3" /> حفظ
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          setRenamingId(null);
                          setRenameError(null);
                        }}
                        className="btn btn-ghost text-[12px]"
                        style={{ minHeight: 44 }}
                      >
                        إلغاء
                      </button>
                      {renameError && (
                        <span className="text-xs text-red-500">
                          {renameError}
                        </span>
                      )}
                    </div>
                  )}

                  {!p.is_archived && (
                    <div
                      data-noopen="true"
                      className="mt-4 flex flex-wrap items-center gap-2"
                    >
                      <span className="text-[12px] font-mono uppercase tracking-widest text-[var(--text-muted)] ml-1">
                        الوضع
                      </span>
                      <button
                        type="button"
                        onClick={() => chooseMode(p.id, "guided")}
                        data-active={mode === "guided"}
                        className="mode-seg"
                        aria-pressed={mode === "guided"}
                      >
                        موجَّه
                      </button>
                      <button
                        type="button"
                        onClick={() => chooseMode(p.id, "expert")}
                        data-active={mode === "expert"}
                        className="mode-seg"
                        aria-pressed={mode === "expert"}
                      >
                        خبير
                      </button>
                      {cardActive && (
                        <span className="mr-auto text-[12px] font-mono text-[var(--accent)]">
                          نشط
                        </span>
                      )}
                    </div>
                  )}

                  <div data-noopen="true" className="mt-4 flex gap-2">
                    {p.is_archived ? (
                      <button
                        type="button"
                        onClick={() => restoreOne(p)}
                        className="btn btn-primary text-[12px]"
                        style={{ minHeight: 44 }}
                      >
                        <ArchiveRestore className="h-3 w-3" /> استعادة
                      </button>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => openProject(p)}
                          className="btn btn-primary text-[12px]"
                          style={{ minHeight: 44 }}
                        >
                          فتح
                        </button>
                        <Link
                          href="/app/upload"
                          onClick={() => pickActive(p.id)}
                          className="btn btn-ghost text-[12px]"
                          style={{ minHeight: 44 }}
                        >
                          رفع بيانات
                        </Link>
                      </>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {/* Single-project delete confirmation modal */}
      {confirmDelete && (
        <ConfirmDeleteModal
          project={confirmDelete.project}
          typed={confirmDelete.typed}
          onTyped={(v) =>
            setConfirmDelete((cur) =>
              cur ? { ...cur, typed: v } : cur
            )
          }
          onCancel={() => setConfirmDelete(null)}
          onConfirm={() => deleteOne(confirmDelete.project)}
        />
      )}

      {/* Bulk delete confirmation modal */}
      {confirmBulkDelete && (
        <BulkConfirmDeleteModal
          count={selectedCount}
          onCancel={() => setConfirmBulkDelete(false)}
          onConfirm={() => bulkAction("delete")}
        />
      )}
    </div>
  );
}

// ---- Modal helpers ----

function ModalShell({
  title,
  children,
  onCancel,
}: {
  title: string;
  children: React.ReactNode;
  onCancel: () => void;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4"
      onClick={onCancel}
    >
      <div
        className="card max-w-md w-full"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-semibold mb-2">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function ConfirmDeleteModal({
  project,
  typed,
  onTyped,
  onCancel,
  onConfirm,
}: {
  project: AxiomProject;
  typed: string;
  onTyped: (v: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  // Require typing the project name to confirm — guards against the
  // worst case of accidentally nuking a project full of work.
  const matches = typed.trim() === project.name.trim();
  return (
    <ModalShell title="حذف المشروع" onCancel={onCancel}>
      <div dir="rtl">
      <p className="text-sm text-[var(--text-muted)]">
        سيؤدّي هذا إلى حذف{" "}
        <span className="font-semibold text-[var(--text)]">
          {project.name}
        </span>
        {" "}نهائيًا، بما في ذلك كل البيانات وسجلّ المحادثات. لا يمكن التراجع عن ذلك.
      </p>
      <p className="text-[12px] text-[var(--text-muted)] mt-3">
        للتأكيد، اكتب اسم المشروع أدناه.
      </p>
      <input
        autoFocus
        value={typed}
        onChange={(e) => onTyped(e.target.value)}
        placeholder={project.name}
        className="mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
        style={{ minHeight: 44 }}
      />
      <div className="mt-4 flex justify-start gap-2">
        <button onClick={onCancel} className="btn btn-ghost text-[12px]" style={{ minHeight: 44 }}>
          إلغاء
        </button>
        <button
          onClick={onConfirm}
          disabled={!matches}
          className="btn btn-primary text-[12px] !bg-red-600 hover:!bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ minHeight: 44 }}
        >
          نعم، متأكد
        </button>
      </div>
      </div>
    </ModalShell>
  );
}

function BulkConfirmDeleteModal({
  count,
  onCancel,
  onConfirm,
}: {
  count: number;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <ModalShell title="حذف المشاريع" onCancel={onCancel}>
      <div dir="rtl">
      <p className="text-sm text-[var(--text-muted)]">
        سيؤدّي هذا إلى حذف{" "}
        <span className="font-semibold text-[var(--text)]">
          {count} مشروع
        </span>
        {" "}نهائيًا، بما في ذلك جميع البيانات وسجلّ المحادثات داخلها. لا يمكن التراجع عن ذلك.
      </p>
      <div className="mt-4 flex justify-start gap-2">
        <button onClick={onCancel} className="btn btn-ghost text-[12px]" style={{ minHeight: 44 }}>
          إلغاء
        </button>
        <button
          onClick={onConfirm}
          className="btn btn-primary text-[12px] !bg-red-600 hover:!bg-red-700"
          style={{ minHeight: 44 }}
        >
          نعم، متأكد · حذف {count}
        </button>
      </div>
      </div>
    </ModalShell>
  );
}
