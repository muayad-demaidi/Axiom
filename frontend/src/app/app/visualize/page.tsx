"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart, Bar, LineChart, Line, ScatterChart, Scatter, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId } from "@/lib/projectContext";

type ChartKind = "bar" | "line" | "scatter" | "pie" | "histogram" | "box" | "heatmap";

type XYPoint = { x: number | string; y: number };
type ScatterPoint = { x: number; y: number };
type PiePoint = { name: string; value: number };
type HistPoint = { bin: string; count: number };
type BoxPoint = {
  column: string;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
  count: number;
};

type VisualizeResponse =
  | { chart: "histogram"; x: string; points: HistPoint[] }
  | { chart: "pie"; x: string; points: PiePoint[] }
  | { chart: "bar"; x: string; y: string; points: XYPoint[] }
  | { chart: "line"; x: string; y: string; points: XYPoint[] }
  | { chart: "scatter"; x: string; y: string; points: ScatterPoint[] }
  | { chart: "box"; points: BoxPoint[] }
  | { chart: "heatmap"; columns: string[]; matrix: number[][] };

const PALETTE = ["#2563eb", "#60a5fa", "#3b82f6", "#1d4ed8", "#93c5fd", "#0ea5e9", "#1e40af"];
const SINGLE_COLUMN_CHARTS: ChartKind[] = ["pie", "histogram"];
const NO_COLUMN_CHARTS: ChartKind[] = ["heatmap"];

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw = (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
}

function corrColor(v: number): string {
  // Diverging blue / white / red around zero.
  const t = Math.max(-1, Math.min(1, v));
  if (t >= 0) {
    const r = Math.round(255 - t * (255 - 37));
    const g = Math.round(255 - t * (255 - 99));
    const b = Math.round(255 - t * (255 - 235));
    return `rgb(${r},${g},${b})`;
  }
  const m = -t;
  const r = Math.round(255 - m * (255 - 220));
  const g = Math.round(255 - m * (255 - 38));
  const b = Math.round(255 - m * (255 - 38));
  return `rgb(${r},${g},${b})`;
}

