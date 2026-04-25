"use client";
import { useEffect, useRef, useState } from "react";
import { api, getToken, streamPostNDJSON } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { ChartRenderer, type ChartPayload } from "./Charts";
import { PredictionCard, type PredictionResult } from "./PredictionCard";
import type { Artifact, PendingTool } from "./ArtifactDrawer";

type ToolEvent =
  | { kind: "started"; tool: string; callId: string; params: Record<string, unknown> }
  | { kind: "finished"; tool: string; callId: string; ok: boolean; summary?: unknown; artifacts?: Artifact[]; error?: string };

type Msg =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; tools?: ToolEvent[] };

type StoredMessage = {
  id: number;
  user_message: string;
  ai_response: string;
};

type ChatPanelProps = {
  sessionId?: number | null;
  onTurnComplete?: () => void;
  // Called whenever a stream ends, regardless of success/failure. Lets the
  // parent flush any "pending tool" skeletons that never got a matching
  // tool_finished event (e.g. the stream was aborted or errored).
  onTurnEnded?: () => void;
  hasData?: boolean;
  initialPrompt?: string | null;
  onInitialPromptConsumed?: () => void;
  /** Notifies the parent each time a tool starts so it can pop the
   * artifact drawer with a skeleton loader. */
  onToolStarted?: (p: PendingTool) => void;
  /** Notifies the parent each time a tool finishes so it can refresh
   * the artifact list and clear the skeleton. */
  onToolFinished?: (callId: string, artifacts: Artifact[]) => void;
};

const GREETING_NEW =
  "Hey — drop a question about any dataset in this project and I'll walk through the analysis step-by-step. I can run charts, predictions, profiling, and clustering directly from chat.";
const GREETING_NO_DATA =
  "This project doesn't have any data yet. Upload a CSV or Excel file from the sidebar and I'll start analysing it.";

