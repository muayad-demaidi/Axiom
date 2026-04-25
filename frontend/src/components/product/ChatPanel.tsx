"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  CheckCircle2,
  Sparkles,
  Stethoscope,
  UploadCloud,
} from "lucide-react";
import { api, getToken, streamPostNDJSON } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import { ChartRenderer, type ChartPayload } from "./Charts";
import { PredictionCard, type PredictionResult } from "./PredictionCard";
import { FloatingComposer, type FloatingComposerHandle } from "./FloatingComposer";
import type { Artifact, PendingTool } from "./ArtifactDrawer";

type ToolEvent =
  | { kind: "started"; tool: string; callId: string; params: Record<string, unknown> }
  | { kind: "finished"; tool: string; callId: string; ok: boolean; summary?: unknown; artifacts?: Artifact[]; error?: string };

type Msg =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string; tools?: ToolEvent[] };

// Inline AI suggestion chips by mode — these render only on a fresh
// thread (greeting only) and disappear once a real exchange starts.
const GUIDED_CHIPS = [
  "Show me a quick summary",
  "What stands out in this data?",
  "Make a chart of the most important trend",
];
const EXPERT_CHIPS = [
  "Profile dtypes & null ratios per column",
  "Pearson correlation matrix on numeric cols",
  "Train baseline model + report cross-val metrics",
];

// Strip the [switch_to_expert] sentinel from a streamed assistant
// response and return both the cleaned text and a flag the bubble can
// use to render the inline switch CTA. We accept the marker on its own
// line or trailing the response, with optional trailing whitespace /
// punctuation the model sometimes appends.
function parseSwitchHandoff(text: string): { body: string; cta: string | null } {
  const re = /\n?\[switch_to_expert\][^\n]*\s*$/i;
  const match = text.match(re);
  if (!match) return { body: text, cta: null };
  const cta = match[0]
    .replace(/^\n?\[switch_to_expert\]\s*/i, "")
    .trim();
  return {
    body: text.slice(0, match.index).trimEnd(),
    cta: cta || "Switch to Expert Mode for the full breakdown",
  };
}

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
  /** When set, the chat is scoped to a project and the mode toggle on
   * the inline "switch" CTA edits the project mode override. */
  projectId?: number | null;
  /** Reports the streaming state up to the parent so the Data context
   * bar can flip its status pill between Idle / Analyzing. */
  onStreamingChange?: (streaming: boolean) => void;
};

const GREETING_NEW =
  "Hey — drop a question about any dataset in this project and I'll walk through the analysis step-by-step. I can run charts, predictions, profiling, and clustering directly from chat.";
const GREETING_NO_DATA =
  "This project doesn't have any data yet. Upload a CSV or Excel file from the sidebar and I'll start analysing it.";

const FOLLOWUP_CHIPS = [
  "Show outliers",
  "Visualize trends",
  "Forecast next period",
  "Summarise key insights",
];

