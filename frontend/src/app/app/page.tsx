"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { useMode } from "@/lib/modeContext";
import { ModeToggle } from "@/components/product/ModeToggle";
import { FloatingComposer } from "@/components/product/FloatingComposer";

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
  }, [router]);

  async function start(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<QuickStartResponse>("/api/chats/quick", {
        method: "POST",
        json: {},
      });
      router.push(
        `/app/project/${res.project_id}?session=${res.session_id}&q=${encodeURIComponent(trimmed)}`
      );
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setError(errMessage(e));
    } finally {
      setBusy(false);
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

        <div className="mt-8 mx-auto">
          <FloatingComposer
            value={input}
            onValueChange={setInput}
            onSubmit={(text) => {
              setInput(text);
              start(text);
            }}
            placeholder={placeholder}
            busy={busy}
            attachHref="/app/upload?back=/app"
            connectorsHref="/app/connectors"
            sendLayoutId="axiom-composer-send"
          />
        </div>

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
