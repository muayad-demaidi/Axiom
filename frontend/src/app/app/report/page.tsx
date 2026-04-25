"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId } from "@/lib/projectContext";

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

export default function ReportPage() {
  const router = useRouter();
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [sections, setSections] = useState<Record<SectionKey, boolean>>({
    include_cover: true,
    include_columns: true,
    include_numeric_summary: true,
    include_chart: true,
    include_ai_insights: true,
  });
  const [numericColumns, setNumericColumns] = useState<string[]>([]);
  const [chartColumn, setChartColumn] = useState<string>("");

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    setDatasetId(id);
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
        // Non-fatal: the chart selector just stays empty and the backend
        // falls back to the first numeric column.
        setNumericColumns([]);
      });
  }, [router]);

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
      const token = getToken();
      const res = await fetch("/api/report/pdf", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/pdf",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          dataset_id: datasetId,
          title: title.trim() || null,
          notes: notes.trim() || null,
          ...sections,
          chart_column: sections.include_chart ? (chartColumn || null) : null,
        }),
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
      a.download = `axiom-report-${datasetId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setStatus("Report downloaded.");
    } catch (e: unknown) {
      setError(errMessage(e));
      setStatus(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl">
      <span className="eyebrow">Insight · Report</span>
      <h1 className="text-2xl font-bold mt-2">Auto-generated reports</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Executive summary with key findings, recommendations, and methodological caveats.
        Wired through <code>/api/report/pdf</code>.
      </p>

      {!datasetId && (
        <div className="card mt-6 text-sm text-red-600">
          No active dataset — upload one first.
        </div>
      )}

      <div className="card mt-6 space-y-3">
        <div>
          <label className="block text-xs font-medium mb-1">Report title (optional)</label>
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
          <label className="block text-xs font-medium mb-1">Notes (optional)</label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Context for the reader…"
            rows={3}
            className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
            disabled={busy}
          />
        </div>

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
            {busy ? "Generating…" : "Generate report"}
          </button>
          {status && <span className="text-xs text-[var(--text-muted)]">{status}</span>}
        </div>
      </div>

      {error && <div className="card mt-4 text-sm text-red-600">{error}</div>}
    </div>
  );
}
