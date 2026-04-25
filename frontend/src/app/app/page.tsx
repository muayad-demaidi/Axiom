"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { useMode } from "@/lib/modeContext";
import { ModeToggle } from "@/components/product/ModeToggle";

type QuickStartResponse = {
  project_id: number;
  session_id: number;
};

const GUIDED_SUGGESTIONS = [
  "Show me what's in my latest upload",
  "Spot anything unusual in my data",
  "What were my best months last year?",
  "Group my customers into similar buckets",
];

const EXPERT_SUGGESTIONS = [
  "Run STL decomposition on monthly_sales and forecast 6 periods",
  "Drop columns >40% null, KNN-impute the rest, then profile",
  "Fit XGBoost regressor with 5-fold CV and report RMSE / MAE",
  "K-Means RFM segmentation on customers, k=4, return cluster centroids",
];

export default function ProductHome() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement | null>(null);
  const { mode } = useMode();
  const suggestions = mode === "expert" ? EXPERT_SUGGESTIONS : GUIDED_SUGGESTIONS;
  const placeholder =
    mode === "expert"
      ? "Describe the analysis (algorithm, params, columns)…"
      : "Ask anything about your data… (e.g. forecast next 6 months from sales.csv)";

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    taRef.current?.focus();
  }, [router]);

  // Grow the textarea with content, capped.
  useEffect(() => {
    const el = taRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 240) + "px";
  }, [input]);

  async function start(initial?: string) {
    const text = (initial ?? input).trim();
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<QuickStartResponse>("/api/chats/quick", {
        method: "POST",
        json: {},
      });
      router.push(
        `/app/project/${res.project_id}?session=${res.session_id}&q=${encodeURIComponent(text)}`
      );
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      start();
    }
  }

  return (
    <div className="min-h-[calc(100vh-7rem)] flex items-start justify-center pt-16">
      <div className="w-full max-w-3xl text-center">
        <div className="text-[11px] font-mono uppercase tracking-[0.25em] text-[var(--text-muted)] mb-3">
          Project-aware data analyst
        </div>
        <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">
          {mode === "expert"
            ? "What analysis should we run?"
            : "What do you want to analyze today?"}
        </h1>
        <p className="text-[var(--text-muted)] mt-3 text-sm">
          {mode === "expert"
            ? "Describe the algorithm, parameters and columns. Methods, metrics and JSON stay visible."
            : "Drop a question, attach a file, or pick from a suggestion. Every chat remembers your data and follows a transparent methodology."}
        </p>
        <div className="mt-4 flex items-center justify-center gap-2">
          <ModeToggle size="sm" />
          <span className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
            applies to new chats
          </span>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            start();
          }}
          className="mt-8 mx-auto"
        >
          <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-sm p-3 text-left">
            <textarea
              ref={taRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder={placeholder}
              rows={1}
              className="w-full resize-none bg-transparent outline-none text-sm leading-6 text-[var(--text)] placeholder:text-[var(--text-muted)] px-1 py-2"
              disabled={busy}
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                <Link
                  href="/app/upload?back=/app"
                  className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1.5 rounded-md hover:bg-[var(--surface-alt)]"
                  title="Upload a CSV or Excel file"
                >
                  <PaperclipIcon /> <span>Attach data</span>
                </Link>
                <Link
                  href="/app/connectors"
                  className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1.5 rounded-md hover:bg-[var(--surface-alt)]"
                  title="Connect to a data source"
                >
                  <PlugIcon /> <span>Connectors</span>
                </Link>
              </div>
              <button
                type="submit"
                disabled={busy || !input.trim()}
                className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-[var(--accent)] text-white disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
                aria-label="Send"
              >
                {busy ? "…" : <ArrowUpIcon />}
              </button>
            </div>
          </div>
        </form>

        {error && <div className="text-red-600 text-sm mt-3">{error}</div>}

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => start(s)}
              disabled={busy}
              className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] border border-[var(--border)] hover:border-[var(--accent)] rounded-full px-3 py-1.5 transition-colors"
            >
              {s}
            </button>
          ))}
        </div>

        <div className="mt-10 text-xs text-[var(--text-muted)]">
          Looking for an existing project?{" "}
          <Link href="/app/projects" className="text-[var(--accent)] hover:underline">
            Open the projects index
          </Link>
          .
        </div>
      </div>
    </div>
  );
}

function PaperclipIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05 12.25 20.24a6 6 0 1 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

function PlugIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 2v6M15 2v6M5 8h14v4a7 7 0 0 1-14 0V8zM12 19v3" />
    </svg>
  );
}

function ArrowUpIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}
