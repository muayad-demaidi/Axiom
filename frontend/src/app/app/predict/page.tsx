"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

type ForecastPoint = { period?: number; forecast?: number; lower?: number; upper?: number } & Record<string, number | string>;
type ForecastResponse = { column: string; forecast: ForecastPoint[] | number[] };

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw = (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
}

function GuidedForecast({ data }: { data: ForecastResponse }) {
  const points = (data.forecast || []) as Array<ForecastPoint | number>;
  const flat: number[] = points.map((p) =>
    typeof p === "number" ? p : Number((p.forecast ?? p.value ?? 0))
  );
  const total = flat.reduce((a, b) => a + b, 0);
  const avg = flat.length ? total / flat.length : 0;
  const peakIdx = flat.indexOf(Math.max(...flat));
  return (
    <div className="space-y-3">
      <div className="text-sm">
        Over the next <strong>{flat.length}</strong> period{flat.length === 1 ? "" : "s"} the forecast for
        <strong> {data.column}</strong> averages
        <strong> {avg.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
        {flat.length > 1 && (
          <> with a peak in period {peakIdx + 1} ({flat[peakIdx].toLocaleString(undefined, { maximumFractionDigits: 2 })}).</>
        )}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-left text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
            <th className="py-1">Period</th>
            <th className="py-1">Forecast</th>
          </tr>
        </thead>
        <tbody>
          {flat.map((v, i) => (
            <tr key={i} className="border-t border-dashed border-[var(--border)]">
              <td className="py-1.5 font-mono text-xs">{i + 1}</td>
              <td className="py-1.5">{v.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function PredictPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
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

  async function run(overridePeriods?: number) {
    const id = getActiveDatasetId();
    if (!id || !column) return;
    setBusy(true); setError(null);
    try {
      const r = await api<ForecastResponse>("/api/predict", {
        method: "POST",
        json: { dataset_id: id, column, periods: overridePeriods ?? periods },
      });
      setForecast(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  const expertControls = (
    <div className="space-y-3">
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
      <button className="btn btn-primary" onClick={() => run()} disabled={busy || !column}>
        {busy ? "Forecasting…" : "Run forecast"}
      </button>
    </div>
  );

  return (
    <div className="max-w-3xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Analysis · Predict"
        guidedTitle="See what's coming next"
        expertTitle="Predictive analytics"
        guidedSubtitle="Pick a number to forecast and we'll show you the next few periods. Open the advanced view to tune the horizon."
        expertSubtitle="Short-horizon forecast on a numeric column via predictions.simple_forecast."
      />

      {mode === "guided" ? (
        <>
          <div className="card mt-6 space-y-3">
            <label className="block text-sm">
              What would you like to forecast?
              <select value={column} onChange={(e) => setColumn(e.target.value)}
                className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
                {columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <div className="flex flex-wrap gap-2 pt-2">
              <button className="btn btn-primary" onClick={() => run(3)} disabled={busy || !column}>
                {busy ? "Forecasting…" : "Forecast next 3 periods"}
              </button>
              <button className="btn btn-ghost" onClick={() => run(6)} disabled={busy || !column}>
                Next 6 periods
              </button>
              <button className="btn btn-ghost" onClick={() => run(12)} disabled={busy || !column}>
                Next 12 periods
              </button>
            </div>
          </div>
          <AdvancedExpander projectId={projectId} hint="Pick exact horizon and column">
            {expertControls}
          </AdvancedExpander>
        </>
      ) : (
        <div className="card mt-6">{expertControls}</div>
      )}

      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {forecast && (
        <div className="card mt-4">
          {mode === "guided" ? (
            <>
              <GuidedForecast data={forecast} />
              <TechnicalDetails projectId={projectId} label="View the model output">
                <pre className="text-[11px] overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(forecast, null, 2)}</pre>
              </TechnicalDetails>
            </>
          ) : (
            <pre className="text-xs overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(forecast, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}
