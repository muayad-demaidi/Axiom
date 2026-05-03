"use client";
/**
 * Result card for the guided predictive flow — Task #212.
 *
 * Renders the payload returned by `POST /api/predict/guided/run`:
 *   • Arabic confidence gauge (0–100, color-banded) with sub-scores
 *   • Key formatted numbers (already pre-formatted as strings)
 *   • Inline forecast sparkline (time-series flow only)
 *   • Top driver bars (driver flow)
 *   • Arabic narrative: context paragraph, conditional sentence
 *     ("if … ← we predict …") and 2–3 recommendations
 *
 * Numbers are NEVER re-formatted from raw values here — we always
 * use the strings returned in `formatted_numbers` so what the model
 * was instructed to quote is what the user sees.
 */
export type GuidedPredictionResult = {
  flow: "guided";
  target: string;
  time_column: string | null;
  is_timeseries: boolean;
  horizon_periods: number;
  answers: Record<string, unknown>;
  model: {
    engine: string;
    history?: { ds: string; y: number }[];
    forecast?: { ds: string; yhat: number; lower: number; upper: number }[];
    metrics?: Record<string, number | null>;
    feature_importance?: { feature: string; importance: number }[];
  };
  feature_importance: { feature: string; importance: number; coefficient?: number }[];
  formatted_numbers: Record<string, string>;
  confidence: {
    score: number;
    band: "low" | "medium" | "high";
    weights: Record<string, number>;
    sub_scores: Record<string, number>;
  };
  narrative: {
    context: string;
    conditional: string;
    recommendations: string[];
  };
};

const SUB_SCORE_LABELS_AR: Record<string, string> = {
  data_volume: "Data volume",
  data_quality: "Data quality",
  signal_strength: "Signal strength",
  time_coverage: "Time coverage",
};

