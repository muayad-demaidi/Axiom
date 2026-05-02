"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  MissingDatasetNotice,
  ModeAwareHeading,
} from "@/components/product/ModeAware";

type RecentReport = {
  id: number;
  dataset_id: number | null;
  project_id: number | null;
  title: string | null;
  notes: string | null;
  dataset_label: string | null;
  created_at: string | null;
};

type SectionKey =
  | "include_cover"
  | "include_columns"
  | "include_numeric_summary"
  | "include_chart"
  | "include_ai_insights";

const SECTIONS: { key: SectionKey; label: string; hint: string }[] = [
  { key: "include_cover", label: "Cover page", hint: "Title, dataset name, row/column count, notes." },
  { key: "include_columns", label: "Columns table", hint: "Per-column dtype, non-null and missing counts." },
  { key: "include_numeric_summary", label: "Numeric summary", hint: "Describe() table for numeric columns." },
  { key: "include_chart", label: "Distribution chart", hint: "Histogram for one numeric column." },
  { key: "include_ai_insights", label: "AI insights", hint: "Generated narrative write-up." },
];

const NUMERIC_DTYPE_RE = /^(u?int\d*|float\d*|number|decimal|long|short)$/i;
function isNumericDtype(dtype: string): boolean {
  const d = (dtype || "").trim();
  return NUMERIC_DTYPE_RE.test(d) || d.toLowerCase().includes("int") || d.toLowerCase().includes("float");
}

const GUIDED_DEFAULTS: Record<SectionKey, boolean> = {
  include_cover: true,
  include_columns: false,
  include_numeric_summary: false,
  include_chart: true,
  include_ai_insights: true,
};

const EXPERT_DEFAULTS: Record<SectionKey, boolean> = {
  include_cover: true,
  include_columns: true,
  include_numeric_summary: true,
  include_chart: true,
  include_ai_insights: true,
};

