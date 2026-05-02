"use client";
/**
 * Power BI–style pivot builder.
 *
 * Wells:
 *   - Filters    (column, op, value(s))
 *   - Rows       (dimensions; date dims expose a grain selector)
 *   - Columns    (optional second axis for pivot)
 *   - Values     (measures with explicit aggregation per measure)
 *
 * Toggles:
 *   - View         — Table / Chart / Both.
 *   - Top/Bottom N — limit + direction.
 *   - Subtotals    — show subtotals per outer row dim.
 *   - Grand total  — show / hide the bottom total row.
 *   - Drop nulls   — exclude rows where a dim value is missing.
 *
 * Interactions:
 *   - Click a chart bar / table row → adds an "=" filter on that
 *     dimension value (cross-filter).
 *   - Click "Explain" on any cell / KPI → modal with formula, filter
 *     summary, contributing-row count and a sample.
 *   - Export CSV → downloads exactly what's on screen.
 *
 * Routes through /api/bi/pivot which calls the central aggregation
 * engine — same engine that powers the visualize page, the dashboard
 * and the chat ``make_chart`` tool.
 */
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
  PieChart, Pie, Cell,
} from "recharts";
import { api, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import type {
  AxiomAggregation,
  AxiomExplainResult,
  AxiomFieldMeta,
  AxiomFieldMetaResponse,
  AxiomFilter,
  AxiomMeasureSpec,
  AxiomPivotMeasureView,
  AxiomPivotResult,
} from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  GuidedActionCard,
  ModeAwareHeading,
  MissingDatasetNotice,
} from "@/components/product/ModeAware";

const PALETTE = ["#2563eb", "#60a5fa", "#3b82f6", "#1d4ed8", "#93c5fd", "#0ea5e9", "#1e40af"];
const DATE_GRAINS = ["day", "week", "month", "quarter", "year"] as const;
type DateGrain = typeof DATE_GRAINS[number];

type ViewMode = "both" | "table" | "chart";
type TopDir = "top" | "bottom";

function fmtValue(v: unknown, kind: string | undefined, precision = 2): string {
  if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "—";
  if (typeof v === "number") {
    if (kind === "currency") {
      return v.toLocaleString(undefined, {
        style: "currency", currency: "USD", maximumFractionDigits: precision,
      });
    }
    if (kind === "percent") return `${(v * 100).toFixed(precision)}%`;
    if (kind === "integer") return Math.round(v).toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: precision });
  }
  return String(v);
}

function PivotPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const datasetId = typeof window !== "undefined" ? getActiveDatasetId() : null;
  const [meta, setMeta] = useState<AxiomFieldMetaResponse | null>(null);
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [rows, setRows] = useState<string[]>([]);
  const [cols, setCols] = useState<string[]>([]);
  const [measures, setMeasures] = useState<AxiomMeasureSpec[]>([]);
  const [filters, setFilters] = useState<AxiomFilter[]>([]);
  const [dateGrains, setDateGrains] = useState<Record<string, DateGrain>>({});
  const [view, setView] = useState<ViewMode>("both");
  const [topN, setTopN] = useState<number>(50);
  const [topDir, setTopDir] = useState<TopDir>("top");
  const [showSubtotals, setShowSubtotals] = useState<boolean>(true);
  const [showGrandTotal, setShowGrandTotal] = useState<boolean>(true);
  const [dropNulls, setDropNulls] = useState<boolean>(false);
  const [collapsedSubtotals, setCollapsedSubtotals] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AxiomPivotResult | null>(null);
  const [explain, setExplain] = useState<AxiomExplainResult | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);
  const seededFromUrl = useRef(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    if (!datasetId) { setHasDataset(false); return; }
    setHasDataset(true);
    api<AxiomFieldMetaResponse>(`/api/bi/${datasetId}/field-meta`)
      .then((r) => {
        setMeta(r);
        // Drill-through from the dashboard via querystring takes
        // precedence over any auto-seeding.
        const qsRow = searchParams.get("row");
        const qsMeasure = searchParams.get("measure");
        const qsAgg = searchParams.get("agg") as AxiomAggregation | null;
        const qsFilter = searchParams.get("filter"); // "col=value"
        if (qsRow || qsMeasure || qsFilter) {
          if (qsRow) setRows([qsRow]);
          if (qsMeasure) {
            const fm = r.fields[qsMeasure];
            const agg = qsAgg || (fm?.default_agg && fm.default_agg !== "none" ? fm.default_agg : "sum");
            setMeasures([{ column: qsMeasure, aggregation: agg }]);
          }
          if (qsFilter && qsFilter.includes("=")) {
            const [col, ...rest] = qsFilter.split("=");
            setFilters([{ column: col, op: "=", value: rest.join("=") }]);
          }
          // If the seeded row is a date column, default to month grain.
          if (qsRow && r.fields[qsRow]?.role === "date") {
            setDateGrains({ [qsRow]: "month" });
          }
          seededFromUrl.current = true;
          return;
        }
        // Auto-seed: first dimension as row, top measure as value.
        const fields = Object.entries(r.fields);
        const firstDim = fields.find(([, m]) => m.role === "dimension")?.[0];
        const firstMeasure = fields.find(([, m]) => m.role === "measure");
        const firstDate = fields.find(([, m]) => m.role === "date")?.[0];
        if (firstDim) setRows([firstDim]);
        if (firstMeasure) {
          setMeasures([{ column: firstMeasure[0], aggregation: firstMeasure[1].default_agg }]);
        }
        if (firstDate) setDateGrains({ [firstDate]: "month" });
      })
      .catch((e) => setError(errMessage(e)));
  }, [datasetId, router, searchParams]);

  const fields = meta?.fields || {};
  const fieldList = Object.entries(fields) as Array<[string, AxiomFieldMeta]>;
  // Hidden fields are intentionally absent from every well.  Identifiers
  // ("key" role) are absent from the Values well too — the central
  // engine accepts them but they're almost never the user's intent.
  const dims = fieldList.filter(
    ([, m]) => (m.role === "dimension" || m.role === "date") && m.visible !== false
  );
  const allMeasures = fieldList.filter(([, m]) => m.role === "measure" && m.visible !== false);

  // Guided-mode "templates": one-click pivots derived from the auto-
  // profiled field meta. Each template fills the wells in one shot and
  // the existing recompute-on-state-change effect runs the pivot.
  const guidedTemplates = useMemo(() => {
    const out: Array<{
      key: string;
      title: string;
      description: string;
      cta: string;
      apply: () => void;
    }> = [];
    const firstDateCol = fieldList.find(([, m]) => m.role === "date")?.[0];
    const firstDimCol = fieldList.find(([, m]) => m.role === "dimension" && m.visible !== false)?.[0];
    const topMeasure = allMeasures[0];
    if (topMeasure && firstDateCol) {
      const [mc, mm] = topMeasure;
      out.push({
        key: "trend",
        title: `Total ${mm.label || mc} by month`,
        description: `Tracks ${mm.label || mc} over time, grouped by month.`,
        cta: "Show trend",
        apply: () => {
          setRows([firstDateCol]);
          setCols([]);
          setMeasures([{ column: mc, aggregation: (mm.default_agg && mm.default_agg !== "none" ? mm.default_agg : "sum") as AxiomAggregation }]);
          setDateGrains({ [firstDateCol]: "month" });
          setFilters([]);
          setTopN(0);
        },
      });
    }
    if (topMeasure && firstDimCol) {
      const [mc, mm] = topMeasure;
      out.push({
        key: "top10",
        title: `Top 10 ${firstDimCol} by ${mm.label || mc}`,
        description: `Highest ${mm.label || mc} broken down by ${firstDimCol}.`,
        cta: "Show top 10",
        apply: () => {
          setRows([firstDimCol]);
          setCols([]);
          setMeasures([{ column: mc, aggregation: (mm.default_agg && mm.default_agg !== "none" ? mm.default_agg : "sum") as AxiomAggregation }]);
          setDateGrains({});
          setFilters([]);
          setTopN(10);
          setTopDir("top");
        },
      });
    }
    if (firstDimCol) {
      out.push({
        key: "counts",
        title: `Counts by ${firstDimCol}`,
        description: `How many rows fall into each ${firstDimCol} bucket.`,
        cta: "Count rows",
        apply: () => {
          setRows([firstDimCol]);
          setCols([]);
          setMeasures([{ column: firstDimCol, aggregation: "count" }]);
          setDateGrains({});
          setFilters([]);
          setTopN(20);
          setTopDir("top");
        },
      });
    }
    if (allMeasures.length > 0) {
      out.push({
        key: "kpis",
        title: "Quick numbers across the dataset",
        description: "Grand totals for every numeric column at a glance.",
        cta: "Show grand totals",
        apply: () => {
          setRows([]);
          setCols([]);
          setMeasures(
            allMeasures.slice(0, 4).map(([c, m]) => ({
              column: c,
              aggregation: (m.default_agg && m.default_agg !== "none" ? m.default_agg : "sum") as AxiomAggregation,
            })),
          );
          setDateGrains({});
          setFilters([]);
          setTopN(0);
        },
      });
    }
    return out;
  }, [fieldList, allMeasures]);

  // Build the request payload that's used both for /pivot and CSV export.
  const buildRequest = useCallback(() => {
    if (!datasetId) return null;
    const grainsForRows: Record<string, string> = {};
    for (const r of rows) {
      if (dateGrains[r]) grainsForRows[r] = dateGrains[r];
    }
    return {
      dataset_id: datasetId,
      rows,
      cols,
      measures,
      filters,
      date_grains: grainsForRows,
      include_subtotals: showSubtotals && rows.length > 1,
      include_grand_total: showGrandTotal,
      drop_nulls_in_dims: dropNulls,
      top_n: topN > 0 ? topN : undefined,
      sort: topN > 0 && measures.length > 0
        ? [{ by: "m0", dir: topDir === "top" ? "desc" : "asc" }]
        : undefined,
    };
  }, [datasetId, rows, cols, measures, filters, dateGrains, showSubtotals, showGrandTotal, dropNulls, topN, topDir]);

  const run = useCallback(async () => {
    const payload = buildRequest();
    if (!payload) return;
    setBusy(true); setError(null);
    try {
      const r = await api<AxiomPivotResult>("/api/bi/pivot", {
        method: "POST",
        json: payload as unknown as Record<string, unknown>,
      });
      setResult(r);
    } catch (e) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }, [buildRequest]);

  // Recompute whenever the wells / toggles change.
  useEffect(() => {
    if (!datasetId || !meta) return;
    if (rows.length === 0 && cols.length === 0 && measures.length === 0) return;
    void run();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows, cols, measures, filters, dateGrains, showSubtotals, showGrandTotal, dropNulls, topN, topDir, datasetId, meta]);

  // Build a flat dataset for the chart view from the pivot rows
  // (excluding any subtotal rows).
  const chartData = useMemo(() => {
    if (!result || !result.rows.length) return [] as Array<Record<string, unknown>>;
    const data: Array<Record<string, unknown>> = [];
    const rowKey = result.row_dims[0];
    if (!rowKey) return data;
    const visibleRows = result.rows.filter((r) => r._subtotal_level === undefined);
    if (result.col_dims.length === 0) {
      for (const r of visibleRows) {
        const out: Record<string, unknown> = { __label: String(r._dims[rowKey] ?? "—") };
        for (const m of result.measures) {
          out[m.label] = r[m.key];
        }
        data.push(out);
      }
      return data;
    }
    const colKey = result.col_dims[0];
    const groups = new Map<string, Record<string, unknown>>();
    for (const r of visibleRows) {
      const rk = String(r._dims[rowKey] ?? "—");
      if (!groups.has(rk)) groups.set(rk, { __label: rk });
      const g = groups.get(rk)!;
      const ck = String(r._cols[colKey] ?? "—");
      const mv = result.measures[0];
      if (mv) g[ck] = r[mv.key];
    }
    return Array.from(groups.values());
  }, [result]);

  // Click on a chart bar/point — push the dimension value as an
  // equality filter (cross-filter behaviour).
  const onCrossFilter = useCallback((dim: string, value: unknown) => {
    if (!dim || value === null || value === undefined) return;
    setFilters((cur) => {
      const dropped = cur.filter((f) => !(f.column === dim && f.op === "="));
      return [...dropped, { column: dim, op: "=", value: String(value) }];
    });
  }, []);

  const openExplain = useCallback(async (
    measure: AxiomPivotMeasureView,
    coordinate: Record<string, unknown>,
  ) => {
    if (!datasetId) return;
    setExplainLoading(true);
    setExplain({
      dataset_id: datasetId, measure, value: null, formula: "",
      filter_summary: [], contributing_rows: 0, total_rows: 0,
      sample_rows: [], warnings: [],
    });
    try {
      const r = await api<AxiomExplainResult>("/api/bi/explain", {
        method: "POST",
        json: {
          dataset_id: datasetId,
          measure: {
            column: measure.column,
            aggregation: measure.aggregation,
            label: measure.label,
            numerator: measure.numerator,
            denominator: measure.denominator,
          },
          filters,
          coordinate,
          sample_rows: 20,
        } as unknown as Record<string, unknown>,
      });
      setExplain(r);
    } catch (e) {
      setExplain({
        dataset_id: datasetId, measure, value: null,
        formula: errMessage(e), filter_summary: [],
        contributing_rows: 0, total_rows: 0, sample_rows: [], warnings: [],
      });
    } finally { setExplainLoading(false); }
  }, [datasetId, filters]);

  const exportCsv = useCallback(async () => {
    const payload = buildRequest();
    if (!payload) return;
    try {
      const token = getToken();
      const res = await fetch("/api/bi/export/csv", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `dataset_${datasetId}_pivot.csv`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setError(errMessage(e)); }
  }, [buildRequest, datasetId]);

  const chart = useMemo(() => {
    if (!result || !chartData.length) return null;
    const suggestion = result.chart_suggestion || "bar";
    const measureKeys = result.col_dims.length > 0
      ? Array.from(new Set(chartData.flatMap((r) => Object.keys(r).filter((k) => k !== "__label"))))
      : result.measures.map((m) => m.label);
    const rowDim = result.row_dims[0];
    const onPointClick = (data: { __label?: unknown }) => {
      if (rowDim) onCrossFilter(rowDim, data.__label);
    };

    if (suggestion === "kpi" && result.measures[0]) {
      const m = result.measures[0];
      const v = result.grand_total[m.key];
      return (
        <div className="text-center py-8 relative">
          <div className="text-xs uppercase tracking-widest text-[var(--text-muted)]">{m.label}</div>
          <div className="text-4xl font-semibold mt-2">{fmtValue(v, m.format_kind, m.precision)}</div>
          <button
            onClick={() => openExplain(m, {})}
            className="absolute top-2 right-2 text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] underline"
          >
            شرح
          </button>
        </div>
      );
    }
    if (suggestion === "line") {
      return (
        <ResponsiveContainer width="100%" height={360}>
          <LineChart data={chartData} onClick={(s) => s && s.activePayload?.[0] && onPointClick(s.activePayload[0].payload)}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="__label" />
            <YAxis />
            <Tooltip />
            <Legend />
            {measureKeys.map((mk, i) => (
              <Line key={mk} type="monotone" dataKey={mk} stroke={PALETTE[i % PALETTE.length]} dot={false} />
            ))}
          </LineChart>
        </ResponsiveContainer>
      );
    }
    if (suggestion === "pie" && result.measures[0]) {
      const m = result.measures[0];
      return (
        <ResponsiveContainer width="100%" height={360}>
          <PieChart>
            <Pie
              data={chartData.map((r) => ({ name: r.__label, value: r[m.label] || 0 }))}
              dataKey="value" nameKey="name" outerRadius={120} label
              onClick={(s: { name?: unknown }) => s && onCrossFilter(rowDim!, s.name)}
            >
              {chartData.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      );
    }
    // Default: bar / stacked_bar / funnel-as-bar.
    return (
      <ResponsiveContainer width="100%" height={360}>
        <BarChart data={chartData} onClick={(s) => s && s.activePayload?.[0] && onPointClick(s.activePayload[0].payload)}>
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="__label" />
          <YAxis />
          <Tooltip />
          <Legend />
          {measureKeys.map((mk, i) => (
            <Bar
              key={mk}
              dataKey={mk}
              fill={PALETTE[i % PALETTE.length]}
              stackId={suggestion === "stacked_bar" ? "stack" : undefined}
              cursor="pointer"
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    );
  }, [result, chartData, onCrossFilter, openExplain]);

  return (
    <div className="max-w-6xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Analysis · Pivot"
        guidedTitle="Slice & dice your data"
        expertTitle="Pivot table"
        guidedSubtitle="Pick what to break down by (rows / columns) and what to measure (values). The same numbers feed your dashboard."
        expertSubtitle="Power BI–style pivot. Rows / Columns / Values / Filters routed through the central aggregation engine."
      />

      {hasDataset === false ? (
        <MissingDatasetNotice projectId={projectId} toolName="pivot" />
      ) : !meta ? (
        <div className="text-xs text-[var(--text-muted)] mt-6" role="status">جارٍ تحميل بيانات الحقول…</div>
      ) : (
        <>
          {mode === "guided" && guidedTemplates.length > 0 && (
            <div className="mt-6">
              <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
                ملخّصات جاهزة
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {guidedTemplates.map((t) => (
                  <GuidedActionCard
                    key={t.key}
                    title={t.title}
                    description={t.description}
                    cta={t.cta}
                    onAction={t.apply}
                  />
                ))}
              </div>
            </div>
          )}
        {(() => {
          const wellsColumn = (
          <div className="space-y-4">
            <FieldsPalette dims={dims} measures={allMeasures} />
            <Well
              label="عوامل التصفية"
              chips={filters.map((f) => `${f.column} ${f.op}`)}
              onClear={() => setFilters([])}
            >
              <FilterBuilder fields={fields} onAdd={(f) => setFilters((cur) => [...cur, f])} />
              {filters.map((f, i) => (
                <div key={i} className="text-xs flex items-center justify-between mt-1">
                  <span className="font-mono">
                    {f.column} {f.op} {String(f.value ?? f.values?.join(",") ?? "")}
                  </span>
                  <button onClick={() => setFilters((cur) => cur.filter((_, j) => j !== i))} className="text-[var(--text-muted)] hover:text-red-500">×</button>
                </div>
              ))}
            </Well>
            <Well label="الصفوف" chips={rows} onClear={() => { setRows([]); setDateGrains({}); }}>
              <ColumnPicker
                fields={dims}
                excluded={[...rows, ...cols]}
                onPick={(c) => {
                  setRows((cur) => [...cur, c]);
                  if (fields[c]?.role === "date" && !dateGrains[c]) {
                    setDateGrains((cur) => ({ ...cur, [c]: "month" }));
                  }
                }}
              />
              {rows.map((c, i) => {
                const isDate = fields[c]?.role === "date";
                return (
                  <div key={c} className="text-xs flex items-center gap-1 mt-1">
                    <span className="font-mono flex-1 truncate">{c}</span>
                    {isDate && (
                      <select
                        value={dateGrains[c] || "month"}
                        onChange={(e) => setDateGrains((cur) => ({ ...cur, [c]: e.target.value as DateGrain }))}
                        className="px-1 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[10px]"
                      >
                        {DATE_GRAINS.map((g) => <option key={g} value={g}>{g}</option>)}
                      </select>
                    )}
                    <button onClick={() => setRows((cur) => cur.filter((_, j) => j !== i))} className="text-[var(--text-muted)] hover:text-red-500">×</button>
                  </div>
                );
              })}
            </Well>
            <Well label="الأعمدة" chips={cols} onClear={() => setCols([])}>
              <ColumnPicker fields={dims} excluded={[...rows, ...cols]} onPick={(c) => setCols((cur) => [...cur, c])} />
              {cols.map((c, i) => (
                <Chip key={c} label={c} onRemove={() => setCols((cur) => cur.filter((_, j) => j !== i))} />
              ))}
            </Well>
            <Well
              label="القيم"
              chips={measures.map((m) => m.label || `${m.aggregation} of ${m.column}`)}
              onClear={() => setMeasures([])}
            >
              <MeasurePicker
                fields={fields}
                vocab={meta.vocab}
                onAdd={(m) => setMeasures((cur) => [...cur, m])}
              />
              <RatioBuilder
                fields={fields}
                onAdd={(m) => setMeasures((cur) => [...cur, m])}
              />
              {measures.map((m, i) => (
                <div key={i} className="text-xs flex items-center gap-1 mt-1">
                  <select
                    value={m.aggregation}
                    onChange={(e) => {
                      const next = [...measures];
                      next[i] = { ...m, aggregation: e.target.value as AxiomAggregation };
                      setMeasures(next);
                    }}
                    className="px-1.5 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[10px]"
                  >
                    {meta.vocab.aggregations.map((a) => (
                      <option key={a} value={a}>{meta.vocab.agg_labels[a]}</option>
                    ))}
                  </select>
                  <span className="font-mono flex-1 truncate">{m.column}</span>
                  <button onClick={() => setMeasures((cur) => cur.filter((_, j) => j !== i))} className="text-[var(--text-muted)] hover:text-red-500">×</button>
                </div>
              ))}
            </Well>
            <div className="card space-y-2">
              <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-muted)]">العرض</div>
              <div className="text-[11px] flex items-center gap-2">
                <select value={topDir} onChange={(e) => setTopDir(e.target.value as TopDir)} className="px-1 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[10px]">
                  <option value="top">الأعلى</option>
                  <option value="bottom">الأدنى</option>
                </select>
                <input
                  type="number" min={0} value={topN}
                  onChange={(e) => setTopN(Math.max(0, Number(e.target.value) || 0))}
                  className="w-16 px-1.5 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[11px]"
                />
                <span className="text-[10px] text-[var(--text-muted)]">N (0 = الكل)</span>
              </div>
              <label className="text-[11px] flex items-center gap-2">
                <input type="checkbox" checked={showSubtotals} onChange={(e) => setShowSubtotals(e.target.checked)} />
                المجاميع الفرعية
              </label>
              <label className="text-[11px] flex items-center gap-2">
                <input type="checkbox" checked={showGrandTotal} onChange={(e) => setShowGrandTotal(e.target.checked)} />
                المجموع الكلي
              </label>
              <label className="text-[11px] flex items-center gap-2">
                <input type="checkbox" checked={dropNulls} onChange={(e) => setDropNulls(e.target.checked)} />
                إسقاط القيم الفارغة من الأبعاد
              </label>
            </div>
          </div>
          );
          const resultColumn = (
          <div>
            <div className="flex items-center gap-2 mb-3 flex-wrap">
              {mode !== "guided" && (
                <div className="inline-flex border border-[var(--border)] rounded overflow-hidden">
                  {(["both", "table", "chart"] as ViewMode[]).map((v) => (
                    <button
                      key={v}
                      onClick={() => setView(v)}
                      className={`px-3 py-1 text-xs ${view === v ? "bg-[var(--accent)] text-white" : "text-[var(--text)] hover:bg-[var(--surface)]"}`}
                    >
                      {v === "both" ? "الكل" : v === "table" ? "جدول" : "رسم بياني"}
                    </button>
                  ))}
                </div>
              )}
              <button onClick={run} disabled={busy} className="btn btn-secondary text-xs">
                {busy ? "جارٍ التشغيل…" : "تحديث"}
              </button>
              {mode !== "guided" && (
                <button onClick={exportCsv} disabled={!result} className="btn btn-secondary text-xs">
                  تصدير CSV
                </button>
              )}
              {result && mode !== "guided" && (
                <span className="text-[10px] text-[var(--text-muted)] font-mono ml-auto">
                  {result.row_count.toLocaleString()} صف مدخل → {result.result_count} خلية
                </span>
              )}
            </div>

            {error && <div className="text-sm text-red-600 mb-3" role="alert">{error}</div>}

            {result && result.warnings && result.warnings.length > 0 && (
              <ul className="mb-3 text-xs text-amber-600 list-disc list-inside space-y-0.5">
                {result.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}

            {(view === "chart" || view === "both") && (
              <div className="card">
                {result && result.rows.length > 0 ? chart : (
                  <div className="text-xs text-[var(--text-muted)] py-8 text-center">
                    أضف بُعدًا إلى الصفوف ومقياسًا إلى القيم لعرض الرسم البياني.
                  </div>
                )}
              </div>
            )}

            {(view === "table" || view === "both") && (
              <div className={view === "both" ? "mt-3" : ""}>
                {result ? (
                  <PivotTable
                    result={result}
                    showGrandTotal={showGrandTotal}
                    collapsed={collapsedSubtotals}
                    onToggleSubtotal={(k) => setCollapsedSubtotals((cur) => ({ ...cur, [k]: !cur[k] }))}
                    onCrossFilter={onCrossFilter}
                    onExplain={openExplain}
                  />
                ) : (
                  <div className="text-xs text-[var(--text-muted)]">لا توجد نتائج بعد.</div>
                )}
              </div>
            )}
          </div>
          );
          if (mode === "guided") {
            return (
              <div className="mt-4 space-y-4">
                {resultColumn}
                <AdvancedExpander
                  projectId={projectId}
                  title="فتح أداة الجدول المحوري الكاملة"
                  hint="الصفوف والأعمدة والقيم وعوامل التصفية والمجاميع"
                >
                  {wellsColumn}
                </AdvancedExpander>
              </div>
            );
          }
          return (
            <div className="grid grid-cols-1 lg:grid-cols-[260px_1fr] gap-6 mt-6">
              {wellsColumn}
              {resultColumn}
            </div>
          );
        })()}
        </>
      )}

      {explain && (
        <ExplainModal
          loading={explainLoading}
          payload={explain}
          onClose={() => setExplain(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function FieldsPalette({
  dims, measures,
}: {
  dims: Array<[string, AxiomFieldMeta]>;
  measures: Array<[string, AxiomFieldMeta]>;
}) {
  return (
    <div className="card">
      <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
        الحقول
      </div>
      <div className="text-[10px] text-[var(--text-muted)] mt-1 mb-1">الأبعاد</div>
      <ul className="space-y-0.5">
        {dims.map(([c, m]) => (
          <li key={c} className="text-xs font-mono px-2 py-0.5 rounded bg-[var(--surface)]">
            {c} <span className="text-[10px] text-[var(--text-muted)]">· {m.role}</span>
          </li>
        ))}
      </ul>
      <div className="text-[10px] text-[var(--text-muted)] mt-3 mb-1">المقاييس</div>
      <ul className="space-y-0.5">
        {measures.map(([c, m]) => (
          <li key={c} className="text-xs font-mono px-2 py-0.5 rounded bg-[var(--surface)]">
            {c} <span className="text-[10px] text-[var(--text-muted)]">· {m.default_agg}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Well({
  label, chips, onClear, children,
}: { label: string; chips: string[]; onClear: () => void; children: React.ReactNode }) {
  return (
    <div className="card">
      <div className="flex items-center justify-between mb-1">
        <div className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-muted)]">{label}</div>
        {chips.length > 0 && (
          <button onClick={onClear} className="text-[10px] text-[var(--text-muted)] hover:text-red-500">مسح</button>
        )}
      </div>
      {children}
    </div>
  );
}

function ColumnPicker({
  fields, excluded, onPick,
}: { fields: Array<[string, AxiomFieldMeta]>; excluded: string[]; onPick: (c: string) => void }) {
  const available = fields.filter(([c]) => !excluded.includes(c));
  if (!available.length) return <div className="text-[10px] text-[var(--text-muted)]">لا توجد حقول أخرى</div>;
  return (
    <select
      value=""
      onChange={(e) => { if (e.target.value) onPick(e.target.value); e.currentTarget.value = ""; }}
      className="w-full px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
    >
      <option value="">+ إضافة عمود…</option>
      {available.map(([c]) => <option key={c} value={c}>{c}</option>)}
    </select>
  );
}

function MeasurePicker({
  fields, vocab, onAdd,
}: {
  fields: Record<string, AxiomFieldMeta>;
  vocab: AxiomFieldMetaResponse["vocab"];
  onAdd: (m: AxiomMeasureSpec) => void;
}) {
  const [col, setCol] = useState("");
  // Only fields whose role is "measure" (or numeric dimensions count for
  // count_distinct) belong in the Values well.  Hiding identifiers /
  // dates / hidden fields prevents nonsensical aggregations like
  // SUM(customer_id) — the engine would warn, but it's better never to
  // offer the option in the first place.
  const measureFields = Object.entries(fields).filter(
    ([, m]) => m.role === "measure" && m.visible !== false
  );
  return (
    <div className="flex items-center gap-1">
      <select
        value={col}
        onChange={(e) => setCol(e.target.value)}
        className="flex-1 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
      >
        <option value="">+ إضافة مقياس…</option>
        {measureFields.map(([c, m]) => (
          <option key={c} value={c}>{c} ({m.default_agg})</option>
        ))}
      </select>
      <button
        type="button"
        disabled={!col}
        onClick={() => {
          const m = fields[col];
          if (!m) return;
          const agg = (m.default_agg && m.default_agg !== "none" ? m.default_agg : "sum") as AxiomAggregation;
          onAdd({ column: col, aggregation: agg });
          setCol("");
        }}
        className="px-2 py-1 text-[11px] rounded bg-[var(--accent)] text-white disabled:opacity-50"
      >
        إضافة
      </button>
      <span className="hidden">{vocab.aggregations.length}</span>
    </div>
  );
}

function RatioBuilder({
  fields, onAdd,
}: {
  fields: Record<string, AxiomFieldMeta>;
  onAdd: (m: AxiomMeasureSpec) => void;
}) {
  const [num, setNum] = useState("");
  const [den, setDen] = useState("");
  const [open, setOpen] = useState(false);
  // The numerator and denominator must be raw numeric facts, never an
  // already-aggregated rate.  Filtering on format_kind != "percent"
  // makes a ratio-of-ratios literally unbuildable from the UI.
  const candidates = Object.entries(fields).filter(
    ([, m]) =>
      m.role === "measure" && m.visible !== false && m.format_kind !== "percent",
  );
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-[11px] text-[var(--accent)] hover:underline mt-1"
        title="Build a derived ratio metric (e.g. CTR = clicks / impressions). Recomputed at every grain — never summed."
      >
        + إضافة مقياس نسبة (CTR / هامش% / تحويل …)
      </button>
    );
  }
  return (
    <div className="mt-1 p-2 rounded border border-[var(--border)] bg-[var(--surface)]/50">
      <div className="text-[11px] text-[var(--text-muted)] mb-1">
        النسبة = SUM(البسط) ÷ SUM(المقام)، يُعاد حسابها عند كل مستوى.
        تُعرض دائمًا كنسبة مئوية.
      </div>
      <div className="grid grid-cols-2 gap-1">
        <select
          value={num}
          onChange={(e) => setNum(e.target.value)}
          className="px-1.5 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[11px]"
        >
          <option value="">البسط…</option>
          {candidates.map(([c]) => (<option key={c} value={c}>{c}</option>))}
        </select>
        <select
          value={den}
          onChange={(e) => setDen(e.target.value)}
          className="px-1.5 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[11px]"
        >
          <option value="">المقام…</option>
          {candidates.filter(([c]) => c !== num).map(([c]) => (<option key={c} value={c}>{c}</option>))}
        </select>
      </div>
      <div className="flex justify-end gap-1 mt-1">
        <button
          type="button"
          onClick={() => { setOpen(false); setNum(""); setDen(""); }}
          className="text-[11px] text-[var(--text-muted)] px-2 py-0.5"
        >إلغاء</button>
        <button
          type="button"
          disabled={!num || !den}
          onClick={() => {
            onAdd({
              aggregation: "ratio",
              numerator: num,
              denominator: den,
              numerator_agg: "sum",
              denominator_agg: "sum",
              format_kind: "percent",
              label: `${num} ÷ ${den}`,
            });
            setOpen(false); setNum(""); setDen("");
          }}
          className="text-[11px] px-2 py-0.5 rounded bg-[var(--accent)] text-white disabled:opacity-50"
        >إضافة النسبة</button>
      </div>
    </div>
  );
}

function FilterBuilder({
  fields, onAdd,
}: {
  fields: Record<string, AxiomFieldMeta>;
  onAdd: (f: AxiomFilter) => void;
}) {
  const [col, setCol] = useState("");
  const [op, setOp] = useState<AxiomFilter["op"]>("=");
  const [val, setVal] = useState("");
  const meta = col ? fields[col] : undefined;
  const isText = meta?.format_kind === "text";
  const isNum = meta?.format_kind === "number" || meta?.format_kind === "integer" || meta?.format_kind === "currency" || meta?.format_kind === "percent";
  const ops: AxiomFilter["op"][] = isText
    ? ["=", "!=", "contains", "in", "is_null", "not_null"]
    : isNum
    ? ["=", "!=", ">", ">=", "<", "<=", "between"]
    : ["=", "!=", "is_null", "not_null"];

  return (
    <div className="space-y-1">
      <select value={col} onChange={(e) => setCol(e.target.value)} className="w-full px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs">
        <option value="">+ إضافة عامل تصفية…</option>
        {Object.keys(fields).map((c) => <option key={c} value={c}>{c}</option>)}
      </select>
      {col && (
        <div className="flex items-center gap-1">
          <select value={op} onChange={(e) => setOp(e.target.value as AxiomFilter["op"])} className="px-1 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[10px]">
            {ops.map((o) => <option key={o} value={o}>{o}</option>)}
          </select>
          {(op !== "is_null" && op !== "not_null") && (
            <input value={val} onChange={(e) => setVal(e.target.value)} className="flex-1 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[11px]" placeholder="قيمة" />
          )}
          <button
            type="button"
            onClick={() => {
              const f: AxiomFilter = { column: col, op };
              if (op === "in" || op === "not_in") f.values = val.split(",").map((s) => s.trim()).filter(Boolean);
              else if (op === "between") {
                const [lo, hi] = val.split(",").map((s) => s.trim());
                f.min = lo; f.max = hi;
              } else if (op !== "is_null" && op !== "not_null") f.value = val;
              onAdd(f);
              setCol(""); setVal("");
            }}
            className="px-2 py-1 text-[11px] rounded bg-[var(--accent)] text-white"
          >
            +
          </button>
        </div>
      )}
    </div>
  );
}

function Chip({ label, onRemove }: { label: string; onRemove: () => void }) {
  return (
    <div className="text-xs flex items-center justify-between mt-1 px-2 py-1 rounded bg-[var(--surface)]">
      <span className="font-mono truncate">{label}</span>
      <button onClick={onRemove} className="text-[var(--text-muted)] hover:text-red-500 ml-2">×</button>
    </div>
  );
}

function PivotTable({
  result, showGrandTotal, collapsed, onToggleSubtotal, onCrossFilter, onExplain,
}: {
  result: AxiomPivotResult;
  showGrandTotal: boolean;
  collapsed: Record<string, boolean>;
  onToggleSubtotal: (key: string) => void;
  onCrossFilter: (dim: string, value: unknown) => void;
  onExplain: (m: AxiomPivotMeasureView, coord: Record<string, unknown>) => void;
}) {
  const colDim = result.col_dims[0];
  const rowDims = result.row_dims;
  const colKeys = colDim
    ? Array.from(new Set(
        result.rows
          .filter((r) => r._subtotal_level === undefined)
          .map((r) => String(r._cols[colDim] ?? "—"))
      ))
    : [];

  if (!colDim) {
    // Subtotal-aware single-axis table.  Subtotal rows are rendered as
    // "header strips" the user can click to collapse the detail rows
    // beneath them — Power BI's matrix-style behaviour.
    const visibleRows: typeof result.rows = [];
    let collapseUntil: number | null = null;
    for (const r of result.rows) {
      const sub = r._subtotal_level;
      if (collapseUntil !== null) {
        // Stop collapsing once we see a row with subtotal_level <=
        // the one that triggered the collapse.
        if (sub !== undefined && sub <= collapseUntil) {
          collapseUntil = null;
        } else {
          // Detail or deeper subtotal rows are hidden.
          continue;
        }
      }
      visibleRows.push(r);
      if (sub !== undefined) {
        const key = rowDims.slice(0, sub + 1).map((d) => String(r._dims[d] ?? "")).join("|");
        if (collapsed[key]) collapseUntil = sub;
      }
    }
    return (
      <div className="card p-0 overflow-auto">
        <table className="w-full text-xs">
          <thead className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest">
            <tr className="border-b border-[var(--border)]">
              {rowDims.map((d) => <th key={d} className="text-left px-3 py-2 font-mono">{d}</th>)}
              {result.measures.map((m) => <th key={m.key} className="text-right px-3 py-2">{m.label}</th>)}
              <th className="px-2 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {visibleRows.map((r, i) => {
              const sub = r._subtotal_level;
              if (sub !== undefined) {
                const key = rowDims.slice(0, sub + 1).map((d) => String(r._dims[d] ?? "")).join("|");
                const isCollapsed = !!collapsed[key];
                return (
                  <tr
                    key={`s${i}`}
                    className="bg-[var(--surface)]/60 border-b border-[var(--border)] cursor-pointer hover:bg-[var(--surface)]"
                    onClick={() => onToggleSubtotal(key)}
                  >
                    {rowDims.map((d, j) => (
                      <td key={d} className="px-3 py-1.5 font-mono font-semibold">
                        {j === sub
                          ? `${isCollapsed ? "▶" : "▼"} ${String(r._dims[d] ?? "—")} subtotal`
                          : j < sub ? String(r._dims[d] ?? "—") : ""}
                      </td>
                    ))}
                    {result.measures.map((m) => (
                      <td key={m.key} className="px-3 py-1.5 text-right tabular-nums font-semibold">
                        {fmtValue(r[m.key], m.format_kind, m.precision)}
                      </td>
                    ))}
                    <td></td>
                  </tr>
                );
              }
              return (
                <tr key={i} className="border-b border-[var(--border)]/60 hover:bg-[var(--surface)]/40">
                  {rowDims.map((d) => (
                    <td
                      key={d}
                      className="px-3 py-1.5 font-mono cursor-pointer"
                      onClick={() => onCrossFilter(d, r._dims[d])}
                      title="اضغط لإضافته كعامل تصفية"
                    >
                      {String(r._dims[d] ?? "—")}
                    </td>
                  ))}
                  {result.measures.map((m) => (
                    <td key={m.key} className="px-3 py-1.5 text-right tabular-nums">
                      {fmtValue(r[m.key], m.format_kind, m.precision)}
                    </td>
                  ))}
                  <td className="px-2 py-1.5 text-right">
                    <button
                      onClick={() => {
                        const coord: Record<string, unknown> = {};
                        for (const d of rowDims) coord[d] = r._dims[d];
                        onExplain(result.measures[0], coord);
                      }}
                      className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)]"
                      title="اشرح هذا الرقم"
                    >
                      ⓘ
                    </button>
                  </td>
                </tr>
              );
            })}
            {showGrandTotal && (
              <tr className="border-t-2 border-[var(--border)] font-semibold bg-[var(--surface)]/40">
                {rowDims.map((d, i) => <td key={d} className="px-3 py-2 font-mono">{i === 0 ? "المجموع" : ""}</td>)}
                {result.measures.map((m) => (
                  <td key={m.key} className="px-3 py-2 text-right tabular-nums">
                    {fmtValue(result.grand_total[m.key], m.format_kind, m.precision)}
                  </td>
                ))}
                <td></td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    );
  }

  // Cross-tab: rows × cols, single measure.
  const m = result.measures[0];
  const groups = new Map<string, { _dims: Record<string, unknown>; values: Record<string, unknown> }>();
  for (const r of result.rows) {
    if (r._subtotal_level !== undefined) continue;
    const key = rowDims.map((d) => String(r._dims[d] ?? "—")).join("|");
    if (!groups.has(key)) groups.set(key, { _dims: r._dims, values: {} });
    groups.get(key)!.values[String(r._cols[colDim] ?? "—")] = r[m.key];
  }
  return (
    <div className="card p-0 overflow-auto">
      <table className="w-full text-xs">
        <thead className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest">
          <tr className="border-b border-[var(--border)]">
            {rowDims.map((d) => <th key={d} className="text-left px-3 py-2 font-mono">{d}</th>)}
            {colKeys.map((c) => <th key={c} className="text-right px-3 py-2 font-mono">{c}</th>)}
            <th className="px-2 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {Array.from(groups.values()).map((g, i) => (
            <tr key={i} className="border-b border-[var(--border)]/60 hover:bg-[var(--surface)]/40">
              {rowDims.map((d) => (
                <td
                  key={d}
                  className="px-3 py-1.5 font-mono cursor-pointer"
                  onClick={() => onCrossFilter(d, g._dims[d])}
                  title="Click to add as filter"
                >
                  {String(g._dims[d] ?? "—")}
                </td>
              ))}
              {colKeys.map((c) => (
                <td
                  key={c}
                  className="px-3 py-1.5 text-right tabular-nums cursor-pointer"
                  onClick={() => {
                    const coord: Record<string, unknown> = {};
                    for (const d of rowDims) coord[d] = g._dims[d];
                    coord[colDim] = c;
                    onExplain(m, coord);
                  }}
                  title="Click to explain"
                >
                  {fmtValue(g.values[c], m.format_kind, m.precision)}
                </td>
              ))}
              <td></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="text-[10px] text-[var(--text-muted)] px-3 py-2 border-t border-[var(--border)]">
        Showing {m.label}. Click any value to explain it. Add another measure in the Values well to see multiple metrics.
      </div>
    </div>
  );
}

function ExplainModal({
  loading, payload, onClose,
}: {
  loading: boolean;
  payload: AxiomExplainResult;
  onClose: () => void;
}) {
  const m = payload.measure as { label?: string; format_kind?: string; precision?: number };
  return (
    <div
      className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-[var(--bg)] border border-[var(--border)] rounded-lg max-w-2xl w-full max-h-[80vh] overflow-auto p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)]">Explain</div>
            <div className="text-lg font-semibold">{m.label || "Measure"}</div>
          </div>
          <button onClick={onClose} className="text-xl text-[var(--text-muted)] hover:text-[var(--text)]">×</button>
        </div>
        {loading ? (
          <div className="text-xs text-[var(--text-muted)]">Computing…</div>
        ) : (
          <div className="space-y-3 text-xs">
            <div className="text-2xl font-semibold tabular-nums">
              {fmtValue(payload.value, m.format_kind, m.precision)}
            </div>
            {payload.formula && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-1">Formula</div>
                <div className="font-mono text-[11px] bg-[var(--surface)] rounded px-2 py-1.5 break-all">{payload.formula}</div>
              </div>
            )}
            {payload.filter_summary && payload.filter_summary.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-1">Active filters</div>
                <ul className="space-y-0.5">
                  {payload.filter_summary.map((f, i) => (
                    <li key={i} className="font-mono text-[11px]">{f}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="text-[11px] text-[var(--text-muted)]">
              {payload.contributing_rows.toLocaleString()} of {payload.total_rows.toLocaleString()} rows contributed.
            </div>
            {payload.warnings && payload.warnings.length > 0 && (
              <ul className="text-[11px] text-amber-600 list-disc list-inside space-y-0.5">
                {payload.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
            {payload.sample_rows && payload.sample_rows.length > 0 && (
              <div>
                <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-1">Sample contributing rows</div>
                <div className="overflow-auto border border-[var(--border)] rounded max-h-64">
                  <table className="w-full text-[11px]">
                    <thead className="bg-[var(--surface)]/60 sticky top-0">
                      <tr>
                        {Object.keys(payload.sample_rows[0]).map((k) => (
                          <th key={k} className="text-left px-2 py-1 font-mono">{k}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {payload.sample_rows.map((r, i) => (
                        <tr key={i} className="border-t border-[var(--border)]/60">
                          {Object.values(r).map((v, j) => (
                            <td key={j} className="px-2 py-1 font-mono whitespace-nowrap">{String(v ?? "—")}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Wrap in <Suspense> so Next.js 14 doesn't fail the production build with
// "useSearchParams() should be wrapped in a suspense boundary". Without
// this, `next build` aborts during static-page generation for /app/pivot
// because useSearchParams forces a client-side bailout that needs an
// explicit fallback.
export default function PivotPage() {
  return (
    <Suspense fallback={<div className="p-6 text-sm text-muted">Loading pivot…</div>}>
      <PivotPageInner />
    </Suspense>
  );
}
