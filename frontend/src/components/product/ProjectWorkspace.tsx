"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import { errMessage, type AxiomDataset, type AxiomProject } from "@/lib/types";
import { setActiveProjectId, setActiveDatasetId, getActiveDatasetId } from "@/lib/projectContext";
import { ChatPanel } from "@/components/product/ChatPanel";
import { DatasetPreviewCard } from "@/components/product/DatasetPreviewCard";
import { ArtifactDrawer, type Artifact, type PendingTool } from "@/components/product/ArtifactDrawer";

type ChatSession = {
  id: number;
  project_id: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
};

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
  const [datasets, setDatasets] = useState<AxiomDataset[]>([]);
  const [sessions, setSessions] = useState<ChatSession[] | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");

  const refreshSessions = useCallback(
    async (preferId?: number | null) => {
      try {
        const list = await api<ChatSession[]>(
          `/api/projects/${projectId}/chats`
        );
        setSessions(list);
        if (preferId != null && list.some((s) => s.id === preferId)) {
          setActiveSessionId(preferId);
        } else if (list.length > 0) {
          setActiveSessionId((cur) =>
            cur && list.some((s) => s.id === cur) ? cur : list[0].id
          );
        } else {
          // Auto-create the first session so the user lands in a usable
          // chat view immediately, without an empty-state click.
          const created = await api<ChatSession>(
            `/api/projects/${projectId}/chats`,
            { method: "POST", json: { title: "New chat" } }
          );
          setSessions([created]);
          setActiveSessionId(created.id);
        }
      } catch (e: unknown) {
        setError(errMessage(e));
      }
    },
    [projectId]
  );

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

    let cancelled = false;
    (async () => {
      try {
        const [projects, allDatasets] = await Promise.all([
          api<AxiomProject[]>("/api/projects"),
          api<AxiomDataset[]>("/api/datasets"),
        ]);
        if (cancelled) return;
        const proj = projects.find((p) => p.id === projectId) || null;
        setProject(proj);
        if (!proj) {
          setError("Project not found.");
          return;
        }
        const projDatasets = allDatasets.filter(
          (d) => d.project_id === projectId
        );
        setDatasets(projDatasets);
        await refreshSessions(requestedSessionId);
      } catch (e: unknown) {
        if (!cancelled) {
          if (e instanceof ApiError && e.status === 401) {
            router.push("/login");
          } else {
            setError(errMessage(e));
          }
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [projectId, router, refreshSessions, requestedSessionId]);

  // If the URL session id changes (e.g. user clicks a different chat in
  // the global sidebar without changing the project), follow it.
  useEffect(() => {
    if (requestedSessionId && sessions?.some((s) => s.id === requestedSessionId)) {
      setActiveSessionId(requestedSessionId);
    }
  }, [requestedSessionId, sessions]);

  async function newSession() {
    if (busy) return;
    setBusy(true);
    try {
      const s = await api<ChatSession>(
        `/api/projects/${projectId}/chats`,
        { method: "POST", json: { title: "New chat" } }
      );
      setSessions((cur) => (cur ? [s, ...cur] : [s]));
      setActiveSessionId(s.id);
    } catch (e: unknown) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function deleteSession(id: number) {
    if (!confirm("Delete this chat?")) return;
    try {
      await api(`/api/chats/${id}`, { method: "DELETE" });
      setSessions((cur) => (cur ? cur.filter((s) => s.id !== id) : cur));
      if (activeSessionId === id) {
        setActiveSessionId(null);
        await refreshSessions();
      }
    } catch (e: unknown) {
      setError(errMessage(e));
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
      setSessions((cur) =>
        cur ? cur.map((s) => (s.id === id ? updated : s)) : cur
      );
    } catch (e: unknown) {
      setError(errMessage(e));
    } finally {
      setRenamingId(null);
    }
  }

  function pickDataset(id: number) {
    setActiveDatasetId(id);
    setActiveDatasetState(id);
  }

  // The chat composer's attach button uploads to /api/datasets/upload and
  // then fires `axiom:dataset:uploaded`. We refetch this project's dataset
  // list, focus the new file, and prefill a profile prompt that the chat
  // sends immediately (which triggers the `profile_dataset` tool).
  useEffect(() => {
    function onUploaded(e: Event) {
      const detail = (e as CustomEvent<{ datasetId: number; filename?: string }>).detail;
      if (!detail || typeof detail.datasetId !== "number") return;
      (async () => {
        try {
          const all = await api<AxiomDataset[]>("/api/datasets");
          const projOnly = all.filter((d) => d.project_id === projectId);
          setDatasets(projOnly);
          const fresh = projOnly.find((d) => d.id === detail.datasetId);
          if (fresh) {
            setActiveDatasetId(fresh.id);
            setActiveDatasetState(fresh.id);
            // 1) Deterministically pin a profile artifact via the seed
            //    endpoint so the workflow is guaranteed even if the LLM
            //    follow-up is delayed or fails. The drawer notices via
            //    the artifact-list refresh below.
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
            // 2) Send a narrative chat message so the assistant explains
            //    the profile in conversation.
            const text = `Just uploaded ${fresh.filename || detail.filename || "a file"}. Walk me through what's interesting in this dataset.`;
            window.dispatchEvent(
              new CustomEvent("axiom:chat:prefill", { detail: { text, send: true } })
            );
          }
        } catch {
          /* swallow — user can retry from the sidebar */
        }
      })();
    }
    window.addEventListener("axiom:dataset:uploaded", onUploaded);
    return () => window.removeEventListener("axiom:dataset:uploaded", onUploaded);
  }, [projectId, activeSessionId]);

  // Dataset shown in the chat preview card. Falls back to the project's
  // first dataset on initial load so a freshly-uploaded file shows up
  // immediately without the user having to click anything.
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

  // Right-side artifact drawer state.
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerTab, setDrawerTab] = useState<
    "profile" | "visualize" | "predictions" | "clusters"
  >("profile");
  const [pendingTools, setPendingTools] = useState<PendingTool[]>([]);
  const [artifactRefresh, setArtifactRefresh] = useState(0);

  function pushChatPrompt(text: string, sendNow: boolean) {
    if (typeof window === "undefined") return;
    window.dispatchEvent(
      new CustomEvent("axiom:chat:prefill", { detail: { text, send: sendNow } })
    );
  }
  const onSuggestedQuestion = useCallback((q: string) => pushChatPrompt(q, true), []);
  const onAskAboutCell = useCallback(
    (rowIndex: number, column: string, value: unknown) => {
      const v = value == null ? "" : String(value);
      pushChatPrompt(
        `Tell me about row ${rowIndex + 1} where \`${column}\` = ${JSON.stringify(v)}. Why does this value stand out, and what surrounds it?`,
        false
      );
    },
    []
  );

  function onToolStarted(p: PendingTool) {
    setPendingTools((cur) => [...cur, p]);
    if (p.tool === "make_chart") setDrawerTab("visualize");
    else if (p.tool === "predict_column") setDrawerTab("predictions");
    else if (p.tool === "cluster_dataset") setDrawerTab("clusters");
    else if (p.tool === "profile_dataset") setDrawerTab("profile");
    setDrawerOpen(true);
  }
  function onToolFinished(callId: string) {
    setPendingTools((cur) => cur.filter((p) => p.id !== callId));
    setArtifactRefresh((n) => n + 1);
  }
  // Clean up any pending skeletons whenever a stream ends — covers
  // network errors, aborts, and any tool whose tool_finished event
  // never arrived. Without this, drawer skeletons could leak forever.
  function onChatTurnEnded() {
    setPendingTools([]);
    setArtifactRefresh((n) => n + 1);
  }
  // And reset whenever the user switches to a different chat session so
  // skeletons from the previous chat can't bleed into the new one.
  useEffect(() => {
    setPendingTools([]);
  }, [activeSessionId]);

  // Strip ?q= from the URL after the prompt is consumed so reloading
  // doesn't resend the message.
  const onInitialPromptConsumed = useCallback(() => {
    if (!initialPrompt) return;
    const sid = activeSessionId;
    if (sid) {
      router.replace(`/app/project/${projectId}?session=${sid}`);
    }
  }, [router, projectId, activeSessionId, initialPrompt]);

  // When the chat panel produces a streaming reply we may want to bump
  // the session's `updated_at`; we do that by re-fetching sessions on
  // every successful turn through the callback below.
  const onTurnComplete = useCallback(() => {
    refreshSessions(activeSessionId);
  }, [refreshSessions, activeSessionId]);

  const activeSession = useMemo(
    () => sessions?.find((s) => s.id === activeSessionId) ?? null,
    [sessions, activeSessionId]
  );

  return (
    <div
      className={`-m-6 grid min-h-[calc(100vh-3.5rem)] transition-[grid-template-columns] ${
        drawerOpen
          ? "grid-cols-[240px_minmax(0,1fr)_440px]"
          : "grid-cols-[240px_minmax(0,1fr)]"
      }`}
    >
      {/* Project rail — narrow, scoped to this project */}
      <aside className="border-r border-[var(--border)] bg-[var(--surface-alt)] p-4 flex flex-col text-sm overflow-y-auto">
        <div className="font-semibold text-[var(--text)] truncate">
          {project?.name ?? "…"}
        </div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)] mt-0.5">
          Project workspace
        </div>

        <button
          onClick={newSession}
          disabled={busy}
          className="btn btn-primary text-xs mt-4 justify-center"
        >
          + New chat in this project
        </button>

        <div className="mt-5">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-2">
            Chats in this project
          </div>
          {sessions === null ? (
            <div className="text-[var(--text-muted)] text-xs">Loading…</div>
          ) : sessions.length === 0 ? (
            <div className="text-[var(--text-muted)] text-xs">No chats yet.</div>
          ) : (
            <ul className="space-y-1">
              {sessions.map((s) => {
                const active = s.id === activeSessionId;
                const isRenaming = renamingId === s.id;
                return (
                  <li
                    key={s.id}
                    className={`group rounded px-2 py-1.5 cursor-pointer flex items-center gap-1 ${
                      active
                        ? "bg-[var(--accent)] text-white"
                        : "hover:bg-[var(--surface)] text-[var(--text)]"
                    }`}
                    onClick={() => !isRenaming && setActiveSessionId(s.id)}
                  >
                    {isRenaming ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={(e) => setRenameValue(e.target.value)}
                        onBlur={() => commitRename(s.id)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") commitRename(s.id);
                          if (e.key === "Escape") setRenamingId(null);
                        }}
                        className="flex-1 px-2 py-1 text-xs rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
                      />
                    ) : (
                      <>
                        <span
                          className="flex-1 truncate text-xs"
                          title={s.title}
                          onDoubleClick={(e) => {
                            e.stopPropagation();
                            setRenamingId(s.id);
                            setRenameValue(s.title);
                          }}
                        >
                          {s.title || "Untitled chat"}
                        </span>
                        <button
                          aria-label="Rename"
                          className={`opacity-0 group-hover:opacity-100 text-[10px] px-1 rounded ${
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
                          ✎
                        </button>
                        <button
                          aria-label="Delete"
                          className={`opacity-0 group-hover:opacity-100 text-[10px] px-1 rounded ${
                            active
                              ? "text-white/80 hover:text-white"
                              : "text-[var(--text-muted)] hover:text-red-500"
                          }`}
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteSession(s.id);
                          }}
                        >
                          ✕
                        </button>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="mt-6">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-2">
            Datasets
          </div>
          {datasets.length === 0 ? (
            <div className="text-[var(--text-muted)] text-xs">
              No data uploaded yet.{" "}
              <Link href="/app/upload" className="text-[var(--accent)] underline">
                Upload
              </Link>
            </div>
          ) : (
            <ul className="space-y-1">
              {datasets.map((d) => (
                <li key={d.id}>
                  <button
                    onClick={() => pickDataset(d.id)}
                    className="text-left w-full rounded px-2 py-1.5 text-xs hover:bg-[var(--surface)]"
                    title={`${d.rows} rows × ${d.cols} cols`}
                  >
                    <span className="truncate block">{d.dataset_name}</span>
                    <span className="text-[10px] text-[var(--text-muted)] font-mono">
                      {d.rows.toLocaleString()} × {d.cols}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <Link
            href="/app/upload"
            className="block mt-2 text-xs text-[var(--accent)] hover:underline"
          >
            + Upload more
          </Link>
        </div>

        {activeSessionId && (
          <Link
            href={`/app/project/${projectId}/report?session=${activeSessionId}`}
            className="mt-6 block text-xs px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] hover:border-[var(--accent)] hover:text-[var(--accent)] text-center"
          >
            Final report →
          </Link>
        )}
      </aside>

      {/* Main pane */}
      <main className="p-6 overflow-auto">
        <div className="max-w-4xl space-y-4">
          {error && <div className="text-red-600 text-sm mb-3">{error}</div>}
          <div className="flex items-baseline justify-between mb-1">
            <div>
              <span className="eyebrow">Project chat</span>
              <h1 className="text-xl font-semibold mt-1">
                {activeSession?.title ?? "New chat"}
              </h1>
            </div>
            <div className="flex items-center gap-2">
              {datasets.length > 0 && (
                <div className="text-xs text-[var(--text-muted)] font-mono">
                  AI sees all {datasets.length} dataset{datasets.length === 1 ? "" : "s"}
                </div>
              )}
              {activeSessionId && (
                <Link
                  href={`/app/project/${projectId}/report?session=${activeSessionId}`}
                  className="btn btn-ghost text-xs"
                  title="Open the final report for this chat · التقرير النهائي"
                >
                  Final report ↗
                </Link>
              )}
              <button
                onClick={() => setDrawerOpen((v) => !v)}
                className="btn btn-ghost text-xs"
                title="Toggle artifact drawer"
              >
                {drawerOpen ? "Hide artifacts" : "Show artifacts"}
              </button>
            </div>
          </div>

          {activeDatasetState != null && datasets.length > 0 && (
            <DatasetPreviewCard
              key={activeDatasetState}
              datasetId={activeDatasetState}
              onAskQuestion={onSuggestedQuestion}
              onAskAboutCell={onAskAboutCell}
            />
          )}

          {activeSessionId ? (
            <ChatPanel
              key={activeSessionId}
              sessionId={activeSessionId}
              onTurnComplete={onTurnComplete}
              hasData={datasets.length > 0}
              initialPrompt={
                requestedSessionId === activeSessionId ? initialPrompt : null
              }
              onInitialPromptConsumed={onInitialPromptConsumed}
              onToolStarted={onToolStarted}
              onToolFinished={(callId) => onToolFinished(callId)}
              onTurnEnded={onChatTurnEnded}
            />
          ) : (
            <div className="card text-sm text-[var(--text-muted)]">
              Loading chat…
            </div>
          )}
        </div>
      </main>

      <ArtifactDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        sessionId={activeSessionId}
        refreshKey={artifactRefresh}
        pending={pendingTools}
        initialTab={drawerTab}
      />
    </div>
  );
}
