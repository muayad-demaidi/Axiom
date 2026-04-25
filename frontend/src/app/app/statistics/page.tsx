"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  MissingDatasetNotice,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

type StatsReport = Record<string, unknown> & {
  rows?: number;
  cols?: number;
  numeric_summary?: Record<string, Record<string, number>>;
  missing?: Record<string, number>;
};

function GuidedSummary({ report }: { report: StatsReport }) {
  const rows = typeof report.rows === "number" ? report.rows : null;
  const cols = typeof report.cols === "number" ? report.cols : null;
  const missing = report.missing && typeof report.missing === "object" ? report.missing : {};
  const missingPairs = Object.entries(missing)
    .filter(([, v]) => typeof v === "number" && (v as number) > 0)
    .sort((a, b) => (b[1] as number) - (a[1] as number))
    .slice(0, 5);
  const numericCols = report.numeric_summary
    ? Object.keys(report.numeric_summary).slice(0, 6)
    : [];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {rows != null && (
          <Tile label="Rows" value={rows.toLocaleString()} />
        )}
        {cols != null && (
          <Tile label="Columns" value={String(cols)} />
        )}
        {numericCols.length > 0 && (
          <Tile label="Numeric columns" value={String(numericCols.length)} />
        )}
      </div>
      {missingPairs.length > 0 ? (
        <div>
          <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-1.5">
            Columns with missing values
          </div>
          <ul className="text-sm space-y-1">
            {missingPairs.map(([col, n]) => (
              <li key={col} className="flex items-baseline justify-between border-b border-dashed border-[var(--border)] pb-1">
                <span className="font-medium truncate pr-2">{col}</span>
                <span className="text-xs text-[var(--text-muted)] font-mono">{(n as number).toLocaleString()} missing</span>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <div className="text-sm text-[var(--text-muted)]">No missing values to worry about.</div>
      )}
      {numericCols.length > 0 && (
        <div className="text-sm text-[var(--text-muted)]">
          Numeric columns ready for analysis: {numericCols.join(", ")}.
        </div>
      )}
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-[var(--border)] bg-[var(--surface-alt)]/50 p-3">
      <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
        {label}
      </div>
      <div className="mt-1 text-xl font-semibold tracking-tight">{value}</div>
    </div>
  );
}

export default function StatisticsPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const [report, setReport] = useState<StatsReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setHasDataset(false); return; }
    setHasDataset(true);
    setBusy(true);
    api<{ report: StatsReport }>("/api/statistics", { method: "POST", json: { dataset_id: id } })
      .then((r) => setReport(r.report))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Statistics failed"))
      .finally(() => setBusy(false));
  }, [router]);

  return (
    <div className="max-w-4xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Analysis · Statistics"
        guidedTitle="What's in your data?"
        expertTitle="Descriptive statistics"
        guidedSubtitle="A plain-language overview of size, shape and gaps. Open the technical view for the full report."
        expertSubtitle="Computed via data_analyzer.generate_summary_report against the active dataset."
      />
      {hasDataset === false && (
        <MissingDatasetNotice
          projectId={projectId}
          toolName="statistics"
          guidedHint="Upload a CSV or Excel file and we'll summarize what's in it."
        />
      )}
      {busy && <div className="card mt-6 text-sm text-[var(--text-muted)]">Computing…</div>}
      {error && <div className="card mt-6 text-sm text-red-600">{error}</div>}
      {report && (
        <div className="card mt-6">
          {mode === "guided" ? (
            <>
              <GuidedSummary report={report} />
              <TechnicalDetails projectId={projectId} label="View the full statistical report">
                <pre className="text-[11px] overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(report, null, 2)}</pre>
              </TechnicalDetails>
            </>
          ) : (
            <pre className="text-xs overflow-auto max-h-[60vh] whitespace-pre-wrap">{JSON.stringify(report, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}
