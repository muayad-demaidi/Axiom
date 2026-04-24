"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId } from "@/lib/projectContext";

type ForecastResponse = { column: string; forecast: Array<Record<string, number | string>> | number[] };

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw = (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
}

export default function PredictPage() {
  const router = useRouter();
  const [columns, setColumns] = useState<string[]>([]);
  const [column, setColumn] = useState("");
  const [periods, setPeriods] = useState(3);
  const [forecast, setForecast] = useState<ForecastResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setError("No active dataset — upload one first."); return; }
    api<AxiomDataset>(`/api/datasets/${id}`)
      .then((d) => {
        const cols = extractColumns(d);
        setColumns(cols);
        setColumn(cols[0] || "");
      })
      .catch((e: unknown) => setError(errMessage(e)));
  }, [router]);

  async function run() {
    const id = getActiveDatasetId();
    if (!id || !column) return;
    setBusy(true); setError(null);
    try {
      const r = await api<ForecastResponse>("/api/predict", {
        method: "POST",
        json: { dataset_id: id, column, periods },
      });
      setForecast(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl">
      <span className="eyebrow">Analysis · Predict</span>
      <h1 className="text-2xl font-bold mt-2">Predictive analytics</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Short-horizon forecast on a numeric column via <code>predictions.simple_forecast</code>.
      </p>
      <div className="card mt-6 space-y-3">
        <label className="block text-sm">
          Column
          <select value={column} onChange={(e) => setColumn(e.target.value)}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="block text-sm">
          Periods to forecast
          <input type="number" min={1} max={24} value={periods}
            onChange={(e) => setPeriods(Number(e.target.value))}
            className="block mt-1 w-32 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" />
        </label>
        <button className="btn btn-primary" onClick={run} disabled={busy || !column}>
          {busy ? "Forecasting…" : "Run forecast"}
        </button>
      </div>
      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {forecast && (
        <pre className="card mt-4 text-xs overflow-auto max-h-[50vh]">{JSON.stringify(forecast, null, 2)}</pre>
      )}
    </div>
  );
}