export function ChatPanel({
  sessionId = null,
  onTurnComplete,
  onTurnEnded,
  hasData = true,
  initialPrompt = null,
  onInitialPromptConsumed,
  onToolStarted,
  onToolFinished,
  projectId = null,
  onStreamingChange,
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
  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  // Mutable near-bottom flag — read inside the auto-scroll effect
  // without re-binding the scroll listener every render. Mirrored into
  // `isNearBottom` state so the "Jump to latest" pill can re-render.
  const nearBottomRef = useRef(true);
  const [isNearBottom, setIsNearBottom] = useState(true);
  // Tracks whether the initial (instant) scroll-to-bottom on mount has
  // already fired so a long history doesn't visibly auto-scroll on entry.
  const didInitialScrollRef = useRef(false);
  // One-shot flag set by the user-initiated `send()` so the next render
  // is guaranteed to scroll to bottom even if the reader is scrolled up.
  // We can't infer this from the message list alone because `send()`
  // immediately seeds an empty assistant bubble after the user message,
  // so the *last* message after submit is always `assistant`, not `user`.
  const forceFollowRef = useRef(false);
  // Becomes true the moment assistant content lands while the reader is
  // scrolled away from the bottom. Drives the "Jump to latest" pill
  // *after* streaming ends — without it the pill would vanish the
  // instant the stream finished and strand the reader mid-history.
  // Reset to false whenever the reader returns to (or jumps to) bottom.
  const [hasMissedContent, setHasMissedContent] = useState(false);
  const composerRef = useRef<FloatingComposerHandle | null>(null);
  const consumedPromptRef = useRef<string | null>(null);
  const sendRef = useRef<((text?: string) => Promise<void>) | null>(null);
  // The toggle inside an actual project edits that project's mode; on
  // the home page (no projectId) it edits the user-level preference.
  const { mode, setMode } = useMode(projectId ?? null);
  const chips = useMemo(() => (mode === "expert" ? EXPERT_CHIPS : GUIDED_CHIPS), [mode]);
  const [uploading, setUploading] = useState(false);
  const [uploadErr, setUploadErr] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  // Counter so nested dragenter/dragleave events on child elements don't
  // make the overlay flicker. We only hide once the counter hits zero.
  const dragCounter = useRef(0);

  const ACCEPTED_EXTS = useMemo(
    () => [".csv", ".tsv", ".xlsx", ".xls", ".json"],
    []
  );

  useEffect(() => {
    setAuthed(!!getToken());
  }, []);

  useEffect(() => {
    onStreamingChange?.(streaming);
  }, [streaming, onStreamingChange]);

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

  // Recompute "near bottom" on every scroll. ~150px threshold matches
  // the spec — anything closer than that means the reader is effectively
  // pinned to the latest content and wants to keep following.
  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
    const near = distance <= 150;
    nearBottomRef.current = near;
    setIsNearBottom((cur) => (cur === near ? cur : near));
    // Returning to bottom dismisses the missed-content flag so the
    // "Jump to latest" pill hides automatically once you catch up.
    if (near) setHasMissedContent((cur) => (cur ? false : cur));
  }, []);

  // Geometry can change without a scroll event firing — most notably
  // when the artifact drawer opens/closes (it changes the chat slot's
  // width and therefore the message layout height) or when the user
  // resizes the window. ResizeObserver covers both because the scroll
  // viewport itself reflows in those cases. Without this, the pill and
  // auto-follow gating would stay stale until the user touched scroll.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => handleScroll());
    ro.observe(el);
    window.addEventListener("resize", handleScroll);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", handleScroll);
    };
  }, [handleScroll]);

  // Honour the user's reduced-motion preference for the auto-follow
  // animation. `useReducedMotion` is already imported for the composer
  // morph; reusing it keeps a single source of truth.
  const reduceMotion = useReducedMotion();
  const scrollBehavior: ScrollBehavior = reduceMotion ? "auto" : "smooth";

  // Smart auto-scroll: follow new content when the reader is near the
  // bottom or has just sent a message; stay put when they've scrolled
  // up to read history. Uses native `scrollIntoView` (no custom JS loop)
  // so long viewports stay efficient.
  useEffect(() => {
    if (loadingHistory) return;
    // Effects run in declaration order, so on the very first paint this
    // effect would otherwise smooth-scroll to bottom milliseconds before
    // the initial-jump effect below instant-snaps to the same place,
    // producing a tiny visible animation on entry. Skip until the
    // initial instant-jump has run; it sets nearBottomRef = true and
    // any subsequent message change will be handled by this effect.
    if (!didInitialScrollRef.current) return;
    // Force-follow path: the user just submitted via `send()`. This MUST
    // win over the reader's scroll position (per spec: "Sending a new
    // user message always scrolls to the bottom regardless of current
    // scroll position"). Checked before the near-bottom branch because
    // after submit the last message is the seeded empty assistant
    // bubble, not the user's — a role-based heuristic would miss it.
    if (forceFollowRef.current) {
      forceFollowRef.current = false;
      nearBottomRef.current = true;
      setIsNearBottom(true);
      setHasMissedContent(false);
      messagesEndRef.current?.scrollIntoView({ behavior: scrollBehavior, block: "end" });
      return;
    }
    if (nearBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: scrollBehavior, block: "end" });
    } else {
      // The reader is scrolled up and new content just landed without
      // their consent — flag it so the pill stays visible after the
      // stream finishes.
      const last = messages[messages.length - 1];
      if (last && last.role === "assistant") {
        setHasMissedContent((cur) => (cur ? cur : true));
      }
    }
  }, [messages, streaming, loadingHistory, scrollBehavior]);

  // First paint: jump straight to the bottom (no smooth animation) so
  // opening a long thread doesn't visibly auto-scroll on entry. Runs
  // once per mount; ProjectWorkspace re-keys this component on session
  // change so the next chat re-runs this effect cleanly.
  useEffect(() => {
    if (loadingHistory) return;
    if (didInitialScrollRef.current) return;
    didInitialScrollRef.current = true;
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    nearBottomRef.current = true;
    setIsNearBottom(true);
  }, [loadingHistory, messages.length]);

  async function send(forceText?: string) {
    const text = (forceText ?? input).trim();
    if (!text || streaming) return;
    // Signal to the smart auto-scroll effect that the upcoming
    // setMessages was user-initiated and must scroll to bottom even if
    // the reader had scrolled up. Consumed (and cleared) on the very
    // next render of the effect.
    forceFollowRef.current = true;
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
          assistant_mode: mode,
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
        // Focus so the user can refine and hit Enter.
        setTimeout(() => composerRef.current?.focus(), 0);
      }
    }
    window.addEventListener("axiom:chat:prefill", onPrefill as EventListener);
    return () => window.removeEventListener("axiom:chat:prefill", onPrefill as EventListener);
  }, []);

  async function handleAttachFile(file: File) {
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
    }
  }

  function handleChipClick(text: string) {
    setInput(text);
    setTimeout(() => composerRef.current?.focus(), 0);
  }

  function isAcceptedFile(file: File): boolean {
    const name = file.name.toLowerCase();
    return ACCEPTED_EXTS.some((ext) => name.endsWith(ext));
  }

  // Only react to drag events that are actually carrying files — ignore
  // text selections, dragged links, etc.
  function dragHasFiles(e: React.DragEvent<HTMLDivElement>): boolean {
    const types = e.dataTransfer?.types;
    if (!types) return false;
    for (let i = 0; i < types.length; i++) {
      if (types[i] === "Files") return true;
    }
    return false;
  }

  function onDragEnter(e: React.DragEvent<HTMLDivElement>) {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    dragCounter.current += 1;
    if (!dragActive) setDragActive(true);
  }

  function onDragOver(e: React.DragEvent<HTMLDivElement>) {
    if (!dragHasFiles(e)) return;
    // Required to let the drop event fire on this surface.
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
  }

  function onDragLeave(e: React.DragEvent<HTMLDivElement>) {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    dragCounter.current = Math.max(0, dragCounter.current - 1);
    if (dragCounter.current === 0) setDragActive(false);
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    if (!dragHasFiles(e)) return;
    e.preventDefault();
    dragCounter.current = 0;
    setDragActive(false);
    const files = e.dataTransfer?.files;
    if (!files || files.length === 0) return;
    // Mirror the paperclip flow: only one file at a time.
    const file = files[0];
    if (!isAcceptedFile(file)) {
      setUploadErr(
        `Unsupported file type. Drop a CSV, TSV, Excel, or JSON file.`
      );
      return;
    }
    void handleAttachFile(file);
  }

  // Manually trigger the jump-to-latest pill action: re-engage auto-follow
  // and scroll to the end of the conversation (smoothly unless the user
  // prefers reduced motion).
  const jumpToLatest = useCallback(() => {
    nearBottomRef.current = true;
    setIsNearBottom(true);
    setHasMissedContent(false);
    messagesEndRef.current?.scrollIntoView({ behavior: scrollBehavior, block: "end" });
  }, [scrollBehavior]);

  // Pill appears specifically when new assistant content is arriving
  // (or has arrived) while the reader is scrolled up — NOT just because
  // a long thread is sitting paused. The `hasMissedContent` half keeps
  // the pill visible briefly after streaming ends so a reader who
  // scrolled up mid-stream still has a one-click way back.
  const showJumpPill =
    !loadingHistory && !isNearBottom && (streaming || hasMissedContent);

  return (
    <div
      className="relative flex flex-col h-full min-h-0 gap-4"
      onDragEnter={onDragEnter}
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
    >
      <AnimatePresence>
        {dragActive && (
          <motion.div
            key="dropzone-overlay"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12, ease: "easeOut" }}
            // Pointer-events:none so the underlying chat surface still
            // emits dragover/drop events through the overlay.
            className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center rounded-2xl border-2 border-dashed border-[var(--accent)] bg-[color-mix(in_srgb,var(--accent)_8%,var(--surface))]/85 backdrop-blur-sm"
            aria-hidden="true"
          >
            <div className="flex flex-col items-center gap-2 text-center px-6">
              <span
                className="inline-flex items-center justify-center h-10 w-10 rounded-full"
                style={{
                  background: "color-mix(in srgb, var(--accent) 18%, transparent)",
                  color: "var(--accent)",
                }}
              >
                <UploadCloud className="h-5 w-5" />
              </span>
              <div className="text-sm font-semibold text-[var(--text)]">
                Drop to upload
              </div>
              <div className="text-[11px] text-[var(--text-muted)]">
                CSV, TSV, Excel, or JSON
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {!authed && (
        <div className="text-xs text-[var(--text-muted)] shrink-0">
          Sign in to enable streaming chat with your data.
        </div>
      )}
      {/* Message viewport wrapper. The wrapper itself is `relative` and
          does NOT scroll — its child is the scroll container. This lets
          the "Jump to latest" pill be absolutely positioned relative to
          the visible viewport (`bottom-3 right-3`) rather than scrolling
          with the message content. */}
      <div className="relative flex-1 min-h-0 flex flex-col">
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          className="flex-1 min-h-0 overflow-y-auto space-y-4 pr-1"
        >
          {loadingHistory ? (
            <div className="text-sm text-[var(--text-muted)]">Loading conversation…</div>
          ) : (
            <>
              {messages.map((m, i) => {
                const isLast = i === messages.length - 1;
                const isStreamingThis = streaming && isLast;
                // The very first synthetic greeting doesn't get follow-up
                // chips — they only appear under real assistant turns.
                const isGreeting = i === 0 && messages.length === 1;
                return (
                  <ChatMessage
                    key={i}
                    msg={m}
                    streaming={isStreamingThis}
                    showChips={
                      !isStreamingThis &&
                      !isGreeting &&
                      m.role === "assistant" &&
                      !!m.content
                    }
                    onChipClick={handleChipClick}
                    projectId={projectId}
                    mode={mode}
                    setMode={setMode}
                  />
                );
              })}
              {/* Inline mode-aware suggestion chips on a fresh thread. */}
              {!streaming &&
                messages.length <= 1 &&
                messages[0]?.role !== "user" && (
                  <div className="pt-1 flex flex-wrap gap-1.5">
                    {chips.map((c) => (
                      <button
                        key={c}
                        type="button"
                        onClick={() => void send(c)}
                        className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text)] border border-[var(--border)] hover:border-[var(--accent)] rounded-full px-2.5 py-1 transition-colors"
                      >
                        {c}
                      </button>
                    ))}
                  </div>
                )}
              {/* Sentinel for the smart auto-scroll effect. Kept as the
                  very last child of the scroll container. */}
              <div ref={messagesEndRef} aria-hidden="true" />
            </>
          )}
        </div>
        {/* Jump-to-latest pill: anchored to the visible bottom-right of
            the viewport wrapper (NOT inside the scroller, so it doesn't
            scroll with content). z-10 keeps it above message bubbles;
            the composer sibling below has no positive z-index so it
            naturally renders on top of everything in this column. */}
        <AnimatePresence>
          {showJumpPill && (
            <motion.button
              key="jump-to-latest"
              type="button"
              onClick={jumpToLatest}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 6 }}
              transition={{ duration: 0.15, ease: "easeOut" }}
              className="absolute bottom-3 right-3 z-10 inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)]/95 backdrop-blur px-3 py-1.5 text-[11px] font-medium text-[var(--text)] shadow-sm hover:border-[var(--accent)] hover:text-[var(--accent)]"
              aria-label="Jump to latest message"
            >
              <ArrowDown className="h-3 w-3" />
              <span>Jump to latest</span>
            </motion.button>
          )}
        </AnimatePresence>
      </div>
      <div className="shrink-0">
        <FloatingComposer
          ref={composerRef}
          value={input}
          onValueChange={setInput}
          onSubmit={(text) => {
            // Clear the composer first so the user gets immediate
            // feedback that their message was sent — `send(text)` reads
            // its own copy of the text via the forceText arg, so this
            // doesn't drop the message.
            setInput("");
            void send(text);
          }}
          placeholder={
            mode === "expert"
              ? "Describe the analysis (algorithm, params, columns)…"
              : "Ask anything about your data… · اسأل عن بياناتك"
          }
          busy={streaming}
          disabled={loadingHistory}
          onAttachFile={handleAttachFile}
          attachBusy={uploading}
          connectorsHref="/app/connectors"
          errorText={uploadErr}
          sendLayoutId="axiom-composer-send"
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Message rendering
// ---------------------------------------------------------------------------

