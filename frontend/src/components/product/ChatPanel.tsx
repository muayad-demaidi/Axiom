"use client";
import { useEffect, useState } from "react";
import { getToken, streamPost } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";

type Msg = { role: "user" | "assistant"; content: string };

export function ChatPanel() {
  const [messages, setMessages] = useState<Msg[]>([
    { role: "assistant", content: "Hello — drop a question about your data and I'll answer in your language." },
  ]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [authed, setAuthed] = useState(true);

  useEffect(() => { setAuthed(!!getToken()); }, []);

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
          dataset_id: getActiveDatasetId(),
          project_id: getActiveProjectId(),
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
    <div className="card flex flex-col h-[60vh]">
      {!authed && (
        <div className="text-xs text-[var(--text-muted)] mb-2">
          Sign in to enable streaming chat with your data.
        </div>
      )}
      <div className="flex-1 overflow-auto space-y-3 pr-2">
        {messages.map((m, i) => (
          <div key={i} className={`text-sm ${m.role === "user" ? "text-right" : ""}`}>
            <div className={`inline-block px-3 py-2 rounded-lg max-w-[85%] whitespace-pre-wrap ${m.role === "user" ? "bg-[var(--accent)] text-white" : "bg-[var(--surface)]"}`}>
              {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
            </div>
          </div>
        ))}
      </div>
      <form
        onSubmit={(e) => { e.preventDefault(); send(); }}
        className="mt-3 flex gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask anything about your dataset…"
          className="flex-1 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
        />
        <button type="submit" className="btn btn-primary" disabled={streaming}>
          {streaming ? "…" : "Send"}
        </button>
      </form>
    </div>
  );
}
