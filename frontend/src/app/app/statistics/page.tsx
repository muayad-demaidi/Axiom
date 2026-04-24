"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { getActiveDatasetId } from "@/lib/projectContext";

export default function StatisticsPage() {
  const router = useRouter();
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setError("No active dataset — upload one first."); return; }
    setBusy(true);
    api<{ report: Record<string, unknown> }>("/api/statistics", { method: "POST", json: { dataset_id: id } })
      .then((r) => setReport(r.report))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : "Statistics failed"))
      .finally(() => setBusy(false));
  }, [router]);

  return (
    <div className="max-w-4xl">
      <span className="eyebrow">Analysis · Statistics</span>
      <h1 className="text-2xl font-bold mt-2">Descriptive statistics</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Computed against the active dataset via <code>data_analyzer.generate_summary_report</code>.
      </p>
      {busy && <div className="card mt-6 text-sm text-[var(--text-muted)]">Computing…</div>}
      {error && <div className="card mt-6 text-sm text-red-600">{error}</div>}
      {report && (
        <pre className="card mt-6 text-xs overflow-auto max-h-[60vh]">{JSON.stringify(report, null, 2)}</pre>
      )}
    </div>
  );
}
