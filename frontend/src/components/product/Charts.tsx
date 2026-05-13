"use client";
/**
 * Recharts-based renderer for chart artifact payloads emitted by the
 * backend `make_chart` tool. The shapes here mirror what
 * `_compute_chart_payload` in `backend/chat.py` produces: histogram /
 * bar / line / scatter / pie / box / heatmap. Heatmap and box use a
 * minimal SVG / CSS-grid renderer because Recharts ships neither out of
 * the box.
 */
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

const PALETTE = [
  "#2563eb", "#60a5fa", "#1d4ed8", "#a5b4fc", "#7c3aed",
  "#0ea5e9", "#22d3ee", "#06b6d4", "#3b82f6", "#818cf8",
];

export type ChartPayload = {
  chart: string;
  title?: string;
  x?: string;
  y?: string;
  points?: Array<Record<string, unknown>>;
  matrix?: number[][];
  columns?: string[];
};

export function ChartRenderer({ payload, height = 280 }: { payload: ChartPayload; height?: number }) {
  const k = (payload.chart || "").toLowerCase();
  if (k === "histogram") {
    const data = (payload.points ?? []).map((p) => ({ bin: String(p.bin ?? ""), count: Number(p.count ?? 0) }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ left: 4, right: 8, top: 8, bottom: 28 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="bin" interval="preserveStartEnd" tick={{ fontSize: 10 }} angle={-30} dy={10} height={48} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Bar dataKey="count" fill={PALETTE[0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }
  if (k === "bar") {
    const data = (payload.points ?? []).map((p) => ({ x: String(p.x ?? ""), y: Number(p.y ?? 0) }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ left: 4, right: 8, top: 8, bottom: 28 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="x" tick={{ fontSize: 10 }} angle={-30} dy={10} height={48} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Bar dataKey="y" name={payload.y || "value"} fill={PALETTE[0]} />
        </BarChart>
      </ResponsiveContainer>
    );
  }
  if (k === "line") {
    const data = (payload.points ?? []).map((p) => ({
      x: typeof p.x === "number" ? Number(p.x) : String(p.x ?? ""),
      y: Number(p.y ?? 0),
    }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ left: 4, right: 8, top: 8, bottom: 28 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="x" tick={{ fontSize: 10 }} angle={-30} dy={10} height={48} />
          <YAxis tick={{ fontSize: 10 }} />
          <Tooltip />
          <Line type="monotone" dataKey="y" name={payload.y || "value"} stroke={PALETTE[0]} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    );
  }
  if (k === "scatter") {
    const data = (payload.points ?? []).map((p) => ({ x: Number(p.x ?? 0), y: Number(p.y ?? 0) }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <ScatterChart margin={{ left: 4, right: 8, top: 8, bottom: 28 }}>
          <CartesianGrid stroke="var(--border)" />
          <XAxis type="number" dataKey="x" name={payload.x} tick={{ fontSize: 10 }} />
          <YAxis type="number" dataKey="y" name={payload.y} tick={{ fontSize: 10 }} />
          <Tooltip cursor={{ strokeDasharray: "3 3" }} />
          <Scatter data={data} fill={PALETTE[0]} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }
  if (k === "pie") {
    const data = (payload.points ?? []).map((p) => ({ name: String(p.name ?? ""), value: Number(p.value ?? 0) }));
    return (
      <ResponsiveContainer width="100%" height={height}>
        <PieChart>
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Pie data={data} dataKey="value" nameKey="name" outerRadius={Math.min(height / 2 - 16, 110)} label={false}>
            {data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    );
  }
  if (k === "box") {
    return <BoxPlot points={(payload.points ?? []) as BoxRow[]} height={height} />;
  }
  if (k === "heatmap") {
    return (
      <Heatmap
        columns={payload.columns ?? []}
        matrix={payload.matrix ?? []}
        height={height}
      />
    );
  }
  return (
    <div
      className="text-[12px] text-[var(--text-muted)] p-4 border border-dashed border-[var(--border)] rounded text-center"
      role="alert"
      dir="rtl"
    >
      Chart type &quot;{payload.chart}&quot; is not supported in this view.
    </div>
  );
}

type BoxRow = {
  column: string;
  min: number;
  q1: number;
  median: number;
  q3: number;
  max: number;
};

function BoxPlot({ points, height }: { points: BoxRow[]; height: number }) {
  if (!points.length) return <div className="text-[12px] text-[var(--text-muted)] text-center" dir="rtl">No numeric columns.</div>;
  const allMin = Math.min(...points.map((p) => p.min));
  const allMax = Math.max(...points.map((p) => p.max));
  const range = allMax - allMin || 1;
  const w = 600;
  const padTop = 16;
  const padBot = 30;
  const usable = height - padTop - padBot;
  const colW = w / points.length;
  const y = (v: number) => padTop + ((allMax - v) / range) * usable;
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} preserveAspectRatio="none">
        {points.map((p, i) => {
          const cx = colW * i + colW / 2;
          const boxX = cx - 18;
          return (
            <g key={p.column}>
              <line x1={cx} x2={cx} y1={y(p.min)} y2={y(p.max)} stroke={PALETTE[0]} strokeWidth={1.2} />
              <rect
                x={boxX}
                y={y(p.q3)}
                width={36}
                height={Math.max(2, y(p.q1) - y(p.q3))}
                fill={PALETTE[1]}
                fillOpacity={0.3}
                stroke={PALETTE[0]}
              />
              <line x1={boxX} x2={boxX + 36} y1={y(p.median)} y2={y(p.median)} stroke={PALETTE[0]} strokeWidth={1.5} />
              <text x={cx} y={height - 8} textAnchor="middle" fontSize={9} fill="var(--text-muted)">
                {p.column.length > 12 ? p.column.slice(0, 11) + "…" : p.column}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Heatmap({ columns, matrix, height }: { columns: string[]; matrix: number[][]; height: number }) {
  if (!columns.length || !matrix.length) {
    return <div className="text-[12px] text-[var(--text-muted)] text-center" dir="rtl">No correlations available.</div>;
  }
  const cell = Math.max(18, Math.min(48, Math.floor((height - 60) / columns.length)));
  function color(v: number) {
    const a = Math.min(1, Math.abs(v));
    if (v >= 0) return `rgba(37, 99, 235, ${a})`;
    return `rgba(239, 68, 68, ${a})`;
  }
  return (
    <div className="overflow-auto">
      <div
        className="grid"
        style={{
          gridTemplateColumns: `auto repeat(${columns.length}, ${cell}px)`,
          rowGap: 2,
          columnGap: 2,
        }}
      >
        <div />
        {columns.map((c) => (
          <div key={`h-${c}`} className="text-[9px] text-[var(--text-muted)] text-center truncate">{c}</div>
        ))}
        {matrix.map((row, i) => (
          <div className="contents" key={i}>
            <div className="text-[9px] text-[var(--text-muted)] pr-2 truncate text-right">{columns[i]}</div>
            {row.map((v, j) => (
              <div
                key={j}
                title={`${columns[i]} × ${columns[j]} = ${v.toFixed(2)}`}
                className="text-[9px] text-center text-white rounded-[2px] flex items-center justify-center"
                style={{ width: cell, height: cell, background: color(v) }}
              >
                {v.toFixed(1)}
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
