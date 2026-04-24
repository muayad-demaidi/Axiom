"use client";
import { useEffect, useRef, useState } from "react";
import { api, getToken, streamPost } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";

type Msg = { role: "user" | "assistant"; content: string };

type StoredMessage = {
  id: number;
  user_message: string;
  ai_response: string;
};

type ChatPanelProps = {
  /** When provided, the panel becomes session-anchored: history is
   * loaded from the server and turns are persisted under the session. */
  sessionId?: number | null;
  /** Called after a successful streaming turn so the parent can refresh
   * its session list (recency / auto-titles). */
  onTurnComplete?: () => void;
  /** Hint used to set a friendlier empty-state message. */
  hasData?: boolean;
};

const GREETING_NEW =
  "Hey — drop a question about any dataset in this project and I'll walk through the analysis step-by-step. I can see all your data here, so feel free to ask across files.";
const GREETING_NO_DATA =
  "This project doesn't have any data yet. Upload a CSV or Excel file from the sidebar and I'll start analysing it.";

export function ChatPanel({ sessionId = null, onTurnComplete, hasData = true }: ChatPanelProps) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [authed, setAuthed] = useState(true);
  const [loadingHistory, setLoadingHistory] = useState(!!sessionId);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setAuthed(!!getToken());
  }, []);

  // Load session history when session changes.
  useEffect(() => {
    let cancelled = false;
    if (!sessionId) {
      setMessages([
        {
          role: "assistant",
          content: hasData ? GREETING_NEW : GREETING_NO_DATA,
        },
      ]);
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
          flat.push({
            role: "assistant",
            content: hasData ? GREETING_NEW : GREETING_NO_DATA,
          });
        }
        setMessages(flat);
      })
      .catch(() => {
        if (!cancelled) {
          setMessages([
            {
              role: "assistant",
              content: "Could not load chat history.",
            },
          ]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingHistory(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, hasData]);

  // Auto-scroll on new content.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function send() {
    if (!input.trim() || streaming) return;
    const userMsg: Msg = { role: "user", content: input };
    const nextHistory = [...messages, userMsg];
    setMessages([...nextHistory, { role: "assistant", content: "" }]);
    setInput("");
    setStreaming(true);
    let acc = "";
    try {
      await streamPost(
        "/api/chat/stream",
        {
          messages: nextHistory,
          session_id: sessionId,
          // Legacy fields — only used when there's no session.
          dataset_id: sessionId ? null : getActiveDatasetId(),
          project_id: sessionId ? null : getActiveProjectId(),
        },
        (chunk) => {
          acc += chunk;
          setMessages((m) => {
            const copy = m.slice();
            copy[copy.length - 1] = { role: "assistant", content: acc };
            return copy;
          });
        }
      );
      onTurnComplete?.();
    } catch (e: unknown) {
      setMessages((m) => {
        const copy = m.slice();
        copy[copy.length - 1] = {
          role: "assistant",
          content: acc || `(Chat error: ${errMessage(e, "request failed")}.)`,
        };
        return copy;
      });
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="card flex flex-col h-[70vh]">
      {!authed && (
        <div className="text-xs text-[var(--text-muted)] mb-2">
          Sign in to enable streaming chat with your data.
        </div>
      )}
      <div ref={scrollRef} className="flex-1 overflow-auto space-y-3 pr-2">
        {loadingHistory ? (
          <div className="text-sm text-[var(--text-muted)]">Loading conversation…</div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={`text-sm ${m.role === "user" ? "text-right" : ""}`}>
              <div
                className={`inline-block px-3 py-2 rounded-lg max-w-[85%] whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-[var(--accent)] text-white"
                    : "bg-[var(--surface)] border border-[var(--border)]"
                }`}
              >
                {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
              </div>
            </div>
          ))
        )}
      </div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="mt-3 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about your data…"
          className="flex-1 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          disabled={loadingHistory}
        />
        <button
          type="submit"
          className="btn btn-primary"
          disabled={streaming || loadingHistory || !input.trim()}
        >
          {streaming ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
