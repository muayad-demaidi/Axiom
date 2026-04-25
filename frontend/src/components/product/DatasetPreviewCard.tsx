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

type ProfileColumn = {
  name: string;
  dtype: string;
  kind?: "numeric" | "datetime" | "categorical";
  missing_pct?: number;
  unique?: number;
};

type Profile = {
  rows: number;
  cols: number;
  duplicate_rows?: number;
  memory_kb?: number;
  columns: ProfileColumn[];
};

type AutoProfile = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
  columns: { name: string; dtype: string }[];
  preview: Record<string, unknown>[];
  profile: Profile;
  insights: Insight[];
  suggestions: string[];
};

type Insight = {
  kind: string;
  severity: "info" | "warn" | "good";
  headline: string;
  subtitle?: string;
};

function profileNarrative(p: Profile | undefined): string {
  if (!p) return "";
  const parts: string[] = [];
  parts.push(
    `This dataset has ${p.rows.toLocaleString()} rows across ${p.cols} columns`
  );
  const numeric = p.columns.filter((c) => c.kind === "numeric").length;
  const cats = p.columns.filter((c) => c.kind === "categorical").length;
  const dts = p.columns.filter((c) => c.kind === "datetime").length;
  const mix: string[] = [];
  if (numeric) mix.push(`${numeric} numeric`);
  if (cats) mix.push(`${cats} categorical`);
  if (dts) mix.push(`${dts} datetime`);
  if (mix.length) parts.push(` (${mix.join(", ")})`);
  parts.push(".");
  if (p.duplicate_rows && p.duplicate_rows > 0) {
    const pct = ((p.duplicate_rows / Math.max(1, p.rows)) * 100).toFixed(1);
    parts.push(` Found ${p.duplicate_rows.toLocaleString()} duplicate rows (${pct}%).`);
  } else {
    parts.push(" No duplicate rows detected.");
  }
  const worstMissing = [...p.columns]
    .filter((c) => (c.missing_pct ?? 0) > 0)
    .sort((a, b) => (b.missing_pct ?? 0) - (a.missing_pct ?? 0))
    .slice(0, 3);
  if (worstMissing.length === 0) {
    parts.push(" No missing values across any column.");
  } else {
    const summary = worstMissing
      .map((c) => `${c.name} (${(c.missing_pct ?? 0).toFixed(1)}%)`)
      .join(", ");
    parts.push(` Highest missingness: ${summary}.`);
  }
  if (p.memory_kb) {
    parts.push(` In-memory size ≈ ${p.memory_kb.toLocaleString()} KB.`);
  }
  return parts.join("");
}

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
  const [data, setData] = useState<AutoProfile | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setData(null);
    // One-shot endpoint: preview + profile + insights + suggestions in
    // a single request, with backend caching on the dataset row.
    api<AutoProfile>(`/api/datasets/${datasetId}/auto-profile?rows=20`, { method: "POST" })
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(errMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  const preview = data;
  const insights = data?.insights ?? null;
  const suggestions = data?.suggestions ?? null;
  const narrative = profileNarrative(data?.profile);

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

      {/* Professional profile paragraph */}
      {data?.profile && narrative && (
        <div className="border border-[var(--border)] rounded-lg p-3 bg-[var(--surface-alt)]">
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)] mb-1.5">
            Profile · ملف الداتا
          </div>
          <p className="text-[12px] leading-relaxed text-[var(--text)]">
            {narrative}
          </p>
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
