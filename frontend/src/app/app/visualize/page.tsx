"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart, Bar, LineChart, Line, ScatterChart, Scatter, PieChart, Pie, Cell,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
  ReferenceLine,
} from "recharts";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  GuidedActionCard,
  MissingDatasetNotice,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

type ChartKind = "bar" | "line" | "scatter" | "pie" | "histogram" | "box" | "heatmap";
type ExpertChartKind = "residuals" | "qq" | "acf" | "pacf";

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

type AggregatedXY = {
  chart: "bar" | "line";
  x: string;
  y: string;
  y_label?: string;
  aggregation?: string;
  format_kind?: string;
  points: XYPoint[];
  warnings?: string[];
  grand_total?: number | null;
};

type VisualizeResponse =
  | { chart: "histogram"; x: string; points: HistPoint[] }
  | { chart: "pie"; x: string; points: PiePoint[] }
  | AggregatedXY
  | { chart: "scatter"; x: string; y: string; points: ScatterPoint[] }
  | { chart: "box"; points: BoxPoint[] }
  | { chart: "heatmap"; columns: string[]; matrix: number[][] };

type AggregationKind = "default" | "sum" | "avg" | "count" | "count_distinct" | "min" | "max" | "median";

const AGG_LABELS: Record<AggregationKind, string> = {
  default: "Auto (field default)",
  sum: "Sum",
  avg: "Average",
  count: "Count",
  count_distinct: "Distinct count",
  min: "Min",
  max: "Max",
  median: "Median",
};

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

type ExpertResult = {
  chart: ExpertChartKind;
  summary: Record<string, unknown>;
  spec: { data?: Array<{ x?: number[]; y?: number[]; mode?: string; type?: string }> };
  values?: number[];
  ci_band?: number;
  column?: string;
  x_col?: string;
  y_col?: string;
  lags?: number;
};

