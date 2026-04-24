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

type ChartKind = "bar" | "line" | "scatter" | "pie" | "histogram";

type XYPoint = { x: number | string; y: number | string };
type PiePoint = { name: string; value: number };
type HistPoint = { bin: string; count: number };

type VisualizeResponse =
  | { chart: "histogram"; x: string; points: HistPoint[] }
  | { chart: "pie"; x: string; points: PiePoint[] }
  | { chart: "bar" | "line" | "scatter"; x: string; y: string; points: XYPoint[] };

const PALETTE = ["#2563eb", "#60a5fa", "#3b82f6", "#1d4ed8", "#93c5fd", "#0ea5e9", "#1e40af"];

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw = (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
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
    if (!id || !x) return;
    setBusy(true); setError(null);
    try {
      const r = await api<VisualizeResponse>("/api/visualize", {
        method: "POST",
        json: { dataset_id: id, chart, x, y },
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
    return (
      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={data.points}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="x" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="y" fill={PALETTE[0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }, [data]);

  return (
    <div className="max-w-4xl">
      <span className="eyebrow">Analysis · Visualize</span>
      <h1 className="text-2xl font-bold mt-2">Visualizations</h1>
      <p className="text-[var(--text-muted)] mt-2">
        Bar, line, scatter, pie, and histogram — rendered with Recharts against the active dataset.
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
          </select>
        </label>
        <label className="text-sm">
          X column
          <select value={x} onChange={(e) => setX(e.target.value)}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
        <label className="text-sm">
          Y column {chart === "pie" || chart === "histogram" ? "(unused)" : ""}
          <select value={y} onChange={(e) => setY(e.target.value)}
            disabled={chart === "pie" || chart === "histogram"}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm disabled:opacity-50">
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      </div>
      <div className="mt-4">
        <button className="btn btn-primary" onClick={run} disabled={busy || !x}>
          {busy ? "Rendering…" : "Render chart"}
        </button>
      </div>
      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {rendered && <div className="card mt-6">{rendered}</div>}
    </div>
  );
}
