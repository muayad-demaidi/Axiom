"use client";
/**
 * Right-side drawer that auto-opens with skeleton loaders the moment a
 * tool fires from the chat. Has four tabs:
 *   • Profile      — dataset profile artifacts
 *   • Predictions  — prediction artifacts (with what-if sliders)
 *   • Visualize    — chart artifacts
 *   • Clusters     — cluster artifacts
 *
 * The "pin" toggle sits on every artifact card and controls whether it
 * shows up in the Final Report. The drawer pulls fresh artifact data
 * from `/api/chats/{sid}/artifacts` whenever a tool finishes.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { ChartRenderer, type ChartPayload } from "./Charts";
import { PredictionCard, type PredictionResult } from "./PredictionCard";

export type Artifact = {
  id: number;
  session_id: number;
  dataset_id: number | null;
  kind: "profile" | "prediction" | "chart" | "cluster" | "insight" | "qa" | string;
  title: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  pinned: boolean;
  created_at: string | null;
};

type Tab = "profile" | "visualize" | "predictions" | "clusters";

const TABS: { key: Tab; label: string; kind: string }[] = [
  { key: "profile", label: "Profile", kind: "profile" },
  { key: "visualize", label: "Visualize", kind: "chart" },
  { key: "predictions", label: "Predictions", kind: "prediction" },
  { key: "clusters", label: "Clusters", kind: "cluster" },
];

const KIND_TO_TAB: Record<string, Tab> = {
  profile: "profile",
  chart: "visualize",
  prediction: "predictions",
  cluster: "clusters",
};

export type PendingTool = { id: string; tool: string };

export function ArtifactDrawer({
  open,
  onClose,
  sessionId,
  refreshKey,
  pending,
  initialTab,
}: {
  open: boolean;
  onClose: () => void;
  sessionId: number | null;
  refreshKey: number;
  pending: PendingTool[];
  initialTab?: Tab;
}) {
  const [tab, setTab] = useState<Tab>(initialTab || "profile");
  const [items, setItems] = useState<Artifact[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

  useEffect(() => {
    if (!sessionId) return;
    let cancelled = false;
    setLoading(true);
    api<Artifact[]>(`/api/chats/${sessionId}/artifacts`)
      .then((rows) => {
        if (cancelled) return;
        setItems(rows);
      })
      .catch((e) => {
        if (!cancelled) setError(errMessage(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, refreshKey]);

  const grouped = useMemo(() => {
    const out: Record<Tab, Artifact[]> = {
      profile: [], visualize: [], predictions: [], clusters: [],
    };
    for (const a of items) {
      const t = KIND_TO_TAB[a.kind];
      if (t) out[t].push(a);
    }
    return out;
  }, [items]);

  const pendingByTab = useMemo(() => {
    const out: Record<Tab, PendingTool[]> = {
      profile: [], visualize: [], predictions: [], clusters: [],
    };
    for (const p of pending) {
      if (p.tool === "profile_dataset") out.profile.push(p);
      else if (p.tool === "make_chart") out.visualize.push(p);
      else if (p.tool === "predict_column") out.predictions.push(p);
      else if (p.tool === "cluster_dataset") out.clusters.push(p);
    }
    return out;
  }, [pending]);

  async function togglePin(a: Artifact) {
    try {
      const next = !a.pinned;
      setItems((cur) => cur.map((x) => (x.id === a.id ? { ...x, pinned: next } : x)));
      await api(`/api/artifacts/${a.id}/pin`, { method: "PATCH", json: { pinned: next } });
    } catch (e) {
      setError(errMessage(e));
    }
  }

  async function removeArtifact(a: Artifact) {
    if (!confirm(`Delete "${a.title}"?`)) return;
    try {
      await api(`/api/artifacts/${a.id}`, { method: "DELETE" });
      setItems((cur) => cur.filter((x) => x.id !== a.id));
    } catch (e) {
      setError(errMessage(e));
    }
  }

  if (!open) return null;

  return (
    <aside
      className="fixed top-14 right-0 bottom-0 w-[440px] max-w-[92vw] border-l border-[var(--border)] bg-[var(--surface)] shadow-2xl z-30 flex flex-col"
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-[var(--border)]">
        <div>
          <div className="font-mono text-[10px] tracking-widest uppercase text-[var(--text-muted)]">
            Artifact drawer
          </div>
          <div className="text-sm font-semibold">Tool outputs</div>
        </div>
        <button
          onClick={onClose}
          className="text-xs text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1 rounded hover:bg-[var(--surface-alt)]"
          aria-label="Close drawer"
        >
          ✕
        </button>
      </div>
      <div className="flex border-b border-[var(--border)]">
        {TABS.map((t) => {
          const count =
            grouped[t.key].length + pendingByTab[t.key].length;
          const active = tab === t.key;
          return (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex-1 text-xs py-2 border-b-2 transition-colors ${
                active
                  ? "border-[var(--accent)] text-[var(--accent)]"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text)]"
              }`}
            >
              {t.label} {count ? <span className="ml-1 text-[10px] font-mono opacity-70">({count})</span> : null}
            </button>
          );
        })}
      </div>
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {error && <div className="text-xs text-red-500">{error}</div>}
        {loading && items.length === 0 && (
          <div className="text-xs text-[var(--text-muted)]">Loading…</div>
        )}
        {pendingByTab[tab].map((p) => (
          <Skeleton key={p.id} tool={p.tool} />
        ))}
        {grouped[tab].map((a) => (
          <ArtifactCard
            key={a.id}
            artifact={a}
            onPin={() => togglePin(a)}
            onDelete={() => removeArtifact(a)}
          />
        ))}
        {!loading && pendingByTab[tab].length === 0 && grouped[tab].length === 0 && (
          <div className="text-xs text-[var(--text-muted)] border border-dashed border-[var(--border)] rounded p-4 text-center">
            Ask the chat for a {tab === "visualize" ? "chart" : tab.replace(/s$/, "")} and it will appear here.
          </div>
        )}
      </div>
    </aside>
  );
}

function Skeleton({ tool }: { tool: string }) {
  const label =
    tool === "profile_dataset" ? "Profiling dataset…"
    : tool === "make_chart" ? "Building chart…"
    : tool === "predict_column" ? "Fitting prediction model…"
    : tool === "cluster_dataset" ? "Clustering rows…"
    : `Running ${tool}…`;
  return (
    <div className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface-alt)]/50 animate-pulse">
      <div className="text-[11px] font-mono text-[var(--text-muted)] mb-3">{label}</div>
      <div className="h-3 bg-[var(--border)] rounded w-3/4 mb-2"></div>
      <div className="h-3 bg-[var(--border)] rounded w-1/2 mb-4"></div>
      <div className="h-32 bg-[var(--border)] rounded"></div>
    </div>
  );
}

function ArtifactCard({
  artifact,
  onPin,
  onDelete,
}: {
  artifact: Artifact;
  onPin: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface-alt)]/40">
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <div className="font-semibold text-sm flex-1 truncate" title={artifact.title}>
          {artifact.title}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={onPin}
            className={`text-[10px] px-2 py-0.5 rounded border ${
              artifact.pinned
                ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10"
                : "border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--accent)]"
            }`}
            title={artifact.pinned ? "Pinned to report" : "Pin to report"}
          >
            {artifact.pinned ? "Pinned" : "Pin"}
          </button>
          <button
            onClick={onDelete}
            className="text-[10px] px-2 py-0.5 rounded text-[var(--text-muted)] hover:text-red-500"
            title="Delete artifact"
          >
            ✕
          </button>
        </div>
      </div>
      <ArtifactBody artifact={artifact} />
    </div>
  );
}

function ArtifactBody({ artifact }: { artifact: Artifact }) {
  if (artifact.kind === "chart") {
    return <ChartRenderer payload={artifact.result as unknown as ChartPayload} height={220} />;
  }
  if (artifact.kind === "prediction") {
    return <PredictionCard title="" result={artifact.result as unknown as PredictionResult} />;
  }
  if (artifact.kind === "profile") {
    return <ProfileBody result={artifact.result as ProfileResult} />;
  }
  if (artifact.kind === "cluster") {
    return <ClusterBody result={artifact.result as ClusterResult} />;
  }
  if (artifact.kind === "insight") {
    return <InsightBody result={artifact.result as { items: InsightItem[] }} />;
  }
  return null;
}

type ProfileResult = {
  rows: number;
  cols: number;
  duplicate_rows: number;
  columns: Array<{
    name: string;
    dtype: string;
    non_null: number;
    missing: number;
    missing_pct: number;
    unique: number;
  }>;
};

function ProfileBody({ result }: { result: ProfileResult }) {
  return (
    <div>
      <div className="text-[11px] text-[var(--text-muted)] font-mono mb-2">
        {result.rows.toLocaleString()} rows · {result.cols} cols · {result.duplicate_rows.toLocaleString()} duplicates
      </div>
      <div className="max-h-72 overflow-auto border border-[var(--border)] rounded">
        <table className="w-full text-[11px]">
          <thead className="sticky top-0 bg-[var(--surface-alt)]">
            <tr>
              <th className="text-left px-2 py-1.5">Column</th>
              <th className="text-left px-2 py-1.5">Dtype</th>
              <th className="text-right px-2 py-1.5">Missing</th>
              <th className="text-right px-2 py-1.5">Unique</th>
            </tr>
          </thead>
          <tbody>
            {(result.columns || []).map((c) => (
              <tr key={c.name} className="border-t border-[var(--border)]/50">
                <td className="px-2 py-1 truncate max-w-[140px]" title={c.name}>{c.name}</td>
                <td className="px-2 py-1 font-mono text-[10px] text-[var(--text-muted)]">{c.dtype}</td>
                <td className="px-2 py-1 text-right font-mono text-[10px]">
                  {c.missing_pct}%
                </td>
                <td className="px-2 py-1 text-right font-mono text-[10px]">
                  {c.unique.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

type ClusterResult = {
  k: number;
  cluster_sizes: Record<string, number>;
  centroids: Array<{ cluster: number; size: number; values: Record<string, number> }>;
  features_used: string[];
  scatter?: Array<{ x: number; y: number; cluster: number }>;
  pca?: { explained_variance_ratio: number[]; sampled: number; total: number };
};

const CLUSTER_COLORS = [
  "#60A5FA", "#F472B6", "#34D399", "#FBBF24", "#A78BFA",
  "#F87171", "#22D3EE", "#FB923C", "#4ADE80", "#E879F9",
];

function ClusterScatter({
  points,
  width = 320,
  height = 220,
}: {
  points: Array<{ x: number; y: number; cluster: number }>;
  width?: number;
  height?: number;
}) {
  if (!points || points.length === 0) return null;
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = Math.min(...ys), yMax = Math.max(...ys);
  const pad = 12;
  const sx = (v: number) =>
    pad + ((v - xMin) / (xMax - xMin || 1)) * (width - 2 * pad);
  const sy = (v: number) =>
    height - pad - ((v - yMin) / (yMax - yMin || 1)) * (height - 2 * pad);
  return (
    <svg width={width} height={height} role="img" aria-label="Cluster PCA scatter">
      <rect x={0} y={0} width={width} height={height} fill="transparent" />
      <line x1={pad} y1={height - pad} x2={width - pad} y2={height - pad}
            stroke="var(--border)" strokeWidth={1} />
      <line x1={pad} y1={pad} x2={pad} y2={height - pad}
            stroke="var(--border)" strokeWidth={1} />
      {points.map((p, i) => (
        <circle
          key={i}
          cx={sx(p.x)}
          cy={sy(p.y)}
          r={2.5}
          fill={CLUSTER_COLORS[p.cluster % CLUSTER_COLORS.length]}
          fillOpacity={0.7}
        />
      ))}
    </svg>
  );
}

function ClusterBody({ result }: { result: ClusterResult }) {
  const total = Object.values(result.cluster_sizes || {}).reduce((a, b) => a + b, 0) || 1;
  const ev = result.pca?.explained_variance_ratio ?? [];
  const evLabel = ev.length >= 2
    ? `PCA · PC1 ${(ev[0] * 100).toFixed(1)}% / PC2 ${(ev[1] * 100).toFixed(1)}%`
    : "PCA";
  return (
    <div className="space-y-3">
      <div className="text-[11px] text-[var(--text-muted)] font-mono">
        k = {result.k} · {result.features_used?.length ?? 0} features
      </div>
      {result.scatter && result.scatter.length > 0 && (
        <div className="border border-[var(--border)] rounded p-2">
          <div className="flex items-baseline justify-between mb-1">
            <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
              {evLabel}
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {Array.from({ length: result.k }).map((_, i) => (
                <div key={i} className="flex items-center gap-1 text-[10px]">
                  <span
                    className="inline-block w-2 h-2 rounded-full"
                    style={{ backgroundColor: CLUSTER_COLORS[i % CLUSTER_COLORS.length] }}
                  />
                  <span className="text-[var(--text-muted)]">#{i}</span>
                </div>
              ))}
            </div>
          </div>
          <ClusterScatter points={result.scatter} />
          {result.pca && (
            <div className="text-[9px] font-mono text-[var(--text-muted)] mt-1">
              Showing {result.pca.sampled.toLocaleString()} of {result.pca.total.toLocaleString()} rows
            </div>
          )}
        </div>
      )}
      <div className="space-y-2">
        {(result.centroids || []).map((c) => (
          <div key={c.cluster} className="border border-[var(--border)] rounded p-2">
            <div className="flex items-baseline justify-between mb-1">
              <div className="text-xs font-semibold">Cluster #{c.cluster}</div>
              <div className="text-[10px] font-mono text-[var(--text-muted)]">
                {c.size.toLocaleString()} rows · {Math.round((c.size / total) * 100)}%
              </div>
            </div>
            <div className="h-1.5 bg-[var(--surface-alt)] rounded overflow-hidden mb-2">
              <div
                className="h-full bg-[var(--accent)]"
                style={{ width: `${Math.max(2, (c.size / total) * 100)}%` }}
              />
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px] font-mono">
              {Object.entries(c.values).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="truncate text-[var(--text-muted)]">{k}</span>
                  <span>{Number(v).toLocaleString(undefined, { maximumFractionDigits: 3 })}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

type InsightItem = { kind: string; severity: string; headline: string; subtitle?: string };

function InsightBody({ result }: { result: { items: InsightItem[] } }) {
  const items = result.items ?? [];
  if (items.length === 0) {
    return <div className="text-xs text-[var(--text-muted)]">No insights.</div>;
  }
  return (
    <ul className="space-y-1.5">
      {items.map((it, i) => (
        <li key={i} className="text-[11px]">
          <div className="font-semibold">[{it.severity.toUpperCase()}] {it.headline}</div>
          {it.subtitle && <div className="text-[var(--text-muted)]">{it.subtitle}</div>}
        </li>
      ))}
    </ul>
  );
}