export function GuidedPredictionCard({
  result,
  onRestart,
}: {
  result: GuidedPredictionResult;
  onRestart?: () => void;
}) {
  const fnums = result.formatted_numbers || {};
  return (
    <div dir="rtl" className="space-y-4 text-right">
      <div className="flex items-start gap-4">
        <ConfidenceGauge
          score={result.confidence.score}
          band={result.confidence.band}
        />
        <div className="flex-1 min-w-0">
          <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
            Guided forecast · {result.is_timeseries ? "time series" : "factor model"}
          </div>
          <div className="text-base font-semibold truncate" title={result.target}>
            {result.target}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-2">
            {Object.entries(fnums).slice(0, 4).map(([k, v]) => (
              <div
                key={k}
                className="rounded-md border border-[var(--border)]/60 bg-[var(--surface)] px-2 py-1"
              >
                <div className="text-[10px] text-[var(--text-muted)]">
                  {KEY_LABELS_AR[k] ?? k}
                </div>
                <div className="text-xs font-mono tabular-nums">{v}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <SubScores scores={result.confidence.sub_scores} />

      {result.is_timeseries && result.model.forecast && result.model.history && (
        <ForecastSparkline
          history={result.model.history}
          forecast={result.model.forecast}
        />
      )}

      {!result.is_timeseries && result.feature_importance.length > 0 && (
        <DriverImportance features={result.feature_importance} />
      )}

      <NarrativeBlock narrative={result.narrative} />

      {onRestart && (
        <div className="flex justify-end">
          <button
            onClick={onRestart}
            className="text-[11px] text-[var(--text-muted)] hover:text-[var(--accent)] underline"
          >
            Run new forecast
          </button>
        </div>
      )}
    </div>
  );
}

const KEY_LABELS_AR: Record<string, string> = {
  next_period_forecast: "Next forecast",
  forecast_average: "Average forecast",
  lower_band: "Lower bound",
  upper_band: "Upper bound",
  horizon_periods: "Horizon (periods)",
  baseline: "Baseline forecast",
  r2: "R² goodness of fit",
  mae: "Mean absolute error",
};

export function ConfidenceGauge({
  score,
  band,
  size = 88,
}: {
  score: number;
  band: "low" | "medium" | "high";
  size?: number;
}) {
  const clamped = Math.max(0, Math.min(100, score));
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (clamped / 100) * circumference;
  const color =
    band === "high" ? "#22c55e"
      : band === "medium" ? "#f59e0b"
      : "#ef4444";
  const bandLabel =
    band === "high" ? "high" : band === "medium" ? "medium" : "low";
  return (
    <div
      className="relative shrink-0 flex flex-col items-center"
      style={{ width: size }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke="var(--border)"
          strokeWidth={6}
          fill="none"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          stroke={color}
          strokeWidth={6}
          fill="none"
          strokeDasharray={`${dash} ${circumference - dash}`}
          strokeDashoffset={circumference / 4}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
        <text
          x="50%"
          y="48%"
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-[var(--text)]"
          style={{ fontSize: size * 0.24, fontWeight: 700 }}
        >
          {Math.round(clamped)}
        </text>
        <text
          x="50%"
          y="68%"
          textAnchor="middle"
          dominantBaseline="middle"
          className="fill-[var(--text-muted)]"
          style={{ fontSize: size * 0.10 }}
        >
          /100
        </text>
      </svg>
      <div
        className="text-[10px] mt-1 font-mono"
        style={{ color }}
      >
        Confidence {bandLabel}
      </div>
    </div>
  );
}

function SubScores({ scores }: { scores: Record<string, number> }) {
  const entries = Object.entries(scores);
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-2">
      {entries.map(([k, v]) => {
        const w = Math.max(0, Math.min(100, Number(v) || 0));
        return (
          <div
            key={k}
            className="rounded-md border border-[var(--border)]/60 bg-[var(--surface)] p-2"
          >
            <div className="flex items-center justify-between mb-1">
              <span className="text-[11px] text-[var(--text-muted)]">
                {SUB_SCORE_LABELS_AR[k] ?? k}
              </span>
              <span className="text-[11px] font-mono tabular-nums">
                {Math.round(w)}
              </span>
            </div>
            <div className="h-1 bg-[var(--border)]/40 rounded">
              <div
                className="h-full bg-[var(--accent)] rounded"
                style={{ width: `${w}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ForecastSparkline({
  history,
  forecast,
  width = 360,
  height = 120,
}: {
  history: { ds: string; y: number }[];
  forecast: { ds: string; yhat: number; lower: number; upper: number }[];
  width?: number;
  height?: number;
}) {
  const all = [
    ...history.map((p) => ({ x: new Date(p.ds).getTime(), y: p.y, kind: "h" as const })),
    ...forecast.map((p) => ({ x: new Date(p.ds).getTime(), y: p.yhat, kind: "f" as const })),
  ];
  if (all.length < 2) return null;
  const xs = all.map((p) => p.x);
  const ys = [
    ...history.map((p) => p.y),
    ...forecast.flatMap((p) => [p.yhat, p.lower, p.upper]),
  ];
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const yMin = Math.min(...ys);
  const yMax = Math.max(...ys);
  const pad = 8;
  const sx = (x: number) =>
    pad + ((x - xMin) / (xMax - xMin || 1)) * (width - 2 * pad);
  const sy = (y: number) =>
    height - pad - ((y - yMin) / (yMax - yMin || 1)) * (height - 2 * pad);

  const histPath = history
    .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(new Date(p.ds).getTime())} ${sy(p.y)}`)
    .join(" ");
  const forecastPath = forecast
    .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(new Date(p.ds).getTime())} ${sy(p.yhat)}`)
    .join(" ");
  const bandTop = forecast.map((p) => `${sx(new Date(p.ds).getTime())},${sy(p.upper)}`);
  const bandBot = [...forecast].reverse().map((p) => `${sx(new Date(p.ds).getTime())},${sy(p.lower)}`);
  const bandPoly = [...bandTop, ...bandBot].join(" ");
  return (
    <div className="border border-[var(--border)]/60 rounded-md p-2 bg-[var(--surface)]">
      <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)] mb-1">
        History & forecast
      </div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Forecast sparkline">
        <polygon points={bandPoly} fill="var(--accent)" fillOpacity={0.12} />
        <path d={histPath} fill="none" stroke="var(--text)" strokeWidth={1.4} />
        <path d={forecastPath} fill="none" stroke="var(--accent)" strokeWidth={1.6} strokeDasharray="4 3" />
      </svg>
    </div>
  );
}

function DriverImportance({
  features,
}: {
  features: { feature: string; importance: number }[];
}) {
  const max = Math.max(...features.map((f) => f.importance), 1e-9);
  return (
    <div className="border border-[var(--border)]/60 rounded-md p-2 bg-[var(--surface)] space-y-1.5">
      <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
        Driver importance
      </div>
      {features.slice(0, 5).map((f) => (
        <div key={f.feature}>
          <div className="flex items-center justify-between text-[11px] mb-0.5">
            <span className="truncate">{f.feature}</span>
            <span className="font-mono tabular-nums text-[var(--text-muted)]">
              {(f.importance / max * 100).toFixed(0)}%
            </span>
          </div>
          <div className="h-1 bg-[var(--border)]/40 rounded">
            <div
              className="h-full bg-[var(--accent)] rounded"
              style={{ width: `${Math.max(2, (f.importance / max) * 100)}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function NarrativeBlock({
  narrative,
}: {
  narrative: GuidedPredictionResult["narrative"];
}) {
  return (
    <div className="space-y-2 leading-relaxed">
      <div className="text-sm text-[var(--text)]">{narrative.context}</div>
      <div className="rounded-md border border-[var(--accent)]/40 bg-[var(--accent)]/5 px-3 py-2 text-sm">
        {narrative.conditional}
      </div>
      {narrative.recommendations.length > 0 && (
        <ul className="text-xs space-y-1 list-disc pr-5">
          {narrative.recommendations.map((r, i) => (
            <li key={i}>{r}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
