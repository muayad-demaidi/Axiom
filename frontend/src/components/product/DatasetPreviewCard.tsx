"use client";
/**
 * "Just landed" view for a dataset inside a chat session: first ~10–20
 * rows, a Surprise-insights ribbon, and 5–8 CRISP-DM-aligned suggested
 * questions the user can click to fire the chat.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { InteractiveTable } from "./InteractiveTable";

type Preview = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
  columns: { name: string; dtype: string }[];
  preview: Record<string, unknown>[];
};

type Insight = {
  kind: string;
  severity: "info" | "warn" | "good";
  headline: string;
  subtitle?: string;
};

const SEV_BG: Record<string, string> = {
  info: "bg-[var(--accent)]/10 text-[var(--accent)] border-[var(--accent)]/30",
  warn: "bg-amber-500/10 text-amber-600 border-amber-500/30",
  good: "bg-emerald-500/10 text-emerald-600 border-emerald-500/30",
};

export function DatasetPreviewCard({
  datasetId,
  onAskQuestion,
  onAskAboutCell,
}: {
  datasetId: number;
  onAskQuestion: (q: string) => void;
  onAskAboutCell?: (column: string, value: unknown) => void;
}) {
  const [preview, setPreview] = useState<Preview | null>(null);
  const [insights, setInsights] = useState<Insight[] | null>(null);
  const [suggestions, setSuggestions] = useState<string[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setPreview(null);
    setInsights(null);
    setSuggestions(null);
    Promise.all([
      api<Preview>(`/api/datasets/${datasetId}/preview?rows=20`),
      api<{ insights: Insight[] }>(`/api/datasets/${datasetId}/insights`),
      api<{ suggestions: string[] }>(`/api/datasets/${datasetId}/suggestions`),
    ])
      .then(([p, i, s]) => {
        if (cancelled) return;
        setPreview(p);
        setInsights(i.insights ?? []);
        setSuggestions(s.suggestions ?? []);
      })
      .catch((e) => {
        if (!cancelled) setError(errMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  return (
    <div className="border border-[var(--border)] rounded-xl bg-[var(--surface)] p-4 space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)]">
            Dataset attached to this chat
          </div>
          <div className="font-semibold text-sm mt-0.5">
            {preview?.dataset_name || preview?.filename || "Loading…"}
          </div>
        </div>
        {preview && (
          <div className="text-[10px] text-[var(--text-muted)] font-mono">
            {preview.rows.toLocaleString()} rows × {preview.cols} cols
          </div>
        )}
      </div>

      {error && (
        <div className="text-xs text-red-500 border border-red-500/30 rounded p-2">
          {error}
        </div>
      )}

      {/* Surprise insights ribbon */}
      {insights && insights.length > 0 && (
        <div>
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-1.5">
            Surprise insights
          </div>
          <div className="flex flex-wrap gap-2">
            {insights.map((it, i) => (
              <div
                key={i}
                className={`text-[11px] px-2.5 py-1.5 rounded-lg border ${SEV_BG[it.severity] || SEV_BG.info}`}
                title={it.subtitle || ""}
              >
                {it.headline}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Preview table */}
      {preview && (
        <div>
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-1.5">
            First {preview.preview.length} rows
          </div>
          <InteractiveTable
            columns={preview.columns}
            rows={preview.preview}
            maxHeight={260}
            onAskAboutCell={onAskAboutCell}
          />
        </div>
      )}

      {/* Suggested questions */}
      {suggestions && suggestions.length > 0 && (
        <div>
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-1.5">
            Try one of these
          </div>
          <div className="flex flex-wrap gap-2">
            {suggestions.map((q, i) => (
              <button
                key={i}
                onClick={() => onAskQuestion(q)}
                className="text-[11px] px-2.5 py-1.5 rounded-full border border-[var(--border)] bg-[var(--surface-alt)] hover:bg-[var(--accent)] hover:text-white hover:border-[var(--accent)] transition-colors text-left"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