export function ChatPanel({
  sessionId = null,
  onTurnComplete,
  onTurnEnded,
  hasData = true,
  initialPrompt = null,
  onInitialPromptConsumed,
  onToolStarted,
  onToolFinished,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  // Aborts any in-flight stream when the user navigates away or switches
  // chat sessions (the parent re-keys this component on session change).
  const abortRef = useRef<AbortController | null>(null);
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      abortRef.current = null;
    };
  }, []);
  const [authed, setAuthed] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(!!sessionId);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const consumedPromptRef = useRef<string | null>(null);
  const sendRef = useRef<((text?: string) => Promise<void>) | null>(null);

  useEffect(() => {
    setAuthed(!!getToken());
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!sessionId) {
      setMessages([{ role: "assistant", content: hasData ? GREETING_NEW : GREETING_NO_DATA }]);
      setLoadingHistory(false);
      return;
    }
    setLoadingHistory(true);
    api<{ messages: StoredMessage[] }>(`/api/chats/${sessionId}/messages`)
      .then((res) => {
        if (cancelled) return;
        const flat: Msg[] = [];
        for (const m of res.messages) {
          if (m.user_message) flat.push({ role: "user", content: m.user_message });
          if (m.ai_response) flat.push({ role: "assistant", content: m.ai_response });
        }
        if (flat.length === 0) {
          flat.push({ role: "assistant", content: hasData ? GREETING_NEW : GREETING_NO_DATA });
        }
        setMessages(flat);
      })
      .catch(() => {
        if (!cancelled) {
          setMessages([{ role: "assistant", content: "Could not load chat history." }]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, hasData]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function send(forceText?: string) {
    const text = (forceText ?? input).trim();
    if (!text || streaming) return;
    const userMsg: Msg = { role: "user", content: text };
    const baseHistory =
      messages.length === 1 && messages[0].role === "assistant" ? [] : messages;
    const nextHistory: Msg[] = [...baseHistory, userMsg];
    const seedAssistant: Msg = { role: "assistant", content: "", tools: [] };
    setMessages([...nextHistory, seedAssistant]);
    if (forceText == null) setInput("");
    setStreaming(true);

    const transcript = nextHistory.map((m) => ({ role: m.role, content: m.content }));
    let textAcc = "";
    const toolBuf: ToolEvent[] = [];

    function patchLast(patch: Partial<Msg>) {
      setMessages((m) => {
        const copy = m.slice();
        const last = copy[copy.length - 1];
        if (last && last.role === "assistant") {
          copy[copy.length - 1] = { ...last, ...patch } as Msg;
        }
        return copy;
      });
    }

    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      await streamPostNDJSON(
        "/api/chat/stream",
        {
          messages: transcript,
          session_id: sessionId,
          dataset_id: sessionId ? null : getActiveDatasetId(),
          project_id: sessionId ? null : getActiveProjectId(),
        },
        (ev) => {
          const t = String(ev.type || "");
          if (t === "text") {
            textAcc += String(ev.data ?? "");
            patchLast({ content: textAcc });
          } else if (t === "done") {
            // The backend signals end-of-stream explicitly; nothing to
            // render but we let the finally block flush state below.
          } else if (t === "tool_started") {
            const callId = String(ev.call_id ?? Math.random());
            const tool = String(ev.tool ?? "tool");
            toolBuf.push({
              kind: "started",
              tool,
              callId,
              params: (ev.params as Record<string, unknown>) || {},
            });
            patchLast({ tools: toolBuf.slice() });
            onToolStarted?.({ id: callId, tool });
          } else if (t === "tool_finished") {
            const callId = String(ev.call_id ?? "");
            const tool = String(ev.tool ?? "tool");
            const finished: ToolEvent = {
              kind: "finished",
              tool,
              callId,
              ok: Boolean(ev.ok),
              summary: ev.summary,
              error: typeof ev.error === "string" ? ev.error : undefined,
              artifacts: (ev.artifacts as Artifact[]) || [],
            };
            const idx = toolBuf.findIndex((x) => x.callId === callId);
            if (idx >= 0) toolBuf[idx] = finished;
            else toolBuf.push(finished);
            patchLast({ tools: toolBuf.slice() });
            onToolFinished?.(callId, finished.artifacts || []);
          } else if (t === "error") {
            textAcc += `\n\n[chat error: ${String(ev.data ?? "unknown")}]`;
            patchLast({ content: textAcc });
          }
        },
        controller.signal,
      );
      onTurnComplete?.();
    } catch (e: unknown) {
      // AbortError is expected when the user navigates away mid-stream;
      // don't paint a scary error message in that case.
      const aborted =
        (e as { name?: string } | null)?.name === "AbortError" ||
        controller.signal.aborted;
      if (!aborted) {
        patchLast({
          content: textAcc || `(Chat error: ${errMessage(e, "request failed")}.)`,
        });
      }
    } finally {
      setStreaming(false);
      // Always notify the parent so any "pending tool" skeletons that
      // never received a matching tool_finished event get cleaned up.
      onTurnEnded?.();
      if (abortRef.current === controller) abortRef.current = null;
    }
  }
  sendRef.current = send;

  useEffect(() => {
    if (loadingHistory) return;
    if (!initialPrompt) return;
    if (consumedPromptRef.current === initialPrompt) return;
    if (streaming) return;
    const isFresh =
      messages.length === 0 ||
      (messages.length === 1 && messages[0].role === "assistant");
    if (!isFresh) return;
    consumedPromptRef.current = initialPrompt;
    onInitialPromptConsumed?.();
    sendRef.current?.(initialPrompt);
  }, [loadingHistory, initialPrompt, messages, streaming, onInitialPromptConsumed]);

  // Allow the parent (ProjectWorkspace) to pre-fill the input, e.g. from
  // a suggested-question chip or an "ask about this cell" click.
  useEffect(() => {
    function onPrefill(e: Event) {
      const detail = (e as CustomEvent<{ text?: string; send?: boolean }>).detail || {};
      const text = String(detail.text || "");
      if (!text) return;
      if (detail.send) {
        sendRef.current?.(text);
      } else {
        setInput(text);
      }
    }
    window.addEventListener("axiom:chat:prefill", onPrefill as EventListener);
    return () => window.removeEventListener("axiom:chat:prefill", onPrefill as EventListener);
  }, []);

  return (
    <div className="card flex flex-col h-[70vh]">
      {!authed && (
        <div className="text-xs text-[var(--text-muted)] mb-2">
          Sign in to enable streaming chat with your data.
        </div>
      )}
      <div ref={scrollRef} className="flex-1 overflow-auto space-y-4 pr-2">
        {loadingHistory ? (
          <div className="text-sm text-[var(--text-muted)]">Loading conversation…</div>
        ) : (
          messages.map((m, i) => (
            <MessageBubble key={i} msg={m} streaming={streaming && i === messages.length - 1} />
          ))
        )}
      </div>
      <ChatComposer
        input={input}
        setInput={setInput}
        send={() => void send()}
        streaming={streaming}
        loadingHistory={loadingHistory}
      />
    </div>
  );
}

/**
 * Composer with an attach-data paperclip. Picking a file uploads it to
 * `/api/datasets/upload` and then fires a global `axiom:dataset:uploaded`
 * event so the workspace can refresh its dataset list, focus the new
 * dataset, and auto-prompt a profile run.
 */
function ChatComposer({
  input,
  setInput,
  send,
  streaming,
  loadingHistory,
}: {
  input: string;
  setInput: (s: string) => void;
  send: () => void;
  streaming: boolean;
  loadingHistory: boolean;
}) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);

  async function onFile(file: File) {
    setUploading(true);
    setUploadErr(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const pid = getActiveProjectId();
      if (pid) form.append("project_id", String(pid));
      form.append("dataset_name", file.name.replace(/\.[^.]+$/, ""));
      const token = getToken();
      const res = await fetch("/api/datasets/upload", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const data = (await res.json()) as { id: number; filename?: string; detail?: string };
      if (!res.ok) throw new Error(data?.detail || "Upload failed");
      window.dispatchEvent(
        new CustomEvent("axiom:dataset:uploaded", {
          detail: { datasetId: data.id, filename: data.filename || file.name },
        })
      );
    } catch (e) {
      setUploadErr(errMessage(e));
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        send();
      }}
      className="mt-3 flex gap-2 items-start"
    >
      <input
        ref={fileRef}
        type="file"
        accept=".csv,.tsv,.xlsx,.xls,.json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) void onFile(f);
        }}
      />
      <button
        type="button"
        onClick={() => fileRef.current?.click()}
        title="Attach a dataset · إرفاق ملف بيانات"
        disabled={uploading || streaming}
        className="px-3 py-2 rounded border border-[var(--border)] text-sm bg-[var(--surface)] hover:bg-[var(--surface-alt)]/60 disabled:opacity-50"
      >
        {uploading ? "↑…" : "📎"}
      </button>
      <div className="flex-1 flex flex-col gap-1">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about your data… · اسأل عن بياناتك"
          className="px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          disabled={loadingHistory}
        />
        {uploadErr && (
          <span className="text-[10px] text-red-500">{uploadErr}</span>
        )}
      </div>
      <button
        type="submit"
        className="btn btn-primary"
        disabled={streaming || loadingHistory || !input.trim()}
      >
        {streaming ? "…" : "Send"}
      </button>
    </form>
  );
}

