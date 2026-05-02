"use client";
/**
 * Per-dataset dashboard.
 *
 * One page that summarises the active dataset.  Tiles are grouped
 * into named sections — Executive KPIs, Trend, Segmentation,
 * Operational — that the auto-builder publishes; sections without
 * tiles render nothing.
 *
 * Page-level slicers (a date-range picker + a categorical "Group"
 * filter) live above all tiles and are passed to the backend as
 * query-string parameters so every tile is filtered identically (the
 * Power BI page-filter behaviour).
 *
 * Tiles can be:
 *   - Removed (the surviving spec is persisted via PUT).
 *   - Drilled into → opens /app/pivot pre-seeded with the same row /
 *     measure / filter so the user lands on the matching cross-tab.
 *   - Explained — calls /api/bi/explain for a formula + sample.
 *   - Exported as CSV via /api/bi/export/csv.
 *
 * Modeling safeguards (grain + fan-out warnings) sit at the top so
 * the user notices them before trusting any number.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import { api, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import type {
  AxiomDashboard,
  AxiomDashboardTileResult,
  AxiomDashboardTileSpec,
  AxiomExplainResult,
  AxiomFieldMetaResponse,
  AxiomModelingSafeguards,
  AxiomPivotMeasureView,
} from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import { ModeAwareHeading, MissingDatasetNotice } from "@/components/product/ModeAware";
import { RecommendationsPanel } from "@/components/product/RecommendationsPanel";

const PALETTE = ["#2563eb", "#60a5fa", "#3b82f6", "#1d4ed8", "#93c5fd", "#0ea5e9", "#1e40af"];

const SECTION_ORDER: Array<{ key: string; label: string }> = [
  { key: "executive", label: "مؤشّرات الأداء التنفيذية" },
  { key: "trend", label: "الاتجاهات عبر الزمن" },
  { key: "segmentation", label: "التقسيم" },
  { key: "operational", label: "التشغيلي" },
  { key: "_other", label: "أخرى" },
];

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

function guidedKpiHint(label: string, kind: string | undefined, value: unknown): string {
  const friendly = label || "هذا المقياس";
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return `تعذّر حساب ${friendly} للنطاق الحالي.`;
  }
  if (kind === "currency") return `إجمالي ${friendly} عبر الصفوف ضمن النطاق.`;
  if (kind === "percent") return `نسبة ${friendly} عبر الصفوف ضمن النطاق.`;
  if (kind === "integer") return `عدد ${friendly} عبر الصفوف ضمن النطاق.`;
  return `القيمة المجمَّعة لـ ${friendly} عبر الصفوف ضمن النطاق.`;
}

export default function DashboardPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const datasetId = typeof window !== "undefined" ? getActiveDatasetId() : null;
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);
  const [dashboard, setDashboard] = useState<AxiomDashboard | null>(null);
  const [meta, setMeta] = useState<AxiomFieldMetaResponse | null>(null);
  const [safeguards, setSafeguards] = useState<AxiomModelingSafeguards | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Slicer state — applied page-wide, sent to /dashboard as query
  // params so every tile is filtered identically.
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [slicerValues, setSlicerValues] = useState<string[]>([]);
  const [slicerOptions, setSlicerOptions] = useState<string[]>([]);

  const [explain, setExplain] = useState<AxiomExplainResult | null>(null);
  const [explainLoading, setExplainLoading] = useState(false);

  const dateSlicer = useMemo(
    () => dashboard?.spec.slicers?.find((s) => s.kind === "date_range") || null,
    [dashboard]
  );
  const catSlicer = useMemo(
    () => dashboard?.spec.slicers?.find((s) => s.kind === "categorical") || null,
    [dashboard]
  );

  const reload = useCallback(async () => {
    if (!datasetId) return;
    setBusy(true); setError(null);
    try {
      const params = new URLSearchParams();
      if (dateFrom) params.set("date_from", dateFrom);
      if (dateTo) params.set("date_to", dateTo);
      if (catSlicer && slicerValues.length > 0) {
        params.set("slicer_column", catSlicer.column);
        params.set("slicer_values", slicerValues.join(","));
      }
      const qs = params.toString();
      const [d, s, m] = await Promise.all([
        api<AxiomDashboard>(`/api/bi/${datasetId}/dashboard${qs ? `?${qs}` : ""}`),
        api<AxiomModelingSafeguards>(`/api/bi/${datasetId}/modeling`),
        meta ? Promise.resolve(meta) : api<AxiomFieldMetaResponse>(`/api/bi/${datasetId}/field-meta`),
      ]);
      setDashboard(d);
      setSafeguards(s);
      if (!meta) setMeta(m);
    } catch (e) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }, [datasetId, dateFrom, dateTo, slicerValues, catSlicer, meta]);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    if (!datasetId) { setHasDataset(false); return; }
    setHasDataset(true);
    void reload();
  }, [datasetId, router, reload]);

  // Once we know the categorical slicer column, fetch its distinct
  // values from /pivot so the user gets a real dropdown.
  useEffect(() => {
    if (!datasetId || !catSlicer) return;
    let cancelled = false;
    api<{ rows: Array<{ _dims: Record<string, unknown> }> }>(
      "/api/bi/pivot",
      {
        method: "POST",
        json: {
          dataset_id: datasetId,
          rows: [catSlicer.column],
          cols: [],
          measures: [{ column: catSlicer.column, aggregation: "count" }],
          top_n: 50,
          drop_nulls_in_dims: true,
        } as unknown as Record<string, unknown>,
      },
    ).then((r) => {
      if (cancelled) return;
      const opts = r.rows
        .map((row) => row._dims?.[catSlicer.column])
        .filter((v) => v !== null && v !== undefined)
        .map(String);
      setSlicerOptions(opts);
    }).catch(() => { /* slicer is optional UX, don't surface */ });
    return () => { cancelled = true; };
  }, [datasetId, catSlicer]);

  const removeTile = useCallback(async (id: string) => {
    if (!datasetId || !dashboard) return;
    const next = dashboard.spec.tiles.filter((t) => t.id !== id);
    setDashboard({ ...dashboard, spec: { ...dashboard.spec, tiles: next } });
    try {
      await api(`/api/bi/${datasetId}/dashboard`, {
        method: "PUT",
        json: { tiles: next } as unknown as Record<string, unknown>,
      });
      void reload();
    } catch (e) { setError(errMessage(e)); }
  }, [datasetId, dashboard, reload]);

  const resetDashboard = useCallback(async () => {
    if (!datasetId) return;
    try {
      await api(`/api/bi/${datasetId}/dashboard`, { method: "DELETE" });
      void reload();
    } catch (e) { setError(errMessage(e)); }
  }, [datasetId, reload]);

  const drillThrough = useCallback((tile: AxiomDashboardTileSpec) => {
    if (!datasetId) return;
    const params = new URLSearchParams();
    const row = (tile.rows && tile.rows[0]) || "";
    const measure = tile.measures && tile.measures[0]?.column;
    const agg = tile.measures && tile.measures[0]?.aggregation;
    if (row) params.set("row", row);
    if (measure) params.set("measure", measure);
    if (agg) params.set("agg", String(agg));
    if (catSlicer && slicerValues.length === 1) {
      params.set("filter", `${catSlicer.column}=${slicerValues[0]}`);
    }
    router.push(`/app/pivot?${params.toString()}`);
  }, [datasetId, router, catSlicer, slicerValues]);

  const exportTileCsv = useCallback(async (tile: AxiomDashboardTileSpec) => {
    if (!datasetId) return;
    try {
      const token = getToken();
      const res = await fetch("/api/bi/export/csv", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          dataset_id: datasetId,
          rows: tile.rows || [],
          cols: tile.cols || [],
          measures: tile.measures || [],
          filters: tile.filters || [],
          date_grains: tile.date_grains || {},
          top_n: tile.top_n,
          include_grand_total: true,
        }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${tile.id}.csv`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch (e) { setError(errMessage(e)); }
  }, [datasetId]);

  const openExplain = useCallback(async (
    measure: AxiomPivotMeasureView,
    tile: AxiomDashboardTileSpec,
    coordinate: Record<string, unknown> = {},
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
          filters: [
            ...(tile.filters || []),
            ...(dashboard?.applied_slicers || []),
          ],
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
  }, [datasetId, dashboard]);

  const sectionedTiles = useMemo(() => {
    const tiles = dashboard?.tiles || [];
    const sections = new Map<string, AxiomDashboardTileResult[]>();
    for (const t of tiles) {
      const sec = t.tile.section || "_other";
      if (!sections.has(sec)) sections.set(sec, []);
      sections.get(sec)!.push(t);
    }
    return sections;
  }, [dashboard]);

  return (
    <div className="max-w-6xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="لوحة المعلومات"
        guidedTitle="بياناتك في لمحة"
        expertTitle="لوحة معلومات البيانات"
        guidedSubtitle="مؤشّرات واتجاهات وتقسيمات تلقائية. استخدم الفلاتر في الأعلى لتصفية كل البلاطات معًا."
        expertSubtitle="مواصفات بلاطات محفوظة فوق محرّك التجميع المركزي. تمرّ فلاتر الصفحة عبر نفس SUM/AVG المستخدَم في pivot وvisualize والمحادثة."
      />

      {hasDataset === false ? (
        <MissingDatasetNotice projectId={projectId} toolName="dashboard" />
      ) : (
        <>
          <div className="mt-6 flex items-center gap-2 flex-wrap" dir="rtl">
            <button onClick={reload} disabled={busy} className="btn btn-secondary text-[12px]" style={{ minHeight: 44 }}>
              {busy ? "جاري التحديث…" : "تحديث"}
            </button>
            {mode !== "guided" && (
              <button onClick={resetDashboard} className="btn text-[12px]" style={{ minHeight: 44 }}>
                إعادة الضبط للاقتراحات التلقائية
              </button>
            )}
          </div>

          {mode !== "guided" && dashboard && dashboard.spec.slicers && dashboard.spec.slicers.length > 0 && (
            <div className="mt-3 card flex items-center gap-3 flex-wrap" dir="rtl">
              <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)] ml-1">الفلاتر</div>
              {dateSlicer && (
                <>
                  <label className="text-[12px] flex items-center gap-1">
                    <span className="text-[var(--text-muted)]">{dateSlicer.column} من</span>
                    <input
                      type="date" value={dateFrom}
                      onChange={(e) => setDateFrom(e.target.value)}
                      className="px-2 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[12px]"
                      style={{ minHeight: 32 }}
                    />
                  </label>
                  <label className="text-[12px] flex items-center gap-1">
                    <span className="text-[var(--text-muted)]">إلى</span>
                    <input
                      type="date" value={dateTo}
                      onChange={(e) => setDateTo(e.target.value)}
                      className="px-2 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[12px]"
                      style={{ minHeight: 32 }}
                    />
                  </label>
                </>
              )}
              {catSlicer && slicerOptions.length > 0 && (
                <label className="text-[12px] flex items-center gap-1">
                  <span className="text-[var(--text-muted)]">{catSlicer.column}</span>
                  <select
                    multiple
                    value={slicerValues}
                    onChange={(e) => {
                      const opts = Array.from(e.target.selectedOptions).map((o) => o.value);
                      setSlicerValues(opts);
                    }}
                    className="px-2 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[12px] min-w-[160px]"
                    size={Math.min(4, slicerOptions.length + 1)}
                  >
                    {slicerOptions.map((v) => <option key={v} value={v}>{v}</option>)}
                  </select>
                </label>
              )}
              {(dateFrom || dateTo || slicerValues.length > 0) && (
                <button
                  className="text-[12px] text-[var(--text-muted)] hover:text-red-500 mr-auto"
                  style={{ minHeight: 32 }}
                  onClick={() => { setDateFrom(""); setDateTo(""); setSlicerValues([]); }}
                >
                  مسح الفلاتر
                </button>
              )}
            </div>
          )}

          {error && <div className="text-sm text-red-600 mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2" role="alert" dir="rtl">{error}</div>}

          {mode !== "guided" && safeguards && (safeguards.fanout.length > 0 || !safeguards.grain.is_unique) && (
            <div className="mt-3 card border-amber-500/60" dir="rtl">
              <div className="text-[12px] font-semibold text-amber-600 mb-1">
                تنبيهات النمذجة
              </div>
              <ul className="text-[12px] space-y-0.5 list-disc list-inside text-amber-700">
                {!safeguards.grain.is_unique && (
                  <li>
                    تعذّر إيجاد دقّة فريدة لهذا الجدول — يحتوي على {" "}
                    {safeguards.grain.duplicate_count.toLocaleString()} صفًا مكرّرًا.
                    قد تتسبّب التجميعات بعدّ مزدوج بدون مفتاح أساسي نظيف.
                  </li>
                )}
                {safeguards.grain.is_unique && safeguards.grain.keys.length > 0 && (
                  <li className="text-[var(--text-muted)]">
                    الدقّة: <span className="font-mono">{safeguards.grain.keys.join(" + ")}</span>
                  </li>
                )}
                {safeguards.fanout.map((f, i) => <li key={i}>{f.warning}</li>)}
              </ul>
            </div>
          )}

          {SECTION_ORDER.map(({ key, label }) => {
            const tiles = sectionedTiles.get(key);
            if (!tiles || tiles.length === 0) return null;
            const isKpi = tiles[0].tile.kind === "kpi";
            return (
              <div key={key} className="mt-5">
                <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {label}
                </div>
                <div className={isKpi
                  ? "grid grid-cols-2 md:grid-cols-4 gap-3"
                  : "grid grid-cols-1 md:grid-cols-2 gap-4"}>
                  {tiles.map((tile) => (
                    isKpi ? (
                      <KpiCard
                        key={tile.tile.id}
                        tile={tile}
                        mode={mode}
                        onRemove={() => removeTile(tile.tile.id)}
                        onExplain={(m) => openExplain(m, tile.tile, {})}
                      />
                    ) : (
                      <ChartTile
                        key={tile.tile.id}
                        tile={tile}
                        mode={mode}
                        onRemove={() => removeTile(tile.tile.id)}
                        onDrillThrough={() => drillThrough(tile.tile)}
                        onExport={() => exportTileCsv(tile.tile)}
                        onExplain={(m) => openExplain(m, tile.tile, {})}
                      />
                    )
                  ))}
                </div>
              </div>
            );
          })}

          {dashboard && (dashboard.tiles || []).length === 0 && (
            <div className="mt-6 card text-[12px] text-[var(--text-muted)] text-center" role="status" dir="rtl">
              <div className="text-2xl mb-2" aria-hidden="true">📊</div>
              لا توجد بلاطات بعد. استخدم صفحة{" "}
              <a href="/app/pivot" className="text-[var(--accent)] hover:underline">المحور</a>
              {" "}أو{" "}
              <a href="/app/visualize" className="text-[var(--accent)] hover:underline">التصوّر</a>
              {" "}للبناء، أو انقر &quot;إعادة الضبط&quot; لاقتراح بلاطات تلقائيًا.
            </div>
          )}

          <RecommendationsPanel projectId={projectId} />
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

function KpiCard({
  tile, mode, onRemove, onExplain,
}: {
  tile: AxiomDashboardTileResult;
  mode: "guided" | "expert";
  onRemove: () => void;
  onExplain: (m: AxiomPivotMeasureView) => void;
}) {
  const m = tile.measures[0];
  const v = m ? tile.grand_total[m.key] : null;
  return (
    <div className="card group relative">
      {mode !== "guided" && (
        <button
          onClick={onRemove}
          className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-[var(--text-muted)] hover:text-red-500 text-xs"
          aria-label="إزالة البلاطة"
        >×</button>
      )}
      <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)]">
        {tile.tile.title}
      </div>
      <div className="text-2xl font-semibold mt-1 tabular-nums">
        {m ? fmtValue(v, m.format_kind, m.precision) : "—"}
      </div>
      {m && (
        <div className="text-[12px] text-[var(--text-muted)] mt-0.5">
          {m.label}
        </div>
      )}
      {mode === "guided" && m && (
        <div className="mt-2 text-[12px] leading-snug text-[var(--text-muted)]" dir="rtl">
          {guidedKpiHint(m.label || tile.tile.title, m.format_kind, v)}
        </div>
      )}
      {tile.warnings && tile.warnings.length > 0 && (
        <div className="mt-1 text-[12px] text-amber-600" role="status">{tile.warnings[0]}</div>
      )}
      {mode !== "guided" && m && (
        <>
          <button
            onClick={() => onExplain(m)}
            className="absolute bottom-1 right-2 text-[12px] text-[var(--text-muted)] hover:text-[var(--accent)] underline"
          >
            تفسير
          </button>
          <details className="mt-2 text-[12px] text-[var(--text-muted)]">
            <summary className="cursor-pointer hover:text-[var(--accent)]">عرض JSON</summary>
            <pre className="mt-1 overflow-auto max-h-48 whitespace-pre-wrap break-all bg-[var(--surface)]/60 rounded p-2 text-[10px]">
              {JSON.stringify({ spec: tile.tile, value: v, measure: m }, null, 2)}
            </pre>
          </details>
        </>
      )}
    </div>
  );
}

function ChartTile({
  tile, mode, onRemove, onDrillThrough, onExport, onExplain,
}: {
  tile: AxiomDashboardTileResult;
  mode: "guided" | "expert";
  onRemove: () => void;
  onDrillThrough: () => void;
  onExport: () => void;
  onExplain: (m: AxiomPivotMeasureView) => void;
}) {
  const m = tile.measures[0];
  const rowKey = tile.row_dims[0];
  const data = (tile.rows || [])
    .filter((r) => r._subtotal_level === undefined)
    .map((r) => ({
      __label: String(r._dims?.[rowKey] ?? "—"),
      value: m ? Number(r[m.key] ?? 0) : 0,
    }));
  const kind = tile.tile.kind;

  return (
    <div className="card group relative">
      {mode !== "guided" && (
        <div className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 flex items-center gap-1.5">
          {m && (
            <button
              onClick={() => onExplain(m)}
              className="text-[12px] text-[var(--text-muted)] hover:text-[var(--accent)]"
              title="تفسير هذه البلاطة"
            >
              تفسير
            </button>
          )}
          <button
            onClick={onExport}
            className="text-[12px] text-[var(--text-muted)] hover:text-[var(--accent)]"
            title="تصدير CSV"
          >
            CSV
          </button>
          <button
            onClick={onDrillThrough}
            className="text-[12px] text-[var(--text-muted)] hover:text-[var(--accent)]"
            title="فتح في المحور"
          >
            تفصيل →
          </button>
          <button
            onClick={onRemove}
            className="text-[var(--text-muted)] hover:text-red-500 text-xs"
            aria-label="إزالة البلاطة"
          >×</button>
        </div>
      )}
      <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
        {tile.tile.title}
      </div>
      {tile.error ? (
        <div className="text-[12px] text-red-600" role="alert">{tile.error}</div>
      ) : kind === "table" ? (
        <div className="overflow-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest border-b border-[var(--border)]">
                <th className="text-left px-2 py-1">{rowKey}</th>
                {m && <th className="text-right px-2 py-1">{m.label}</th>}
              </tr>
            </thead>
            <tbody>
              {data.map((r, i) => (
                <tr key={i} className="border-b border-[var(--border)]/40">
                  <td className="px-2 py-1 font-mono">{r.__label}</td>
                  {m && <td className="px-2 py-1 text-right tabular-nums">{fmtValue(r.value, m.format_kind, m.precision)}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : kind === "line" ? (
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="__label" />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="value" stroke={PALETTE[0]} dot={false} name={m?.label || "Value"} />
          </LineChart>
        </ResponsiveContainer>
      ) : (
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="__label" />
            <YAxis />
            <Tooltip />
            <Legend />
            <Bar dataKey="value" fill={PALETTE[0]} name={m?.label || "Value"} />
          </BarChart>
        </ResponsiveContainer>
      )}
      {tile.warnings && tile.warnings.length > 0 && (
        <ul className="mt-2 text-[10px] text-amber-600 list-disc list-inside space-y-0.5">
          {tile.warnings.slice(0, 3).map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
      {mode !== "guided" && (
        <details className="mt-2 text-[12px] text-[var(--text-muted)]">
          <summary className="cursor-pointer hover:text-[var(--accent)]">عرض JSON</summary>
          <pre className="mt-1 overflow-auto max-h-48 whitespace-pre-wrap break-all bg-[var(--surface)]/60 rounded p-2 text-[10px]">
            {JSON.stringify({ spec: tile.tile, measures: tile.measures, row_dims: tile.row_dims, sample: data.slice(0, 5) }, null, 2)}
          </pre>
        </details>
      )}
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
        <div className="flex items-center justify-between mb-3" dir="rtl">
          <div>
            <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)]">تفسير</div>
            <div className="text-lg font-semibold">{m.label || "مقياس"}</div>
          </div>
          <button onClick={onClose} className="text-xl text-[var(--text-muted)] hover:text-[var(--text)] inline-flex items-center justify-center" style={{ minHeight: 44, minWidth: 44 }} aria-label="إغلاق">×</button>
        </div>
        {loading ? (
          <div className="text-[12px] text-[var(--text-muted)] inline-flex items-center gap-2" role="status" aria-live="polite" dir="rtl">
            <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]" aria-hidden="true" />
            جاري الحساب…
          </div>
        ) : (
          <div className="space-y-3 text-[12px]" dir="rtl">
            <div className="text-2xl font-semibold tabular-nums">
              {fmtValue(payload.value, m.format_kind, m.precision)}
            </div>
            {payload.formula && (
              <div>
                <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)] mb-1">الصيغة</div>
                <div className="font-mono text-[12px] bg-[var(--surface)] rounded px-2 py-1.5 break-all" dir="ltr">{payload.formula}</div>
              </div>
            )}
            {payload.filter_summary && payload.filter_summary.length > 0 && (
              <div>
                <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)] mb-1">الفلاتر النشِطة</div>
                <ul className="space-y-0.5">
                  {payload.filter_summary.map((f, i) => (
                    <li key={i} className="font-mono text-[12px]" dir="ltr">{f}</li>
                  ))}
                </ul>
              </div>
            )}
            <div className="text-[12px] text-[var(--text-muted)]">
              ساهم {payload.contributing_rows.toLocaleString()} من أصل {payload.total_rows.toLocaleString()} صف.
            </div>
            {payload.warnings && payload.warnings.length > 0 && (
              <ul className="text-[12px] text-amber-600 list-disc list-inside space-y-0.5">
                {payload.warnings.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            )}
            {payload.sample_rows && payload.sample_rows.length > 0 && (
              <div>
                <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)] mb-1">عيّنة من الصفوف المساهِمة</div>
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