function ExpertChartView({ result }: { result: ExpertResult }) {
  const traces = result.spec?.data ?? [];

  if (result.chart === "residuals") {
    const t = traces[0];
    const points = (t?.x ?? []).map((xv, i) => ({
      x: Number(xv), y: Number((t?.y ?? [])[i]),
    }));
    return (
      <ResponsiveContainer width="100%" height={320}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" dataKey="x" name={`Fitted (${result.x_col ?? "x"})`} />
          <YAxis type="number" dataKey="y" name="Residual" />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} />
          <ReferenceLine y={0} stroke="#9ca3af" strokeDasharray="4 4" />
          <Scatter data={points} fill={PALETTE[0]} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  if (result.chart === "qq") {
    const sample = traces[0];
    const ref = traces[1];
    const samplePoints = (sample?.x ?? []).map((xv, i) => ({
      x: Number(xv), y: Number((sample?.y ?? [])[i]),
    }));
    const refPoints = (ref?.x ?? []).map((xv, i) => ({
      x: Number(xv), y: Number((ref?.y ?? [])[i]),
    }));
    return (
      <ResponsiveContainer width="100%" height={320}>
        <ScatterChart>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis type="number" dataKey="x" name="Theoretical quantiles" />
          <YAxis type="number" dataKey="y" name="Sample quantiles" />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} />
          <Scatter name="sample" data={samplePoints} fill={PALETTE[0]} />
          <Scatter name="reference" data={refPoints} line fill="#9ca3af" shape={() => <></>} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }

  // acf / pacf
  const values = result.values ?? [];
  const ci = result.ci_band ?? 0;
  const points = values.map((v, i) => ({ lag: i, value: Number(v) }));
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={points}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="lag" />
        <YAxis />
        <Tooltip />
        <ReferenceLine y={ci} stroke="#9ca3af" strokeDasharray="3 3" />
        <ReferenceLine y={-ci} stroke="#9ca3af" strokeDasharray="3 3" />
        <Bar dataKey="value" fill={PALETTE[0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export default function VisualizePage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const [columns, setColumns] = useState<string[]>([]);
  const [chart, setChart] = useState<ChartKind>("bar");
  const [x, setX] = useState("");
  const [y, setY] = useState("");
  const [aggregation, setAggregation] = useState<AggregationKind>("default");
  const [data, setData] = useState<VisualizeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);
  // Expert-only diagnostic charts (Task #250).
  const [expertChart, setExpertChart] = useState<ExpertChartKind>("residuals");
  const [expertLags, setExpertLags] = useState<number>(20);
  const [expertResult, setExpertResult] = useState<{
    chart: ExpertChartKind;
    summary: Record<string, unknown>;
    spec: { data?: Array<{ x?: number[]; y?: number[]; mode?: string; type?: string }> };
    values?: number[];
    ci_band?: number;
    column?: string;
    x_col?: string;
    y_col?: string;
    lags?: number;
  } | null>(null);

  const xDisabled = NO_COLUMN_CHARTS.includes(chart);
  const yDisabled = SINGLE_COLUMN_CHARTS.includes(chart) || NO_COLUMN_CHARTS.includes(chart) || chart === "box";

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setHasDataset(false); return; }
    setHasDataset(true);
    api<AxiomDataset>(`/api/datasets/${id}`)
      .then((d) => {
        const cols = extractColumns(d);
        setColumns(cols);
        setX(cols[0] || "");
        setY(cols[1] || cols[0] || "");
      })
      .catch((e: unknown) => setError(errMessage(e)));
  }, [router]);

  async function run(override?: { chart: ChartKind; x?: string | null; y?: string | null }) {
    const id = getActiveDatasetId();
    if (!id) return;
    const useChart = override?.chart ?? chart;
    const useX = override ? (override.x ?? null) : (xDisabled ? null : x || null);
    const useY = override ? (override.y ?? null) : (yDisabled ? null : y || null);
    if (!override && !xDisabled && !x) return;
    setBusy(true); setError(null); setData(null);
    if (override) setChart(override.chart);
    try {
      const body: Record<string, unknown> = { dataset_id: id, chart: useChart, x: useX, y: useY };
      if ((useChart === "bar" || useChart === "line") && aggregation !== "default") {
        body.aggregation = aggregation;
      }
      const r = await api<VisualizeResponse>("/api/visualize", {
        method: "POST",
        json: body,
      });
      setData(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  async function runExpertChart() {
    const id = getActiveDatasetId();
    if (!id) return;
    setBusy(true); setError(null); setExpertResult(null);
    try {
      const body: Record<string, unknown> = {
        dataset_id: id,
        chart: expertChart,
        x_col: x || null,
        y_col: y || null,
      };
      if (expertChart === "acf" || expertChart === "pacf") {
        body.lags = expertLags;
      }
      const r = await api<{
        chart: ExpertChartKind;
        summary: Record<string, unknown>;
        spec: { data?: Array<{ x?: number[]; y?: number[]; mode?: string; type?: string }> };
        values?: number[];
        ci_band?: number;
        column?: string;
        x_col?: string;
        y_col?: string;
        lags?: number;
      }>("/api/visualize/expert-charts", { method: "POST", json: body });
      setExpertResult(r);
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
            <Line type="monotone" dataKey="y" stroke={PALETTE[0]} dot={false} name={data.y_label || data.y} />
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
          <Bar
            dataKey="y"
            fill={PALETTE[0]}
            name={"y_label" in data && data.y_label ? data.y_label : data.y}
          />
        </BarChart>
      </ResponsiveContainer>
    );
  }, [data]);

  // Aggregation warnings + resolved label live underneath the chart so
  // it's obvious when the API quietly used SUM (not MEAN) or warned
  // about averaging a percentage column.
  const aggMeta = useMemo(() => {
    if (!data || (data.chart !== "bar" && data.chart !== "line")) return null;
    return {
      label: data.y_label,
      aggregation: data.aggregation,
      warnings: data.warnings || [],
      grand_total: data.grand_total ?? null,
      format: data.format_kind,
    };
  }, [data]);

  const xHelp = chart === "box"
    ? "Pick a numeric column, or leave to summarize all numeric columns"
    : chart === "heatmap"
      ? "Heatmap uses every numeric column"
      : "";

  const expertControls = (
    <>
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
      {(chart === "bar" || chart === "line") && (
        <div className="card mt-3">
          <label className="text-sm block">
            Aggregation for Y
            <select
              value={aggregation}
              onChange={(e) => setAggregation(e.target.value as AggregationKind)}
              className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
            >
              {(Object.keys(AGG_LABELS) as AggregationKind[]).map((k) => (
                <option key={k} value={k}>{AGG_LABELS[k]}</option>
              ))}
            </select>
          </label>
          <p className="text-xs text-[var(--text-muted)] mt-2">
            &quot;Auto&quot; uses the field&apos;s role-aware default — Sum for additive measures
            like revenue, Average for percentages (with a warning), Count for non-numeric.
            The pivot, dashboard and chat assistant all share this engine.
          </p>
        </div>
      )}
      <div className="mt-4">
        <button className="btn btn-primary" onClick={() => run()} disabled={busy || (!xDisabled && !x)}>
          {busy ? "Rendering…" : "Render chart"}
        </button>
      </div>
      {mode === "expert" && (
        <div className="card mt-6 space-y-3">
          <div className="text-sm font-medium">Expert diagnostics</div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <label className="text-sm">
              Diagnostic
              <select
                value={expertChart}
                onChange={(e) => setExpertChart(e.target.value as ExpertChartKind)}
                className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
              >
                <option value="residuals">Residuals vs fitted</option>
                <option value="qq">Q–Q plot (normality)</option>
                <option value="acf">Autocorrelation (ACF)</option>
                <option value="pacf">Partial autocorrelation (PACF)</option>
              </select>
            </label>
            {(expertChart === "acf" || expertChart === "pacf") && (
              <label className="text-sm">
                Lags
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={expertLags}
                  onChange={(e) => setExpertLags(Math.max(1, Number(e.target.value) || 1))}
                  className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
                />
              </label>
            )}
          </div>
          <p className="text-xs text-[var(--text-muted)]">
            Residuals & Q–Q use the X / Y selectors above. ACF / PACF use the X column
            (a numeric, time-ordered series).
          </p>
          <button
            className="btn btn-primary"
            onClick={runExpertChart}
            disabled={busy || !x}
          >
            {busy ? "Computing…" : "Run diagnostic"}
          </button>
          {expertResult && (
            <div className="mt-3 space-y-2">
              <ExpertChartView result={expertResult} />
              <div className="text-xs text-[var(--text-muted)]">
                {expertResult.chart} summary
              </div>
              <pre className="text-[11px] overflow-auto max-h-[30vh] whitespace-pre-wrap p-2 rounded bg-[var(--surface)] border border-[var(--border)]">
                {JSON.stringify(expertResult.summary, null, 2)}
              </pre>
            </div>
          )}
        </div>
      )}
    </>
  );

  return (
    <div className="max-w-4xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Analysis · Visualize"
        guidedTitle="Show me a chart"
        expertTitle="Visualizations"
        guidedSubtitle="Pick what you want to see. Open the advanced view to choose chart type, x and y columns yourself."
        expertSubtitle="Bar, line, scatter, pie, histogram, box plot and correlation heatmap — aggregated server-side from the active dataset."
      />

      {hasDataset === false ? (
        <MissingDatasetNotice
          projectId={projectId}
          toolName="charts"
          guidedHint="Upload a CSV or Excel file and we'll let you build a chart from it."
        />
      ) : mode === "guided" ? (
        <>
          <div className="card mt-6">
            <label className="text-sm block">
              Column to visualize
              <select value={x} onChange={(e) => setX(e.target.value)}
                className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
                {columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <GuidedActionCard
              title="Show distribution"
              description="A histogram of how this column is spread out — good for spotting skew or outliers."
              cta="Show histogram"
              busy={busy}
              disabled={!x}
              onAction={() => run({ chart: "histogram", x })}
            />
            <GuidedActionCard
              title="Show share of total"
              description="A pie chart of the categories in this column."
              cta="Show pie chart"
              busy={busy}
              disabled={!x}
              onAction={() => run({ chart: "pie", x })}
            />
            <GuidedActionCard
              title="Find what moves together"
              description="A correlation heatmap across every numeric column. No column needed."
              cta="Show heatmap"
              busy={busy}
              onAction={() => run({ chart: "heatmap", x: null, y: null })}
            />
            <GuidedActionCard
              title="Spot outliers"
              description="A box plot summary of every numeric column at once."
              cta="Show box plot"
              busy={busy}
              onAction={() => run({ chart: "box", x: null, y: null })}
            />
          </div>
          <AdvancedExpander projectId={projectId} hint="Choose any chart type and pick x / y manually">
            {expertControls}
          </AdvancedExpander>
        </>
      ) : (
        expertControls
      )}

      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {rendered && (
        <div className="card mt-6">
          {rendered}
          {aggMeta && (
            <div className="mt-3 flex items-center gap-3 flex-wrap text-xs">
              {aggMeta.label && (
                <span className="font-mono px-2 py-1 rounded bg-[var(--surface)] text-[var(--text-muted)]">
                  Y: <span className="text-[var(--text)]">{aggMeta.label}</span>
                </span>
              )}
              {aggMeta.aggregation && (
                <span className="font-mono px-2 py-1 rounded bg-[var(--surface)] text-[var(--text-muted)]">
                  agg: <span className="text-[var(--text)]">{aggMeta.aggregation}</span>
                </span>
              )}
              {aggMeta.grand_total !== null && aggMeta.grand_total !== undefined && (
                <span className="font-mono px-2 py-1 rounded bg-[var(--surface)] text-[var(--text-muted)]">
                  total: <span className="text-[var(--text)]">{Number(aggMeta.grand_total).toLocaleString(undefined, { maximumFractionDigits: 2 })}</span>
                </span>
              )}
            </div>
          )}
          {aggMeta && aggMeta.warnings.length > 0 && (
            <ul className="mt-2 text-xs text-amber-600 list-disc list-inside space-y-0.5">
              {aggMeta.warnings.map((w, i) => <li key={i}>{w}</li>)}
            </ul>
          )}
          {mode === "guided" && data && (
            <TechnicalDetails projectId={projectId} label="View the underlying numbers">
              <pre className="text-[11px] overflow-auto max-h-[40vh] whitespace-pre-wrap">{JSON.stringify(data, null, 2)}</pre>
            </TechnicalDetails>
          )}
        </div>
      )}
    </div>
  );
}
