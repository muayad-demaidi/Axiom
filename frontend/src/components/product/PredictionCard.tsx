"use client";
/**
 * Prediction artifact card.
 *
 * The backend `predict_column` tool persists a LinearRegression as
 * { intercept, feature_importance: [{feature, coefficient, importance}],
 *   feature_ranges: { f: {min, max, mean} }, metrics: {r2, mae, ...} }.
 * That payload is enough to power a what-if slider client-side: the
 * predicted value is `intercept + Σ coef_i × x_i` so we can recompute
 * it instantly as the user drags.
 */
import { useMemo, useState } from "react";
import { InteractiveTable } from "./InteractiveTable";
import { Gauge, bandFor } from "@/components/ui/Gauge";

type Importance = {
  feature: string;
  coefficient: number;
  importance: number;
};

type Range = { min: number; max: number; mean: number };

export type PredictionResult = {
  target: string;
  model: string;
  metrics: { r2: number; mae: number; n_train?: number; n_test?: number };
  intercept: number;
  feature_importance: Importance[];
  feature_ranges: Record<string, Range>;
  // Optional: shipped by newer prediction artifacts so the report can
  // synthesise deterministic ±10/±25 % what-if rows.
  feature_means?: Record<string, number>;
  linear_coefs?: Record<string, number>;
  baseline_prediction?: number;
};

export function PredictionCard({
  title,
  result,
}: {
  title: string;
  result: PredictionResult;
}) {
  const sliderFeatures = (result.feature_importance ?? []).slice(0, 5);
  const [values, setValues] = useState<Record<string, number>>(() => {
    const out: Record<string, number> = {};
    for (const f of sliderFeatures) {
      out[f.feature] = result.feature_ranges?.[f.feature]?.mean ?? 0;
    }
    return out;
  });

  const predicted = useMemo(() => {
    let v = result.intercept || 0;
    for (const f of result.feature_importance || []) {
      const x = values[f.feature];
      if (typeof x === "number") {
        v += f.coefficient * x;
      } else {
        v += f.coefficient * (result.feature_ranges?.[f.feature]?.mean ?? 0);
      }
    }
    return v;
  }, [values, result]);

  // Confidence score derived from R²; clamped to 0-100 for the gauge.
  const r2 = Number(result.metrics?.r2 ?? 0);
  const confidence = Math.max(0, Math.min(100, Math.round(r2 * 100)));
  const band = bandFor(confidence);
  const confidenceCopy =
    band === "high"
      ? "ثقة مرتفعة في التنبؤ."
      : band === "medium"
      ? "ثقة متوسطة — راجع النتائج قبل الاعتماد عليها."
      : "ثقة منخفضة — لا يُنصح بالاعتماد على هذا التنبؤ كما هو.";

  return (
    <div dir="rtl" className="space-y-3 text-right">
      <div className="flex flex-row-reverse items-baseline justify-between gap-3">
        <div className="font-semibold text-sm">{title}</div>
        <div className="text-[12px] text-[var(--text-muted)] font-mono">
          R² {fmt(result.metrics?.r2)} · MAE {fmt(result.metrics?.mae)} · {result.model}
        </div>
      </div>

      <div className="flex flex-row-reverse items-start gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface-alt)]/40 p-3">
        <Gauge
          score={confidence}
          size={88}
          label="ثقة النموذج"
          description={confidenceCopy}
        />
        <div className="flex-1 text-[12px] leading-relaxed text-[var(--text-muted)]">
          نُحسب درجة الثقة من جودة المطابقة (R²). تقاس على مقياس 0–100،
          حيث ≥ 70 ثقة مرتفعة، 40–69 متوسطة، وأقل من 40 منخفضة.
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <section className="border border-[var(--border)] rounded p-3 bg-[var(--surface)]">
          <div className="font-mono text-[12px] tracking-widest uppercase text-[var(--text-muted)] mb-2">
            أهم العوامل المؤثرة
          </div>
          <ul className="space-y-1.5">
            {(result.feature_importance ?? []).slice(0, 8).map((f) => {
              const max = Math.max(...(result.feature_importance ?? []).map((g) => g.importance), 1e-9);
              const w = Math.max(2, Math.round((f.importance / max) * 100));
              return (
                <li key={f.feature} className="text-[12px]">
                  <div className="flex flex-row-reverse items-baseline justify-between">
                    <span className="truncate">{f.feature}</span>
                    <span className="font-mono text-[12px] text-[var(--text-muted)]">
                      {f.coefficient >= 0 ? "+" : ""}
                      {fmt(f.coefficient)}
                    </span>
                  </div>
                  <div className="h-1.5 bg-[var(--surface-alt)] rounded overflow-hidden">
                    <div
                      className="h-full bg-[var(--accent)]"
                      style={{ width: `${w}%` }}
                    />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        <section className="border border-[var(--border)] rounded p-3 bg-[var(--surface)]">
          <div className="font-mono text-[12px] tracking-widest uppercase text-[var(--text-muted)] mb-2">
            كل العوامل (ابحث / رتّب)
          </div>
          <InteractiveTable
            columns={[
              { name: "feature", dtype: "string" },
              { name: "coefficient", dtype: "float" },
              { name: "importance", dtype: "float" },
            ]}
            rows={(result.feature_importance ?? []).map((f) => ({
              feature: f.feature,
              coefficient: Number(f.coefficient.toFixed(5)),
              importance: Number(f.importance.toFixed(5)),
            }))}
            maxHeight={180}
          />
        </section>

        <section className="border border-[var(--border)] rounded p-3 bg-[var(--surface)] sm:col-span-2">
          <div className="font-mono text-[12px] tracking-widest uppercase text-[var(--text-muted)] mb-2">
            ماذا لو · توقّع {result.target}
          </div>
          <div className="text-2xl font-semibold mb-2 text-[var(--accent)]" aria-live="polite">
            {fmt(predicted)}
          </div>
          {sliderFeatures.length === 0 && (
            <div className="text-[12px] text-[var(--text-muted)]">
              لا توجد متغيرات قابلة للضبط.
            </div>
          )}
          <div className="space-y-2">
            {sliderFeatures.map((f) => {
              const r = result.feature_ranges?.[f.feature];
              if (!r) return null;
              const v = values[f.feature];
              const span = r.max - r.min || 1;
              const step = span / 100;
              const sliderId = `pred-${result.target}-${f.feature}`;
              return (
                <div key={f.feature}>
                  <div className="flex flex-row-reverse items-baseline justify-between text-[12px]">
                    <label htmlFor={sliderId} className="truncate">{f.feature}</label>
                    <span className="font-mono">{fmt(v)}</span>
                  </div>
                  <input
                    id={sliderId}
                    type="range"
                    min={r.min}
                    max={r.max}
                    step={step}
                    value={v}
                    onChange={(e) =>
                      setValues((cur) => ({ ...cur, [f.feature]: Number(e.target.value) }))
                    }
                    className="w-full accent-[var(--accent)]"
                    aria-label={`ضبط ${f.feature}`}
                  />
                  <div className="flex flex-row-reverse justify-between text-[12px] text-[var(--text-muted)] font-mono">
                    <span>{fmt(r.min)}</span>
                    <span>μ {fmt(r.mean)}</span>
                    <span>{fmt(r.max)}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      </div>
    </div>
  );
}

function fmt(v: number | undefined | null): string {
  if (v == null || !Number.isFinite(v)) return "—";
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
}