function BoxPlot({ points }: { points: BoxPoint[] }) {
  const lo = Math.min(...points.map((p) => p.min));
  const hi = Math.max(...points.map((p) => p.max));
  const span = hi - lo || 1;
  const pct = (v: number) => `${((v - lo) / span) * 100}%`;
  return (
    <div className="space-y-4 py-2">
      {points.map((p) => (
        <div key={p.column}>
          <div className="flex items-baseline justify-between text-sm">
            <span className="font-medium">{p.column}</span>
            <span className="text-xs text-[var(--text-muted)]">
              n={p.count} · median {p.median.toLocaleString(undefined, { maximumFractionDigits: 4 })}
            </span>
          </div>
          <div className="relative h-8 mt-1 rounded bg-[var(--surface)] border border-[var(--border)]">
            <div
              className="absolute top-1/2 h-px bg-[var(--text-muted)]"
              style={{ left: pct(p.min), right: `calc(100% - ${pct(p.max)})` }}
            />
            <div
              className="absolute top-1 bottom-1 rounded"
              style={{
                left: pct(p.q1),
                right: `calc(100% - ${pct(p.q3)})`,
                background: PALETTE[1],
                border: `1px solid ${PALETTE[3]}`,
              }}
            />
            <div
              className="absolute top-1 bottom-1 w-0.5 bg-[var(--text)]"
              style={{ left: pct(p.median) }}
            />
            {(["min", "max"] as const).map((k) => (
              <div
                key={k}
                className="absolute top-2 bottom-2 w-px bg-[var(--text-muted)]"
                style={{ left: pct(p[k]) }}
              />
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-[var(--text-muted)]">
            <span>{lo.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
            <span>{hi.toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function Heatmap({ columns, matrix }: { columns: string[]; matrix: number[][] }) {
  return (
    <div className="overflow-auto">
      <table className="text-xs border-separate" style={{ borderSpacing: 2 }}>
        <thead>
          <tr>
            <th />
            {columns.map((c) => (
              <th key={c} className="px-2 py-1 text-left text-[var(--text-muted)] font-normal">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {matrix.map((row, i) => (
            <tr key={columns[i]}>
              <th className="px-2 py-1 text-right text-[var(--text-muted)] font-normal">
                {columns[i]}
              </th>
              {row.map((v, j) => (
                <td
                  key={j}
                  title={`${columns[i]} × ${columns[j]} = ${v.toFixed(3)}`}
                  className="text-center align-middle px-2 py-1 rounded"
                  style={{
                    background: corrColor(v),
                    color: Math.abs(v) > 0.55 ? "#fff" : "#111",
                    minWidth: 56,
                  }}
                >
                  {v.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function VisualizePage() {
  const router = useRouter();
  const [columns, setColumns] = useState<string[]>([]);
  const [chart, setChart] = useState<ChartKind>("bar");
  const [x, setX] = useState("");
  const [y, setY] = useState("");
  const [data, setData] = useState<VisualizeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const xDisabled = NO_COLUMN_CHARTS.includes(chart);
  const yDisabled = SINGLE_COLUMN_CHARTS.includes(chart) || NO_COLUMN_CHARTS.includes(chart) || chart === "box";

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setError("No active dataset — upload one first."); return; }
    api<AxiomDataset>(`/api/datasets/${id}`)
      .then((d) => {
        const cols = extractColumns(d);
        setColumns(cols);
        setX(cols[0] || "");
        setY(cols[1] || cols[0] || "");
      })
      .catch((e: unknown) => setError(errMessage(e)));
  }, [router]);

  async function run() {
    const id = getActiveDatasetId();
    if (!id) return;
    if (!xDisabled && !x) return;
    setBusy(true); setError(null); setData(null);
    try {
      const r = await api<VisualizeResponse>("/api/visualize", {
        method: "POST",
        json: {
          dataset_id: id,
          chart,
          x: xDisabled ? null : x || null,
          y: yDisabled ? null : y || null,
        },
      });
      setData(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  const rendered = useMemo(() => {
    if (!data) return null;
    if (data.chart === "pie") {
      return (
        <ResponsiveContainer width="100%" height={360}>
          <PieChart>
            <Pie data={data.points} dataKey="value" nameKey="name" outerRadius={120} label>
              {data.points.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      );
    }
    if (data.chart === "histogram") {
      return (
        <ResponsiveContainer width="100%" height={360}>
          <BarChart data={data.points}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="bin" />
            <YAxis />
            <Tooltip />
            <Bar dataKey="count" fill={PALETTE[0]} />
          </BarChart>
        </ResponsiveContainer>
      );
    }
    if (data.chart === "scatter") {
      return (
        <ResponsiveContainer width="100%" height={360}>
          <ScatterChart>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" dataKey="x" name={data.x} />
            <YAxis type="number" dataKey="y" name={data.y} />
            <Tooltip cursor={{ strokeDasharray: "3 3" }} />
            <Scatter data={data.points} fill={PALETTE[0]} />
          </ScatterChart>
        </ResponsiveContainer>
      );
    }
    if (data.chart === "line") {
      return (
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={data.points}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="x" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="y" stroke={PALETTE[0]} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      );
    }
    if (data.chart === "box") {
      return <BoxPlot points={data.points} />;
    }
    if (data.chart === "heatmap") {
      return <Heatmap columns={data.columns} matrix={data.matrix} />;
    }
    return (
      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={data.points}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="x" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="y" fill={PALETTE[0]} name={data.y} />
        </BarChart>
      </ResponsiveContainer>
    );
  }, [data]);

  const xHelp = chart === "box"
    ? "Pick a numeric column, or leave to summarize all numeric columns"
    : chart === "heatmap"
      ? "Heatmap uses every numeric column"
      : "";

  return (
    <div className="max-w-4xl">
      <span className="eyebrow">Analysis · Visualize</span>
      <h1 className="text-2xl font-bold mt-2">Visualizations</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Bar, line, scatter, pie, histogram, box plot, and correlation heatmap — aggregated server-side
        from the active dataset.
      </p>
      <div className="card mt-6 grid grid-cols-1 md:grid-cols-3 gap-3">
        <label className="text-sm">
          Chart
          <select value={chart} onChange={(e) => setChart(e.target.value as ChartKind)}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
            <option value="bar">Bar</option>
            <option value="line">Line</option>
            <option value="scatter">Scatter</option>
            <option value="pie">Pie</option>
            <option value="histogram">Histogram</option>
            <option value="box">Box plot</option>
            <option value="heatmap">Correlation heatmap</option>
          </select>
        </label>
        <label className="text-sm">
          X column {xDisabled ? "(unused)" : ""}
          <select value={x} onChange={(e) => setX(e.target.value)} disabled={xDisabled}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm disabled:opacity-50">
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="text-sm">
          Y column {yDisabled ? "(unused)" : ""}
          <select value={y} onChange={(e) => setY(e.target.value)} disabled={yDisabled}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm disabled:opacity-50">
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>
      {xHelp && <p className="text-xs text-[var(--text-muted)] mt-2">{xHelp}</p>}
      <div className="mt-4">
        <button className="btn btn-primary" onClick={run} disabled={busy || (!xDisabled && !x)}>
          {busy ? "Rendering…" : "Render chart"}
        </button>
      </div>
      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {rendered && <div className="card mt-6">{rendered}</div>}
    </div>
  );
}