function MessageBubble({ msg, streaming }: { msg: Msg; streaming: boolean }) {
  if (msg.role === "user") {
    return (
      <div className="text-sm text-right">
        <div className="inline-block px-3 py-2 rounded-lg max-w-[85%] whitespace-pre-wrap bg-[var(--accent)] text-white">
          {msg.content}
        </div>
      </div>
    );
  }
  return (
    <div className="text-sm">
      <div className="inline-block px-3 py-2 rounded-lg max-w-[92%] whitespace-pre-wrap bg-[var(--surface)] border border-[var(--border)]">
        {msg.content || (streaming ? "…" : "")}
      </div>
      {msg.tools && msg.tools.length > 0 && (
        <div className="mt-2 space-y-2 max-w-[92%]">
          {msg.tools.map((t) => (
            <ToolEventCard key={t.callId} ev={t} />
          ))}
        </div>
      )}
    </div>
  );
}

function ToolEventCard({ ev }: { ev: ToolEvent }) {
  const label = toolLabel(ev.tool);
  if (ev.kind === "started") {
    return (
      <div className="border border-[var(--border)] rounded-lg p-3 bg-[var(--surface-alt)]/50 animate-pulse">
        <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
          Running tool
        </div>
        <div className="text-xs font-semibold mt-0.5">{label}…</div>
      </div>
    );
  }
  if (!ev.ok) {
    return (
      <div className="border border-red-500/30 rounded-lg p-3 bg-red-500/10 text-red-600 text-xs">
        {label} failed: {ev.error || "unknown error"}
      </div>
    );
  }
  return (
    <div className="space-y-2">
      {(ev.artifacts ?? []).map((a) => (
        <InlineArtifact key={a.id} artifact={a} />
      ))}
    </div>
  );
}

