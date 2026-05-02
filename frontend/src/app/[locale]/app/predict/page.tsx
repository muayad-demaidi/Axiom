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
  MissingDatasetNotice,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

type ForecastPoint = { period?: number; forecast?: number; lower?: number; upper?: number } & Record<string, number | string>;
type FeatureImportance = Record<string, number | string> & {
  shap_top?: Record<string, number>;
  note?: string;
};
type ExpertPayload = {
  model_used?: string;
  family?: string;
  feature_importance?: FeatureImportance;
} & Record<string, unknown>;
type ForecastResponse = {
  column: string;
  mode?: string;
  forecast: ForecastPoint[] | number[];
  expert?: ExpertPayload;
  guided?: Record<string, unknown>;
};

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw = (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
}

function ShapTopFeatures({ expert }: { expert: ExpertPayload }) {
  const fi = expert.feature_importance;
  if (!fi) return null;
  const shap = fi.shap_top;
  if (shap && Object.keys(shap).length > 0) {
    const entries = Object.entries(shap)
      .map(([name, value]) => [name, Number(value)] as [string, number])
      .sort((a, b) => b[1] - a[1]);
    const max = Math.max(...entries.map(([, v]) => v), 1e-9);
    return (
      <div className="space-y-2" dir="rtl">
        <div className="flex flex-row-reverse items-baseline justify-between">
          <h3 className="text-sm font-medium">أهم تفسيرات المتغيّرات (SHAP)</h3>
          <span className="text-[12px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
            mean |SHAP|
          </span>
        </div>
        <p className="text-[12px] text-[var(--text-muted)]">
          إسهامات المتغيّرات في توقّعات النموذج {expert.model_used ?? "المختار"}.
          كلما زاد الشريط زاد تأثير المتغيّر على التوقّعات في المتوسّط.
        </p>
        <ul className="space-y-1.5">
          {entries.map(([name, value]) => {
            const pct = Math.max(2, Math.round((value / max) * 100));
            return (
              <li key={name} className="text-xs">
                <div className="flex justify-between gap-3">
                  <span className="font-mono truncate">{name}</span>
                  <span className="font-mono text-[var(--text-muted)]">
                    {value.toLocaleString(undefined, { maximumFractionDigits: 5 })}
                  </span>
                </div>
                <div className="mt-1 h-1.5 rounded bg-[var(--surface-2,rgba(0,0,0,0.06))] overflow-hidden">
                  <div
                    className="h-full rounded bg-[var(--accent,#6366f1)]"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    );
  }
  if (typeof fi.note === "string" && fi.note.toLowerCase().includes("shap")) {
    return (
      <div className="text-[12px] text-[var(--text-muted)]" dir="rtl">
        <h3 className="text-sm font-medium text-[var(--text)] mb-1">
          أهم تفسيرات المتغيّرات (SHAP)
        </h3>
        <p>{fi.note}</p>
      </div>
    );
  }
  return null;
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
    <div className="space-y-3" dir="rtl">
      <div className="text-sm">
        خلال الـ <strong>{flat.length}</strong> فترة القادمة يبلغ متوسّط التوقّع لـ
        <strong> {data.column} </strong>
        <strong>{avg.toLocaleString(undefined, { maximumFractionDigits: 2 })}</strong>
        {flat.length > 1 && (
          <> مع ذروة في الفترة {peakIdx + 1} ({flat[peakIdx].toLocaleString(undefined, { maximumFractionDigits: 2 })}).</>
        )}
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-right text-[12px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
            <th className="py-1">الفترة</th>
            <th className="py-1">التوقّع</th>
          </tr>
        </thead>
        <tbody>
          {flat.map((v, i) => (
            <tr key={i} className="border-t border-dashed border-[var(--border)]">
              <td className="py-1.5 font-mono text-[12px]">{i + 1}</td>
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
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setHasDataset(false); return; }
    setHasDataset(true);
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
    <div className="space-y-3" dir="rtl">
      <label className="block text-sm">
        العمود
        <select value={column} onChange={(e) => setColumn(e.target.value)}
          className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" style={{ minHeight: 44 }}>
          {columns.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      </label>
      <label className="block text-sm">
        عدد الفترات المتوقَّعة
        <input type="number" min={1} max={24} value={periods}
          onChange={(e) => setPeriods(Number(e.target.value))}
          className="block mt-1 w-32 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" style={{ minHeight: 44 }} />
      </label>
      <button className="btn btn-primary" style={{ minHeight: 44 }} onClick={() => run()} disabled={busy || !column}>
        {busy ? "جاري التنبّؤ…" : "ابدأ التنبّؤ"}
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

      {hasDataset === false ? (
        <MissingDatasetNotice
          projectId={projectId}
          toolName="forecasts"
          guidedHint="ارفع ملف CSV أو Excel يحتوي عمودًا رقميًا وسنتنبّأ به."
        />
      ) : mode === "guided" ? (
        <>
          <div className="card mt-6 space-y-3" dir="rtl">
            <label className="block text-sm">
              ماذا تريد أن نتنبّأ به؟
              <select value={column} onChange={(e) => setColumn(e.target.value)}
                className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" style={{ minHeight: 44 }}>
                {columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
            <div className="flex flex-wrap gap-2 pt-2">
              <button className="btn btn-primary" style={{ minHeight: 44 }} onClick={() => run(3)} disabled={busy || !column}>
                {busy ? "جاري التنبّؤ…" : "تنبّأ بـ 3 فترات قادمة"}
              </button>
              <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={() => run(6)} disabled={busy || !column}>
                6 فترات قادمة
              </button>
              <button className="btn btn-ghost" style={{ minHeight: 44 }} onClick={() => run(12)} disabled={busy || !column}>
                12 فترة قادمة
              </button>
            </div>
          </div>
          <AdvancedExpander projectId={projectId} hint="اختر الأفق الزمني والعمود بدقّة">
            {expertControls}
          </AdvancedExpander>
        </>
      ) : (
        <div className="card mt-6">{expertControls}</div>
      )}

      {error && (
        <div
          className="text-sm text-red-600 mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2"
          role="alert"
          dir="rtl"
        >
          {error}
        </div>
      )}
      {forecast && (
        <div className="card mt-4 space-y-4" dir="rtl">
          {mode === "guided" ? (
            <>
              <GuidedForecast data={forecast} />
              <TechnicalDetails projectId={projectId} label="عرض مخرجات النموذج">
                {forecast.expert ? <ShapTopFeatures expert={forecast.expert} /> : null}
                <pre className="mt-3 text-[11px] overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(forecast, null, 2)}</pre>
              </TechnicalDetails>
            </>
          ) : (
            <>
              {forecast.expert ? <ShapTopFeatures expert={forecast.expert} /> : null}
              <pre className="text-xs overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(forecast, null, 2)}</pre>
            </>
          )}
        </div>
      )}
    </div>
  );
}
