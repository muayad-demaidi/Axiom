"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "@/lib/api";
import { getActiveDatasetId } from "@/lib/projectContext";

export default function ReportPage() {
  const router = useRouter();
  const [datasetId, setDatasetId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    setDatasetId(getActiveDatasetId());
  }, [router]);

  async function generate() {
    if (!datasetId) {
      setError("No active dataset — upload one first.");
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
      setError(e instanceof Error ? e.message : "Report failed");
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
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={generate}
            disabled={busy || !datasetId}
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
