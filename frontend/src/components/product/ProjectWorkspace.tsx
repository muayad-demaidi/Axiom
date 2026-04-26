"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { api, ApiError, getToken } from "@/lib/api";
import { errMessage, type AxiomDataset, type AxiomProject } from "@/lib/types";
import { setActiveProjectId, setActiveDatasetId, getActiveDatasetId } from "@/lib/projectContext";
import {
  cacheKeys,
  setCached,
  useCachedList,
} from "@/lib/workspaceCache";
import { ChatPanel } from "@/components/product/ChatPanel";
import { DatasetPreviewCard } from "@/components/product/DatasetPreviewCard";
import { DataContextBar } from "@/components/product/DataContextBar";
import { ArtifactDrawer, type PendingTool } from "@/components/product/ArtifactDrawer";
import { OpenQuestionsBar } from "@/components/product/OpenQuestionsBar";
import { ModeToggle } from "@/components/product/ModeToggle";
import { useMode } from "@/lib/modeContext";

type ChatSession = {
  id: number;
  project_id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
};

const DRAWER_PREF_KEY = "axiom_drawer_open";

export function ProjectWorkspace({ projectId }: { projectId: number }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedSessionId = useMemo(() => {
    const s = searchParams.get("session");
    const n = s ? Number(s) : NaN;
    return Number.isFinite(n) ? n : null;
  }, [searchParams]);
  const initialPrompt = searchParams.get("q") || null;

  const [project, setProject] = useState<AxiomProject | null>(null);
  const [activeSessionId, setLocalActiveSessionId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ---- Cached projects + datasets + chats ----
  // Both sidebar and workspace pull from the same cache so navigation
  // back to a previously visited project shows lists instantly while a
  // background revalidate runs.
  const fetchProjects = useCallback(
    () => api<AxiomProject[]>("/api/projects"),
    []
  );
  const { data: projects } = useCachedList<AxiomProject[]>(
    cacheKeys.projects(),
    fetchProjects
  );

  const fetchProjDatasets = useCallback(async () => {
    const all = await api<AxiomDataset[]>("/api/datasets");
    return all.filter((d) => d.project_id === projectId);
  }, [projectId]);
  const { data: datasetsRaw, refresh: refreshDatasets } =
    useCachedList<AxiomDataset[]>(
      cacheKeys.projectDatasets(projectId),
      fetchProjDatasets
    );
  const datasets = useMemo(() => datasetsRaw ?? [], [datasetsRaw]);

  const fetchSessions = useCallback(
    () => api<ChatSession[]>(`/api/projects/${projectId}/chats`),
    [projectId]
  );
  const { data: sessionsRaw, refresh: refreshSessionsCache } =
    useCachedList<ChatSession[]>(
      cacheKeys.projectChats(projectId),
      fetchSessions
    );
  const sessions: ChatSession[] | null = sessionsRaw ?? null;

  // Resolve the active project (memoized; not a separate fetch).
  useEffect(() => {
    if (!projects) return;
    const proj = projects.find((p) => p.id === projectId) || null;
    setProject(proj);
    if (!proj) setError("Project not found.");
  }, [projects, projectId]);

  // Auth + project breadcrumb.
  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    if (!Number.isFinite(projectId)) {
      router.push("/app");
      return;
    }
    setActiveProjectId(projectId);
  }, [projectId, router]);

  // Pick / auto-create the active session once the cached chat list
  // resolves. Auto-create runs at most once per empty project.
  const [autoCreateGuard, setAutoCreateGuard] = useState<number | null>(null);
  useEffect(() => {
    if (sessions == null) return;
    if (requestedSessionId && sessions.some((s) => s.id === requestedSessionId)) {
      setLocalActiveSessionId(requestedSessionId);
      return;
    }
    if (sessions.length > 0) {
      setLocalActiveSessionId((cur) =>
        cur && sessions.some((s) => s.id === cur) ? cur : sessions[0].id
      );
      return;
    }
    if (autoCreateGuard === projectId) return;
    setAutoCreateGuard(projectId);
    (async () => {
      try {
        const created = await api<ChatSession>(
          `/api/projects/${projectId}/chats`,
          { method: "POST", json: { title: "New chat" } }
        );
        setCached(cacheKeys.projectChats(projectId), [created]);
        setLocalActiveSessionId(created.id);
      } catch (e: unknown) {
        if (e instanceof ApiError && e.status === 401) {
          router.push("/login");
        } else {
          setError(errMessage(e));
        }
      }
    })();
  }, [sessions, requestedSessionId, projectId, autoCreateGuard, router]);

  // Mirror the active session into `?session=…` so the sidebar (which
  // reads it via useSearchParams) can highlight the current chat.
  useEffect(() => {
    if (!activeSessionId) return;
    if (requestedSessionId === activeSessionId) return;
    const qs = new URLSearchParams(window.location.search);
    qs.set("session", String(activeSessionId));
    router.replace(`/app/project/${projectId}?${qs.toString()}`);
  }, [activeSessionId, requestedSessionId, router, projectId]);

  // The chat composer's attach button uploads to /api/datasets/upload
  // and then fires `axiom:dataset:uploaded`. Refetch this project's
  // dataset list, focus the new file, and prefill a profile prompt.
  useEffect(() => {
    function onUploaded(e: Event) {
      const detail = (e as CustomEvent<{ datasetId: number; filename?: string }>).detail;
      if (!detail || typeof detail.datasetId !== "number") return;
      (async () => {
        try {
          const projOnly = await refreshDatasets();
          if (!projOnly) return;
          const fresh = projOnly.find((d) => d.id === detail.datasetId);
          if (!fresh) return;
          setActiveDatasetId(fresh.id);
          setActiveDatasetState(fresh.id);
          if (activeSessionId) {
            try {
              await api(
                `/api/chats/${activeSessionId}/seed-profile?dataset_id=${fresh.id}`,
                { method: "POST" }
              );
            } catch {
              /* non-fatal — chat prefill below is still triggered */
            }
          }
          const text = `Just uploaded ${fresh.filename || detail.filename || "a file"}. Walk me through what's interesting in this dataset.`;
          window.dispatchEvent(
            new CustomEvent("axiom:chat:prefill", { detail: { text, send: true } })
          );
        } catch {
          /* swallow — user can retry from the sidebar */
        }
      })();
    }
    window.addEventListener("axiom:dataset:uploaded", onUploaded);
    return () => window.removeEventListener("axiom:dataset:uploaded", onUploaded);
  }, [activeSessionId, refreshDatasets]);

  const seededModelForSessionRef = useRef<number | null>(null);

  // ---- Active dataset for the chat preview card ----
  const [activeDatasetState, setActiveDatasetState] = useState<number | null>(null);
  useEffect(() => {
    if (activeDatasetState != null) return;
    const stored = getActiveDatasetId();
    if (stored && datasets.some((d) => d.id === stored)) {
      setActiveDatasetState(stored);
      return;
    }
    if (datasets.length > 0) setActiveDatasetState(datasets[0].id);
  }, [datasets, activeDatasetState]);

  // Listen for dataset selection from the sidebar.
  useEffect(() => {
    function onActive(e: Event) {
      const detail = (e as CustomEvent<{ datasetId: number }>).detail;
      if (detail?.datasetId != null) setActiveDatasetState(detail.datasetId);
    }
    window.addEventListener("axiom:dataset:active", onActive);
    return () => window.removeEventListener("axiom:dataset:active", onActive);
  }, []);

  const pickDataset = useCallback((id: number) => {
    setActiveDatasetId(id);
    setActiveDatasetState(id);
  }, []);

  // Status pill source of truth lifted from ChatPanel.
  const [chatStreaming, setChatStreaming] = useState(false);

  // Guided-prediction wizard surfaces its own running state via a
  // window event so the Data Context Bar can show "جاري التنبؤ…"
  // without prop-drilling through ChatPanel / drawer internals.
  const [predictionRunning, setPredictionRunning] = useState(false);
  useEffect(() => {
    function onState(e: Event) {
      const detail = (e as CustomEvent<{ phase?: string }>).detail;
      setPredictionRunning(detail?.phase === "running" || detail?.phase === "scanning");
    }
    window.addEventListener("axiom:guided-predict:state", onState);
    return () => window.removeEventListener("axiom:guided-predict:state", onState);
  }, []);

  const activeDatasetMeta = useMemo(
    () => datasets.find((d) => d.id === activeDatasetState) ?? null,
    [datasets, activeDatasetState]
  );

  // ---- Right-side artifact drawer ----
  // Drawer is collapsed by default on first visit; we remember the
  // user's last toggled state for the rest of the tab session so it
  // doesn't keep snapping shut between chats.
  const [drawerOpen, setDrawerOpen] = useState(false);
  useEffect(() => {
    try {
      const v = window.sessionStorage.getItem(DRAWER_PREF_KEY);
      if (v === "1") setDrawerOpen(true);
    } catch {
      /* sessionStorage may be blocked — fall back to closed */
    }
  }, []);
  const toggleDrawer = useCallback(() => {
    setDrawerOpen((cur) => {
      const next = !cur;
      try {
        window.sessionStorage.setItem(DRAWER_PREF_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);
  const closeDrawer = useCallback(() => {
    setDrawerOpen(false);
    try {
      window.sessionStorage.setItem(DRAWER_PREF_KEY, "0");
    } catch {
      /* ignore */
    }
  }, []);

  const [drawerTab, setDrawerTab] = useState<
    "profile" | "visualize" | "predictions" | "clusters" | "model"
  >("profile");
  const [pendingTools, setPendingTools] = useState<PendingTool[]>([]);
  const [artifactRefresh, setArtifactRefresh] = useState(0);

  // Multi-CSV projects (≥2 datasets) get a deterministic Data model
  // artifact seeded into the chat session so users see the proposed
  // joins / open questions in the drawer without depending on the LLM
  // choosing the `list_model` tool. Idempotent on the backend.
  useEffect(() => {
    if (!activeSessionId || datasets.length < 2) return;
    if (seededModelForSessionRef.current === activeSessionId) return;
    seededModelForSessionRef.current = activeSessionId;
    (async () => {
      try {
        await api(
          `/api/chats/${activeSessionId}/seed-data-model`,
          { method: "POST" }
        );
        setArtifactRefresh((n) => n + 1);
      } catch {
        seededModelForSessionRef.current = null;
      }
    })();
  }, [activeSessionId, datasets.length]);

  const pushChatPrompt = useCallback((text: string, sendNow: boolean) => {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent("axiom:chat:prefill", { detail: { text, send: sendNow } })
    );
  }, []);
  const onSuggestedQuestion = useCallback(
    (q: string) => pushChatPrompt(q, true),
    [pushChatPrompt]
  );
  const onAskAboutCell = useCallback(
    (rowIndex: number, column: string, value: unknown) => {
      const v = value == null ? "" : String(value);
      pushChatPrompt(
        `Tell me about row ${rowIndex + 1} where \`${column}\` = ${JSON.stringify(v)}. Why does this value stand out, and what surrounds it?`,
        false
      );
    },
    [pushChatPrompt]
  );

  const onToolStarted = useCallback((p: PendingTool) => {
    setPendingTools((cur) => [...cur, p]);
    if (p.tool === "make_chart") setDrawerTab("visualize");
    else if (p.tool === "predict_column") setDrawerTab("predictions");
    else if (p.tool === "cluster_dataset") setDrawerTab("clusters");
    else if (p.tool === "profile_dataset") setDrawerTab("profile");
    else if (
      p.tool === "list_model" ||
      p.tool === "query_model" ||
      p.tool === "explain_model"
    )
      setDrawerTab("model");
    setDrawerOpen(true);
    try {
      window.sessionStorage.setItem(DRAWER_PREF_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);
  const onToolFinished = useCallback((callId: string) => {
    setPendingTools((cur) => cur.filter((p) => p.id !== callId));
    setArtifactRefresh((n) => n + 1);
  }, []);
  // Clean up any pending skeletons whenever a stream ends — covers
  // network errors, aborts, and any tool whose tool_finished event
  // never arrived. Without this, drawer skeletons could leak forever.
  const onChatTurnEnded = useCallback(() => {
    setPendingTools([]);
    setArtifactRefresh((n) => n + 1);
  }, []);
  // Reset whenever the user switches to a different chat session so
  // skeletons from the previous chat can't bleed into the new one.
  useEffect(() => {
    setPendingTools([]);
  }, [activeSessionId]);

  // Stable callback so ChatPanel (now React.memo'd) doesn't re-render
  // every time the workspace re-renders for unrelated reasons.
  const onArtifactCreated = useCallback(
    () => setArtifactRefresh((n) => n + 1),
    []
  );

  // Strip ?q= from the URL after the prompt is consumed so reloading
  // doesn't resend the message.
  const onInitialPromptConsumed = useCallback(() => {
    if (!initialPrompt) return;
    const sid = activeSessionId;
    if (sid) {
      router.replace(`/app/project/${projectId}?session=${sid}`);
    }
  }, [router, projectId, activeSessionId, initialPrompt]);

  // Refresh chats cache on each successful turn so updated_at orderings
  // stay fresh in the sidebar tree.
  const onTurnComplete = useCallback(() => {
    void refreshSessionsCache();
  }, [refreshSessionsCache]);

  const activeSession = useMemo(
    () => sessions?.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId]
  );

  // Memoize the chat header so ChatPanel (now React.memo'd) sees a
  // stable `headerSlot` reference across unrelated parent re-renders
  // (drawer toggling, mode pill flip, etc.) and can short-circuit.
  const chatHeaderSlot = useMemo(
    () => (
      <>
        <OpenQuestionsBar
          projectId={projectId}
          onAskQuestion={onSuggestedQuestion}
          refreshKey={artifactRefresh}
        />
        {activeDatasetState != null && datasets.length > 0 ? (
          <DatasetPreviewCard
            key={activeDatasetState}
            datasetId={activeDatasetState}
            onAskQuestion={onSuggestedQuestion}
            onAskAboutCell={onAskAboutCell}
          />
        ) : null}
      </>
    ),
    [
      projectId,
      onSuggestedQuestion,
      artifactRefresh,
      activeDatasetState,
      datasets.length,
      onAskAboutCell,
    ]
  );

  const dataContextRight = useMemo(
    () => (
      <div className="flex items-center gap-1.5">
        {activeSessionId && (
          <Link
            href={`/app/project/${projectId}/report?session=${activeSessionId}`}
            className="hidden md:inline-flex text-[11px] px-2 py-1 rounded-md border border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--accent)] text-[var(--text-muted)]"
            title="Open the final report for this chat · التقرير النهائي"
          >
            Final report ↗
          </Link>
        )}
        <ModeToggle projectId={projectId} size="sm" label="MODE" />
        <button
          onClick={toggleDrawer}
          className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-[var(--border)] hover:border-[var(--accent)] hover:text-[var(--accent)] text-[var(--text-muted)]"
          title={drawerOpen ? "Hide artifact drawer" : "Show artifact drawer"}
          aria-pressed={drawerOpen}
        >
          {drawerOpen ? (
            <ChevronRight className="h-3 w-3" />
          ) : (
            <ChevronLeft className="h-3 w-3" />
          )}
          Artifacts
        </button>
      </div>
    ),
    [activeSessionId, projectId, toggleDrawer, drawerOpen]
  );

  return (
    <div
      className={`-m-6 h-[calc(100vh-3.5rem)] flex flex-col overflow-hidden transition-[padding] ${
        drawerOpen ? "pr-[440px]" : ""
      }`}
    >
      <main className="flex-1 min-h-0 flex flex-col overflow-hidden bg-[var(--surface)]">
        <DataContextBar
          projectName={project?.name ?? activeSession?.title ?? "Project"}
          projectId={projectId}
          datasets={datasets}
          activeDatasetId={activeDatasetState}
          onPickDataset={pickDataset}
          streaming={chatStreaming}
          predictionRunning={predictionRunning}
          rightSlot={dataContextRight}
        />
        <div className="flex-1 min-h-0 flex flex-col overflow-hidden px-4 sm:px-6 py-6">
          <div className="mx-auto w-full max-w-[800px] flex-1 min-h-0 flex flex-col gap-4">
            {error && <div className="text-red-600 text-sm shrink-0">{error}</div>}
            <div className="shrink-0">
              <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
                Conversation
              </span>
              <h1 className="text-lg font-semibold mt-0.5 text-[var(--text)]">
                {activeSession?.title ?? "New chat"}
              </h1>
            </div>

            {/* Mode-aware contextual hint sits inside the centred thread,
                under the new sticky chips bar. The sticky DataContextBar
                handles dataset chips + Quick Preview + status pill; this
                inline strip preserves the Expert/Guided wording flex. */}
            <div className="shrink-0">
              <ModeAwareContextBar projectId={projectId} datasets={datasets} />
            </div>

            {activeSessionId ? (
              // `min-h-0` (NOT a fixed min-h) is essential here: the
              // chat slot is a flex child whose own child (`ChatPanel`)
              // has its own internal scroller, and the ancestor uses
              // `overflow-hidden`. A non-zero `min-h` would let this
              // slot grow past the parent's space and clip the composer.
              //
              // The dataset preview is passed as `headerSlot` so it
              // renders INSIDE the chat scroller above the greeting and
              // turns — that way the user sees a single unified thread
              // (preview → greeting → user → assistant), the composer
              // is always visible at the bottom, and the preview slides
              // off-screen naturally as the conversation grows.
              <div className="flex-1 min-h-0 flex flex-col">
                <ChatPanel
                  key={activeSessionId}
                  sessionId={activeSessionId}
                  projectId={projectId}
                  onTurnComplete={onTurnComplete}
                  hasData={datasets.length > 0}
                  initialPrompt={
                    requestedSessionId === activeSessionId ? initialPrompt : null
                  }
                  onInitialPromptConsumed={onInitialPromptConsumed}
                  onToolStarted={onToolStarted}
                  onToolFinished={onToolFinished}
                  onTurnEnded={onChatTurnEnded}
                  onStreamingChange={setChatStreaming}
                  headerSlot={chatHeaderSlot}
                />
              </div>
            ) : (
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] p-6 text-sm text-[var(--text-muted)] shrink-0">
                Loading chat…
              </div>
            )}
          </div>
        </div>
      </main>

      <ArtifactDrawer
        open={drawerOpen}
        onClose={closeDrawer}
        sessionId={activeSessionId}
        refreshKey={artifactRefresh}
        pending={pendingTools}
        initialTab={drawerTab}
        showDataModelTab={datasets.length >= 2}
        activeDatasetId={activeDatasetState}
        activeDatasetName={
          activeDatasetMeta?.dataset_name ?? activeDatasetMeta?.filename ?? undefined
        }
        onArtifactCreated={onArtifactCreated}
      />
    </div>
  );
}

/**
 * Mode-aware "Data Context Bar" sitting between the chat title and the
 * conversation. Guided users get a friendly, plain-language sentence;
 * Expert users get a compact metric strip with row counts and a hint
 * that JSON / SQL is welcome in the prompt.
 */
function aggregateDatasetStats(datasets: AxiomDataset[]): {
  totalRows: number;
  totalCols: number;
  numericCols: number;
  categoricalCols: number;
  datetimeCols: number;
  otherCols: number;
  avgMissingPct: number;
} {
  let totalRows = 0;
  let totalCols = 0;
  let numericCols = 0;
  let categoricalCols = 0;
  let datetimeCols = 0;
  let otherCols = 0;
  let missingSum = 0;
  let missingDen = 0;
  for (const d of datasets) {
    totalRows += d.rows || 0;
    totalCols += d.cols || 0;
    const sum = (d as unknown as { summary?: Record<string, unknown> }).summary;
    if (!sum) continue;
    const numeric = (sum.numeric_summary as Record<string, Record<string, unknown>> | undefined) || {};
    const categorical = (sum.categorical_summary as Record<string, Record<string, unknown>> | undefined) || {};
    const distributions = (sum.distributions as Record<string, Record<string, unknown>> | undefined) || {};
    const numericNames = Object.keys(numeric);
    numericCols += numericNames.length;
    categoricalCols += Object.keys(categorical).length;
    for (const [, info] of Object.entries(distributions)) {
      const t = String((info as { type?: unknown }).type ?? "").toLowerCase();
      if (t.includes("date") || t.includes("time")) datetimeCols += 1;
    }
    otherCols += Math.max(
      0,
      (d.cols || 0) - numericNames.length - Object.keys(categorical).length
    );
    for (const stats of Object.values(numeric)) {
      const m = stats?.["missing_pct"];
      if (typeof m === "number" && Number.isFinite(m)) {
        missingSum += m;
        missingDen += 1;
      }
    }
    if (d.rows && d.rows > 0) {
      for (const stats of Object.values(categorical)) {
        const m = stats?.["missing"];
        if (typeof m === "number" && Number.isFinite(m)) {
          missingSum += (m / d.rows) * 100;
          missingDen += 1;
        }
      }
    }
  }
  return {
    totalRows,
    totalCols,
    numericCols,
    categoricalCols,
    datetimeCols,
    otherCols: Math.max(0, otherCols - datetimeCols),
    avgMissingPct: missingDen > 0 ? missingSum / missingDen : 0,
  };
}

function ModeAwareContextBar({
  projectId,
  datasets,
}: {
  projectId: number;
  datasets: AxiomDataset[];
}) {
  const { mode } = useMode(projectId);
  const datasetCount = datasets.length;
  if (datasetCount === 0) {
    return (
      <div className="mb-3 text-xs rounded-md border border-dashed border-[var(--border)] bg-[var(--surface-alt)]/50 px-3 py-2 text-[var(--text-muted)]">
        {mode === "expert"
          ? "No datasets bound to this project. Upload a CSV/Parquet/Excel file to enable tool calls."
          : "No data uploaded yet — drop a file in and the assistant can start analysing it."}
      </div>
    );
  }
  const agg = aggregateDatasetStats(datasets);
  if (mode === "expert") {
    const dtypeChips: string[] = [];
    if (agg.numericCols) dtypeChips.push(`${agg.numericCols} numeric`);
    if (agg.categoricalCols) dtypeChips.push(`${agg.categoricalCols} categorical`);
    if (agg.datetimeCols) dtypeChips.push(`${agg.datetimeCols} datetime`);
    if (agg.otherCols) dtypeChips.push(`${agg.otherCols} other`);
    return (
      <div className="mb-3 text-[11px] font-mono rounded-md border border-[var(--border)] bg-[var(--surface-alt)]/50 px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[var(--text-muted)]">
        <span>
          <strong className="text-[var(--text)]">{datasetCount}</strong> dataset
          {datasetCount === 1 ? "" : "s"}
        </span>
        <span>
          <strong className="text-[var(--text)]">{agg.totalRows.toLocaleString()}</strong> rows
        </span>
        <span>
          <strong className="text-[var(--text)]">{agg.totalCols.toLocaleString()}</strong> cols
        </span>
        {dtypeChips.length > 0 && (
          <span title="Column dtypes (numeric / categorical / datetime / other)">
            {dtypeChips.join(" · ")}
          </span>
        )}
        <span title="Mean per-column missing % across all bound datasets">
          missing&nbsp;
          <strong className="text-[var(--text)]">
            {agg.avgMissingPct.toFixed(1)}%
          </strong>
        </span>
        <span>JSON / SQL / column names accepted</span>
      </div>
    );
  }
  return (
    <div className="mb-3 text-xs rounded-md border border-[var(--border)] bg-[var(--surface-alt)]/50 px-3 py-2 text-[var(--text-muted)]">
      I can see all <strong className="text-[var(--text)]">{datasetCount}</strong> dataset
      {datasetCount === 1 ? "" : "s"} in this project ({agg.totalRows.toLocaleString()} rows).
      Ask in plain language and I&apos;ll handle the analysis.
    </div>
  );
}