function toolLabel(tool: string): string {
  if (tool === "make_chart") return "Build chart";
  if (tool === "predict_column") return "Fit prediction model";
  if (tool === "cluster_dataset") return "Cluster rows";
  if (tool === "profile_dataset") return "Profile dataset";
  return tool;
}

function InlineArtifact({ artifact }: { artifact: Artifact }) {
  const [pinned, setPinned] = useState<boolean>(!!artifact.pinned);
  const [busy, setBusy] = useState(false);
  async function togglePin() {
    if (busy) return;
    setBusy(true);
    const next = !pinned;
    try {
      await api(`/api/artifacts/${artifact.id}/pin`, {
        method: "PATCH",
        json: { pinned: next },
      });
      setPinned(next);
      // Let the drawer (and report) refresh its pinned-only views.
      window.dispatchEvent(new CustomEvent("axiom:artifact:pinned", { detail: { id: artifact.id, pinned: next } }));
    } catch {
      /* surface nothing — drawer will reconcile on next refetch */
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="border border-[var(--border)] rounded-lg p-3 bg-[var(--surface)]">
      <div className="flex items-baseline justify-between mb-2 gap-2">
        <div className="text-xs font-semibold truncate">{artifact.title}</div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={togglePin}
            disabled={busy}
            title={pinned ? "Pinned to report · مثبَّت بالتقرير" : "Pin to report · ثبِّت بالتقرير"}
            className={`text-[11px] px-2 py-0.5 rounded border ${
              pinned
                ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/5"
                : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
            } disabled:opacity-50`}
          >
            {pinned ? "📌 Pinned" : "📌 Pin"}
          </button>
          <div className="text-[9px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
            {artifact.kind}
          </div>
        </div>
      </div>
      {artifact.kind === "chart" && (
        <ChartRenderer payload={artifact.result as unknown as ChartPayload} height={200} />
      )}
      {artifact.kind === "prediction" && (
        <PredictionCard title="" result={artifact.result as unknown as PredictionResult} />
      )}
      {artifact.kind === "profile" && (
        <div className="text-[11px] text-[var(--text-muted)]">
          {String((artifact.result as { rows?: number }).rows ?? 0).toLocaleString()} rows ·{" "}
          {String((artifact.result as { cols?: number }).cols ?? 0)} cols. See the Profile tab on the right for the full breakdown.
        </div>
      )}
      {artifact.kind === "cluster" && (
        <div className="text-[11px] text-[var(--text-muted)]">
          k = {String((artifact.result as { k?: number }).k ?? 0)} · sizes:{" "}
          {Object.entries(((artifact.result as { cluster_sizes?: Record<string, number> }).cluster_sizes) || {})
            .map(([k, v]) => `#${k}:${v}`)
            .join(" · ")}
        </div>
      )}
      {artifact.kind === "insight" && (
        <ul className="text-[11px] space-y-0.5">
          {((artifact.result as { items?: Array<{ headline: string; severity: string }> }).items || [])
            .slice(0, 4)
            .map((it, i) => (
              <li key={i}>
                <span className="font-mono uppercase tracking-widest text-[10px] text-[var(--text-muted)] mr-1">
                  {it.severity}
                </span>
                {it.headline}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