export default function ReportPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const [activeProjectId, setActiveProjectIdState] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [recent, setRecent] = useState<RecentReport[]>([]);
  const [recentLoading, setRecentLoading] = useState(false);
  const [recentError, setRecentError] = useState<string | null>(null);
  const [regeneratingId, setRegeneratingId] = useState<number | null>(null);

  // Default the Guided form to a narrative-first slice (cover + chart +
  // AI insights). The Expert form keeps the full toggle grid. The
  // user is free to override either default via the AdvancedExpander.
  const [sections, setSections] = useState<Record<SectionKey, boolean>>(
    mode === "guided" ? GUIDED_DEFAULTS : EXPERT_DEFAULTS,
  );
  const [numericColumns, setNumericColumns] = useState<string[]>([]);
  const [chartColumn, setChartColumn] = useState<string>("");

  // When the mode flips at runtime (project mode override toggled
  // elsewhere), nudge the section defaults to the new shape *only* if
  // the user hasn't customised them yet. Comparing to both defaults
  // detects the "untouched" state regardless of which mode they came in.
  useEffect(() => {
    setSections((prev) => {
      const matchesGuided = (Object.keys(GUIDED_DEFAULTS) as SectionKey[])
        .every((k) => prev[k] === GUIDED_DEFAULTS[k]);
      const matchesExpert = (Object.keys(EXPERT_DEFAULTS) as SectionKey[])
        .every((k) => prev[k] === EXPERT_DEFAULTS[k]);
      if (!matchesGuided && !matchesExpert) return prev;
      return mode === "guided" ? GUIDED_DEFAULTS : EXPERT_DEFAULTS;
    });
  }, [mode]);

  const fetchRecent = useCallback(async (pid: number | null) => {
    const token = getToken();
    if (!token) return;
    setRecentLoading(true);
    setRecentError(null);
    try {
      const qs = pid != null ? `?project_id=${pid}` : "";
      const res = await fetch(`/api/reports/recent${qs}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`Failed to load recent reports (${res.status})`);
      const j = (await res.json()) as { reports?: RecentReport[] };
      setRecent(Array.isArray(j.reports) ? j.reports : []);
    } catch (e: unknown) {
      setRecentError(e instanceof Error ? e.message : "Failed to load recent reports");
    } finally {
      setRecentLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    const pid = getActiveProjectId();
    setDatasetId(id);
    setActiveProjectIdState(pid);
    fetchRecent(pid);
    if (!id) return;
    api<AxiomDataset>(`/api/datasets/${id}`)
      .then((d) => {
        const raw = (d.summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
        const numeric = raw
          .map((c) => (typeof c === "string" ? { name: c, dtype: "" } : c))
          .filter((c) => !c.dtype || isNumericDtype(c.dtype))
          .map((c) => c.name);
        setNumericColumns(numeric);
      })
      .catch(() => {
        setNumericColumns([]);
      });
  }, [router, fetchRecent]);

  async function downloadPdf(opts: {
    datasetId: number;
    title: string | null;
    notes: string | null;
    filenameId: number;
    sections?: Record<SectionKey, boolean>;
    chartColumn?: string | null;
  }): Promise<void> {
    const token = getToken();
    const body: Record<string, unknown> = {
      dataset_id: opts.datasetId,
      title: opts.title,
      notes: opts.notes,
    };
    if (opts.sections) {
      Object.assign(body, opts.sections);
      body.chart_column = opts.sections.include_chart ? (opts.chartColumn || null) : null;
    }
    const res = await fetch("/api/report/pdf", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/pdf",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      let detail = text;
      try {
        const j = JSON.parse(text) as { detail?: string };
        if (j?.detail) detail = j.detail;
      } catch { /* keep raw text */ }
      throw new Error(detail || `Report failed (${res.status})`);
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `axiom-report-${opts.filenameId}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  function toggleSection(key: SectionKey) {
    setSections((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  const anySelected = Object.values(sections).some(Boolean);

  async function generate() {
    if (!datasetId) {
      setError("No active dataset — upload one first.");
      return;
    }
    if (!anySelected) {
      setError("Pick at least one section to include in the report.");
      return;
    }
    setBusy(true); setError(null); setStatus("Building report…");
    try {
      await downloadPdf({
        datasetId,
        title: title.trim() || null,
        notes: notes.trim() || null,
        filenameId: datasetId,
        sections,
        chartColumn,
      });
      setStatus("Report downloaded.");
      fetchRecent(activeProjectId);
    } catch (e: unknown) {
      setError(errMessage(e));
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  async function regenerate(r: RecentReport) {
    if (!r.dataset_id) {
      setRecentError("This report's dataset is no longer available.");
      return;
    }
    setRegeneratingId(r.id);
    setRecentError(null);
    try {
      await downloadPdf({
        datasetId: r.dataset_id,
        title: r.title,
        notes: r.notes,
        filenameId: r.dataset_id,
      });
    } catch (e: unknown) {
      setRecentError(e instanceof Error ? e.message : "Re-download failed");
    } finally {
      setRegeneratingId(null);
    }
  }

  const sectionPicker = (
    <div>
      <div className="text-xs font-medium mb-2">Sections to include</div>
      <div className="space-y-2">
        {SECTIONS.map((s) => (
          <label key={s.key} className="flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={sections[s.key]}
              onChange={() => toggleSection(s.key)}
              disabled={busy}
              className="mt-0.5"
            />
            <span>
              <span className="font-medium">{s.label}</span>
              <span className="text-[var(--text-muted)]"> — {s.hint}</span>
            </span>
          </label>
        ))}
      </div>
    </div>
  );

  return (
    <div className="max-w-3xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Insight · Report"
        guidedTitle="Get a written summary of your data"
        expertTitle="Auto-generated reports"
        guidedSubtitle="A narrative summary with the headline chart, written so anyone on the team can read it."
        expertSubtitle="Executive summary with key findings, recommendations, and methodological caveats. Wired through /api/report/pdf."
      />

      {!datasetId ? (
        <MissingDatasetNotice
          projectId={projectId}
          toolName="reports"
          guidedHint="Upload a CSV or Excel file and we'll write you a one-page summary."
        />
      ) : (
        <>
          <div className="card mt-6 space-y-3">
            <div>
              <label className="block text-xs font-medium mb-1">
                {mode === "guided" ? "Give your report a title (optional)" : "Report title (optional)"}
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="AXIOM Dataset Report"
                className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
                disabled={busy}
              />
            </div>
            <div>
              <label className="block text-xs font-medium mb-1">
                {mode === "guided" ? "Anything we should mention up top? (optional)" : "Notes (optional)"}
              </label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder={mode === "guided"
                  ? "e.g. This data covers Q3 sales for the EMEA region…"
                  : "Context for the reader…"}
                rows={3}
                className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
                disabled={busy}
              />
            </div>

            {mode === "guided" ? (
              <>
                <div className="rounded-md border border-dashed border-[var(--border)] bg-[var(--surface-alt)]/40 p-3 text-xs text-[var(--text-muted)] space-y-1">
                  <div className="font-medium text-[var(--text)]">What you&apos;ll get</div>
                  <ul className="list-disc list-inside space-y-0.5">
                    <li>Cover page with the dataset name and your notes.</li>
                    <li>A narrative write-up of the key findings.</li>
                    <li>One headline chart of the most interesting numeric column.</li>
                  </ul>
                  <div className="text-[10px] mt-1">
                    Open Advanced if you also want the raw column tables and numeric summary.
                  </div>
                </div>
                <AdvancedExpander
                  projectId={projectId}
                  hint="Pick exactly which sections to include"
                >
                  {sectionPicker}
                </AdvancedExpander>
              </>
            ) : (
              sectionPicker
            )}

            {sections.include_chart && (
              <div>
                <label className="block text-xs font-medium mb-1">Chart column (numeric)</label>
                <select
                  value={chartColumn}
                  onChange={(e) => setChartColumn(e.target.value)}
                  disabled={busy || numericColumns.length === 0}
                  className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
                >
                  <option value="">
                    {numericColumns.length === 0 ? "No numeric columns detected" : "First numeric column (default)"}
                  </option>
                  {numericColumns.map((c) => (
                    <option key={c} value={c}>{c}</option>
                  ))}
                </select>
              </div>
            )}

            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={generate}
                disabled={busy || !datasetId || !anySelected}
                className="btn btn-primary text-sm"
              >
                {busy
                  ? "Generating…"
                  : mode === "guided" ? "Write my report" : "Generate report"}
              </button>
              {status && <span className="text-xs text-[var(--text-muted)]">{status}</span>}
            </div>
          </div>

          {error && <div className="card mt-4 text-sm text-red-600">{error}</div>}
        </>
      )}

      <div className="mt-8">
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold">Recent reports</h2>
          <button
            type="button"
            onClick={() => fetchRecent(activeProjectId)}
            className="text-xs text-[var(--text-muted)] hover:underline"
            disabled={recentLoading}
          >
            {recentLoading ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        <p className="text-xs text-[var(--text-muted)] mb-3">
          {activeProjectId
            ? "Reports you've generated for the active project."
            : "Reports you've generated recently."}
        </p>

        {recentError && (
          <div className="card text-sm text-red-600">{recentError}</div>
        )}

        {!recentError && recent.length === 0 && !recentLoading && (
          <div className="card text-sm text-[var(--text-muted)]">
            No reports yet. Generate one above and it will show up here.
          </div>
        )}

        {recent.length > 0 && (
          <div className="card divide-y divide-[var(--border)] p-0">
            {recent.map((r) => {
              const created = r.created_at
                ? new Date(r.created_at).toLocaleString()
                : "—";
              const label = r.title?.trim() || "AXIOM Dataset Report";
              return (
                <div
                  key={r.id}
                  className="flex items-center justify-between gap-3 px-4 py-3"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-medium truncate">{label}</div>
                    <div className="text-xs text-[var(--text-muted)] truncate">
                      {r.dataset_label || `Dataset #${r.dataset_id ?? "?"}`}
                      {" · "}
                      {created}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => regenerate(r)}
                    disabled={regeneratingId === r.id || !r.dataset_id}
                    className="btn btn-ghost text-xs whitespace-nowrap"
                    title={
                      r.dataset_id
                        ? "Regenerate and download this report"
                        : "Original dataset is no longer available"
                    }
                  >
                    {regeneratingId === r.id ? "Preparing…" : "Download"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
