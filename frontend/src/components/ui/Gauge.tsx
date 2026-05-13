"use client";

export type GaugeBand = "high" | "medium" | "low";

export type GaugeProps = {
  /** 0-100 */
  score: number;
  size?: number;
  label?: string;
  description?: string;
  factors?: { label: string; value: number }[];
  bandLabels?: Partial<Record<GaugeBand, string>>;
};

export function bandFor(score: number): GaugeBand {
  if (score >= 70) return "high";
  if (score >= 40) return "medium";
  return "low";
}

const BAND_COLOR: Record<GaugeBand, string> = {
  high: "#22c55e",
  medium: "#f59e0b",
  low: "#ef4444",
};

const DEFAULT_BAND_LABELS: Record<GaugeBand, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

export function Gauge({
  score,
  size = 88,
  label,
  description,
  factors,
  bandLabels,
}: GaugeProps) {
  const clamped = Math.max(0, Math.min(100, score));
  const band = bandFor(clamped);
  const radius = (size - 12) / 2;
  const circumference = 2 * Math.PI * radius;
  const dash = (clamped / 100) * circumference;
  const color = BAND_COLOR[band];
  const bandLabel = bandLabels?.[band] ?? DEFAULT_BAND_LABELS[band];

  return (
    <div
      className="flex flex-col items-center gap-1 shrink-0"
      style={{ width: size }}
      role="img"
      aria-label={`${label ?? "Confidence"}: ${Math.round(clamped)} of 100, ${bandLabel}`}
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
          style={{ fontSize: size * 0.1 }}
        >
          /100
        </text>
      </svg>
      <div className="text-[12px] font-semibold" style={{ color }}>
        {bandLabel}
      </div>
      {description ? (
        <div className="text-[12px] text-[var(--text-muted)] leading-snug text-center max-w-[160px]">
          {description}
        </div>
      ) : null}
      {factors && factors.length > 0 ? (
        <ul className="mt-1 w-full space-y-1">
          {factors.map((f) => (
            <li key={f.label} className="text-[12px]">
              <div className="flex items-center justify-between">
                <span className="text-[var(--text-muted)]">{f.label}</span>
                <span className="font-mono tabular-nums">
                  {Math.round(Math.max(0, Math.min(100, f.value)))}
                </span>
              </div>
              <div className="h-1 bg-[var(--border)]/50 rounded">
                <div
                  className="h-full rounded"
                  style={{
                    width: `${Math.max(0, Math.min(100, f.value))}%`,
                    background: BAND_COLOR[bandFor(f.value)],
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