function ChatMessage({
  msg,
  streaming,
  showChips,
  onChipClick,
  projectId,
  mode,
  setMode,
}: {
  msg: Msg;
  streaming: boolean;
  showChips: boolean;
  onChipClick: (text: string) => void;
  projectId?: number | null;
  mode: string;
  setMode: (m: "guided" | "expert") => Promise<void>;
}) {
  const reduceMotion = useReducedMotion();
  if (msg.role === "user") {
    return (
      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.15, ease: "easeOut" }}
        className="text-sm flex justify-end"
      >
        <div
          className="inline-block px-3 py-2 rounded-2xl rounded-br-sm max-w-[85%] whitespace-pre-wrap bg-[var(--accent)] text-white shadow-sm"
        >
          {msg.content}
        </div>
      </motion.div>
    );
  }

  const { body, cta } = parseSwitchHandoff(msg.content);
  const meta = inferAssistantMeta(body);
  const Icon = meta.Icon;
  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.16, ease: "easeOut" }}
      className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-sm overflow-hidden"
    >
      <div className="px-4 pt-3 pb-2 flex items-center gap-2">
        <span
          className="inline-flex items-center justify-center h-6 w-6 rounded-full"
          style={{
            background: "color-mix(in srgb, var(--accent) 14%, transparent)",
            color: "var(--accent)",
          }}
        >
          <Icon className="h-3.5 w-3.5" />
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)]">
          {meta.label}
        </span>
      </div>
      <div className="px-4 pb-3 prose-mark text-sm">
        <div className="whitespace-pre-wrap leading-relaxed">
          {body || (streaming ? <StreamingDots /> : "")}
        </div>
        {cta && mode === "guided" && (
          <div className="mt-2.5">
            <button
              type="button"
              onClick={() => void setMode("expert")}
              className="inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-white transition-colors"
            >
              <span aria-hidden>↗</span> {cta}
            </button>
          </div>
        )}
      </div>
      {msg.tools && msg.tools.length > 0 && (
        <div className="px-4 pb-3 space-y-2">
          {msg.tools.map((t) => (
            <ToolEventCard key={t.callId} ev={t} />
          ))}
        </div>
      )}
      <AnimatePresence initial={false}>
        {showChips && (
          <motion.div
            initial={reduceMotion ? false : { opacity: 0, y: -2 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -2 }}
            transition={{ duration: 0.16, ease: "easeOut" }}
            className="px-4 pb-3 pt-1 border-t border-[var(--border)] flex flex-wrap gap-1.5"
          >
            <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)] mr-1 self-center">
              Try
            </span>
            {FOLLOWUP_CHIPS.slice(0, 3).map((chip) => (
              <button
                key={chip}
                type="button"
                onClick={() => onChipClick(chip)}
                className="text-[11px] px-2.5 py-1 rounded-full border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--accent)] hover:border-[var(--accent)] transition-colors"
              >
                {chip}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function StreamingDots() {
  return (
    <span className="inline-flex items-center gap-1 text-[var(--text-muted)]">
      <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
      <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse [animation-delay:120ms]" />
      <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse [animation-delay:240ms]" />
    </span>
  );
}

type Meta = { label: string; Icon: typeof Sparkles };

function inferAssistantMeta(text: string): Meta {
  const t = (text || "").toLowerCase();
  if (/diagnos|scan|profile|missing values|data quality/.test(t)) {
    return { label: "Diagnostics", Icon: Stethoscope };
  }
  if (/warning|caution|outlier|anomal|risk|fail/.test(t)) {
    return { label: "Warning", Icon: AlertTriangle };
  }
  if (/done|complete|success|✓|finished|ready/.test(t)) {
    return { label: "Success", Icon: CheckCircle2 };
  }
  if (/forecast|trend|seasonal|predict|model/.test(t)) {
    return { label: "Insight", Icon: Activity };
  }
  return { label: "AXIOM", Icon: Sparkles };
}

// ---------------------------------------------------------------------------
// Tool result rendering (kept from previous implementation, retuned)
// ---------------------------------------------------------------------------

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
  const summary = (ev.summary ?? null) as null | {
    kind?: string;
    notice?: { message_en?: string; message_ar?: string };
  };
  if (summary && summary.kind === "small_sample_notice" && summary.notice) {
    return <SmallSampleNotice notice={summary.notice} />;
  }
  return (
    <div className="space-y-2">
      {(ev.artifacts ?? []).map((a) => (
        <InlineArtifact key={a.id} artifact={a} />
      ))}
    </div>
  );
}

function SmallSampleNotice({
  notice,
}: {
  notice: { message_en?: string; message_ar?: string };
}) {
  return (
    <div className="border border-[var(--border)] rounded-lg p-3 bg-[var(--surface-alt)]/40 text-xs space-y-2">
      <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
        Note · ملاحظة
      </div>
      {notice.message_en && (
        <p className="leading-snug text-[var(--text)]">{notice.message_en}</p>
      )}
      {notice.message_ar && (
        <p className="leading-snug text-[var(--text)]" dir="rtl" lang="ar">
          {notice.message_ar}
        </p>
      )}
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
  // Memoize result casts so re-renders don't churn child components.
  const chartPayload = useMemo(
    () => artifact.result as unknown as ChartPayload,
    [artifact.result]
  );
  const predictionResult = useMemo(
    () => artifact.result as unknown as PredictionResult,
    [artifact.result]
  );
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
      window.dispatchEvent(
        new CustomEvent("axiom:artifact:pinned", { detail: { id: artifact.id, pinned: next } })
      );
    } catch {
      /* surface nothing — drawer will reconcile on next refetch */
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="border border-[var(--border)] rounded-lg p-3 bg-[var(--surface-alt)]/40">
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
        <ChartRenderer payload={chartPayload} height={200} />
      )}
      {artifact.kind === "prediction" && (
        <PredictionCard title="" result={predictionResult} />
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

