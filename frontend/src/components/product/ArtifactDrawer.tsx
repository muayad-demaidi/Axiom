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
import { memo, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { ChartRenderer, type ChartPayload } from "./Charts";
import { PredictionCard, type PredictionResult } from "./PredictionCard";

export type Artifact = {
  id: number;
  session_id: number;
  project_id?: number | null;
  dataset_id: number | null;
  kind: "profile" | "prediction" | "chart" | "cluster" | "insight" | "qa" | "data_model" | "data_model_query" | string;
  title: string;
  params: Record<string, unknown>;
  result: Record<string, unknown>;
  pinned: boolean;
  created_at: string | null;
};

type Tab = "profile" | "visualize" | "predictions" | "clusters" | "model";

const TABS: { key: Tab; label: string; kind: string }[] = [
  { key: "profile", label: "Profile", kind: "profile" },
  { key: "visualize", label: "Visualize", kind: "chart" },
  { key: "predictions", label: "Predictions", kind: "prediction" },
  { key: "clusters", label: "Clusters", kind: "cluster" },
  { key: "model", label: "Data model", kind: "data_model" },
];

const KIND_TO_TAB: Record<string, Tab> = {
  profile: "profile",
  chart: "visualize",
  prediction: "predictions",
  cluster: "clusters",
  data_model: "model",
  data_model_query: "model",
};

export type PendingTool = { id: string; tool: string };

function ArtifactDrawerBase({
  open,
  onClose,
  sessionId,
  refreshKey,
  pending,
  initialTab,
  showDataModelTab = true,
}: {
  open: boolean;
  onClose: () => void;
  sessionId: number | null;
  refreshKey: number;
  pending: PendingTool[];
  initialTab?: Tab;
  showDataModelTab?: boolean;
}) {
  const visibleTabs = useMemo(
    () => (showDataModelTab ? TABS : TABS.filter((t) => t.key !== "model")),
    [showDataModelTab],
  );
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
      profile: [], visualize: [], predictions: [], clusters: [], model: [],
    };
    for (const a of items) {
      const t = KIND_TO_TAB[a.kind];
      if (t) out[t].push(a);
    }
    return out;
  }, [items]);

  const pendingByTab = useMemo(() => {
    const out: Record<Tab, PendingTool[]> = {
      profile: [], visualize: [], predictions: [], clusters: [], model: [],
    };
    for (const p of pending) {
      if (p.tool === "profile_dataset") out.profile.push(p);
      else if (p.tool === "make_chart") out.visualize.push(p);
      else if (p.tool === "predict_column") out.predictions.push(p);
      else if (p.tool === "cluster_dataset") out.clusters.push(p);
      else if (
        p.tool === "list_model" ||
        p.tool === "query_model" ||
        p.tool === "explain_model"
      )
        out.model.push(p);
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
        {visibleTabs.map((t) => {
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
    : tool === "list_model" ? "Loading data model…"
    : tool === "query_model" ? "Running cross-table query…"
    : tool === "explain_model" ? "Explaining data model…"
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
  if (artifact.kind === "data_model") {
    return <DataModelBody artifact={artifact} />;
  }
  if (artifact.kind === "data_model_query") {
    return <DataModelQueryBody result={artifact.result as DataModelQueryResult} />;
  }
  return null;
}

type DataModelTable = {
  id?: number;
  dataset_id: number;
  dataset_name: string;
  rows: number;
  cols: number;
  role: "fact" | "dimension" | "summary" | "bridge" | string;
  grain?: { label?: string };
  pk_columns?: string[];
  fk_columns?: string[];
  id_columns?: string[];
  date_columns?: string[];
  measure_columns?: string[];
  suspicious?: { column: string; kind: string; detail: string }[];
  columns?: { name: string; kind?: string; dtype?: string }[];
  confirmed: boolean;
};

type DataModelRel = {
  id: number;
  left_table: string;
  left_column: string;
  right_table: string;
  right_column: string;
  cardinality: string;
  status: "proposed" | "confirmed" | "rejected" | string;
  band: "high" | "medium" | "low" | "inferred" | string;
  confidence: number;
  evidence: string[];
  explanation?: string;
};

type DataModelQuestion = {
  id: number;
  kind: string;
  prompt: string;
  status?: string;
  options?: { label: string; value: string }[];
  target?: Record<string, unknown>;
};

type DataModelBundle = {
  description?: string | null;
  confirmed?: boolean;
  tables: DataModelTable[];
  relationships: DataModelRel[];
  questions: DataModelQuestion[];
};

const ROLE_LABEL: Record<string, string> = {
  fact: "Fact",
  dimension: "Dimension",
  summary: "Summary",
  bridge: "Bridge",
};

const BAND_LABEL: Record<string, string> = {
  high: "high",
  medium: "medium",
  low: "low",
  inferred: "inferred",
};

const ROLE_OPTIONS = ["fact", "dimension", "summary", "bridge"];

function DataModelBody({ artifact }: { artifact: Artifact }) {
  // The artifact's `result` is a snapshot taken when the tool ran.
  // We refetch the live bundle so the user always sees their latest
  // confirmations and any edits made from this drawer instantly.
  const projectId = artifact.project_id ?? null;
  const snapshot = (artifact.result || {}) as Partial<DataModelBundle>;
  const [bundle, setBundle] = useState<DataModelBundle>({
    description: snapshot.description ?? "",
    confirmed: snapshot.confirmed ?? false,
    tables: snapshot.tables ?? [],
    relationships: snapshot.relationships ?? [],
    questions: snapshot.questions ?? [],
  });
  const [busy, setBusy] = useState(false);
  const [draftDesc, setDraftDesc] = useState<string>(snapshot.description ?? "");
  const [showDescEditor, setShowDescEditor] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    api<DataModelBundle>(`/api/projects/${projectId}/data-model`)
      .then((live) => {
        if (cancelled) return;
        setBundle(live);
        setDraftDesc(live.description ?? "");
      })
      .catch(() => {
        /* keep snapshot fallback */
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  async function refetch() {
    if (!projectId) return;
    try {
      const live = await api<DataModelBundle>(`/api/projects/${projectId}/data-model`);
      setBundle(live);
      setDraftDesc(live.description ?? "");
    } catch {
      /* swallow */
    }
  }

  async function patchTable(t: DataModelTable, body: Record<string, unknown>) {
    // Backend route is keyed by dataset_id (the FK), not the
    // ProjectSemanticTable row id. Send dataset_id.
    if (!projectId || !t.dataset_id) return;
    setBusy(true);
    try {
      await api(`/api/projects/${projectId}/data-model/tables/${t.dataset_id}`, {
        method: "PATCH",
        json: body,
      });
      await refetch();
    } catch {
      /* swallow */
    } finally {
      setBusy(false);
    }
  }

  async function patchRel(r: DataModelRel, body: Record<string, unknown>) {
    if (!projectId) return;
    setBusy(true);
    try {
      await api(`/api/projects/${projectId}/data-model/relationships/${r.id}`, {
        method: "PATCH",
        json: body,
      });
      await refetch();
    } catch {
      /* swallow */
    } finally {
      setBusy(false);
    }
  }

  async function patchQuestion(q: DataModelQuestion, body: Record<string, unknown>) {
    if (!projectId) return;
    setBusy(true);
    try {
      await api(`/api/projects/${projectId}/data-model/questions/${q.id}`, {
        method: "PATCH",
        json: body,
      });
      await refetch();
    } catch {
      /* swallow */
    } finally {
      setBusy(false);
    }
  }

  async function saveDescription() {
    if (!projectId) return;
    setBusy(true);
    try {
      await api(`/api/projects/${projectId}/data-model/description`, {
        method: "PUT",
        json: { description: draftDesc, confirmed: true },
      });
      setShowDescEditor(false);
      await refetch();
    } catch {
      /* swallow */
    } finally {
      setBusy(false);
    }
  }

  async function refreshModel() {
    if (!projectId) return;
    setBusy(true);
    try {
      await api(`/api/projects/${projectId}/data-model/refresh`, { method: "POST" });
      await refetch();
    } catch {
      /* swallow */
    } finally {
      setBusy(false);
    }
  }

  const tables = bundle.tables ?? [];
  const rels = bundle.relationships ?? [];
  const questions = bundle.questions ?? [];

  return (
    <div className="space-y-3">
      {/* ---- Business description editor ---- */}
      <div className="rounded border border-[var(--border)] bg-[var(--surface-alt)]/40 p-2">
        <div className="flex items-center justify-between gap-2 mb-1">
          <div className="font-mono text-[9px] uppercase tracking-widest text-[var(--text-muted)]">
            Business description
          </div>
          <div className="flex gap-1">
            {projectId != null && (
              <button
                onClick={refreshModel}
                disabled={busy}
                className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] hover:bg-[var(--surface-alt)] text-[var(--text-muted)] disabled:opacity-50"
                title="Re-profile tables and re-suggest joins"
              >
                Refresh
              </button>
            )}
            <button
              onClick={() => setShowDescEditor((v) => !v)}
              className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] hover:bg-[var(--surface-alt)] text-[var(--text-muted)]"
            >
              {showDescEditor ? "Cancel" : "Edit"}
            </button>
          </div>
        </div>
        {showDescEditor ? (
          <div className="space-y-1">
            <textarea
              value={draftDesc}
              onChange={(e) => setDraftDesc(e.target.value)}
              rows={3}
              placeholder="Describe what this data is about, in plain English. e.g. 'Customers buy products and we track campaigns and KPIs.'"
              className="w-full text-[11px] p-2 rounded border border-[var(--border)] bg-[var(--surface)] font-sans leading-relaxed"
            />
            <div className="flex justify-end">
              <button
                onClick={saveDescription}
                disabled={busy}
                className="text-[10px] px-2 py-0.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--surface-alt)] disabled:opacity-50"
              >
                Save
              </button>
            </div>
          </div>
        ) : (
          <div className="text-[11px] leading-relaxed">
            {bundle.description?.trim()
              ? bundle.description
              : <span className="text-[var(--text-muted)] italic">No business context yet — click Edit to add one. The assistant will use it to ground its answers.</span>}
          </div>
        )}
      </div>

      {/* ---- Tables ---- */}
      <div>
        <div className="font-mono text-[9px] uppercase tracking-widest text-[var(--text-muted)] mb-1">
          Tables ({tables.length})
        </div>
        <div className="space-y-2">
          {tables.map((t) => (
            <div key={t.dataset_id}
                 className="border border-[var(--border)] rounded p-2">
              <div className="flex items-baseline justify-between gap-2">
                <div className="font-semibold text-xs truncate" title={t.dataset_name}>
                  {t.dataset_name}
                </div>
                <select
                  value={t.role}
                  disabled={busy || !t.id}
                  onChange={(e) => patchTable(t, { role: e.target.value, confirmed: true })}
                  className="text-[10px] font-mono px-1 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
                  aria-label="Override table role"
                >
                  {ROLE_OPTIONS.map((r) => (
                    <option key={r} value={r}>{ROLE_LABEL[r]}</option>
                  ))}
                </select>
              </div>
              <div className="text-[10px] font-mono text-[var(--text-muted)] mt-0.5">
                {t.rows.toLocaleString()} rows · {t.cols} cols
                {t.grain?.label ? ` · ${t.grain.label}` : ""}
              </div>
              {t.pk_columns && t.pk_columns.length > 0 && (
                <div className="text-[10px] mt-1">
                  <span className="text-[var(--text-muted)]">PK: </span>
                  <span className="font-mono">{t.pk_columns.join(", ")}</span>
                </div>
              )}
              {t.fk_columns && t.fk_columns.length > 0 && (
                <div className="text-[10px] mt-0.5">
                  <span className="text-[var(--text-muted)]">FK candidates: </span>
                  <span className="font-mono">{t.fk_columns.join(", ")}</span>
                </div>
              )}
              {t.date_columns && t.date_columns.length > 0 && (
                <div className="text-[10px] mt-0.5">
                  <span className="text-[var(--text-muted)]">Dates: </span>
                  <span className="font-mono">{t.date_columns.join(", ")}</span>
                </div>
              )}
              {t.measure_columns && t.measure_columns.length > 0 && (
                <div className="text-[10px] mt-0.5">
                  <span className="text-[var(--text-muted)]">Measures: </span>
                  <span className="font-mono">{t.measure_columns.join(", ")}</span>
                </div>
              )}
              {t.suspicious && t.suspicious.length > 0 && (
                <div className="text-[10px] mt-1 text-[var(--text-muted)]">
                  ⚠ {t.suspicious.slice(0, 3).map((s) => `${s.column} (${s.detail})`).join(", ")}
                </div>
              )}
              {t.confirmed && (
                <div className="text-[9px] font-mono text-[var(--accent)] mt-1">
                  confirmed
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ---- Relationships with Confirm/Reject controls ---- */}
      {rels.length > 0 && (
        <div>
          <div className="font-mono text-[9px] uppercase tracking-widest text-[var(--text-muted)] mb-1">
            Relationships ({rels.length})
          </div>
          <div className="space-y-1.5">
            {rels.map((r) => (
              <div key={r.id} className="border border-[var(--border)] rounded p-2">
                <div className="text-[11px] font-mono flex items-center gap-1 flex-wrap">
                  <span>{r.left_table}.</span>
                  {(() => {
                    const leftCols =
                      tables.find((t) => t.dataset_name === r.left_table)
                        ?.columns?.map((c) => c.name) ?? [];
                    return projectId != null && leftCols.length > 0 ? (
                      <select
                        value={r.left_column}
                        disabled={busy}
                        onChange={(e) =>
                          patchRel(r, { left_column: e.target.value })
                        }
                        className="text-[11px] font-mono px-1 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
                        aria-label={`Edit join column for ${r.left_table}`}
                      >
                        {leftCols.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    ) : (
                      <span>{r.left_column}</span>
                    );
                  })()}
                  <span className="text-[var(--text-muted)] mx-1">↔</span>
                  <span>{r.right_table}.</span>
                  {(() => {
                    const rightCols =
                      tables.find((t) => t.dataset_name === r.right_table)
                        ?.columns?.map((c) => c.name) ?? [];
                    return projectId != null && rightCols.length > 0 ? (
                      <select
                        value={r.right_column}
                        disabled={busy}
                        onChange={(e) =>
                          patchRel(r, { right_column: e.target.value })
                        }
                        className="text-[11px] font-mono px-1 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
                        aria-label={`Edit join column for ${r.right_table}`}
                      >
                        {rightCols.map((c) => (
                          <option key={c} value={c}>{c}</option>
                        ))}
                      </select>
                    ) : (
                      <span>{r.right_column}</span>
                    );
                  })()}
                </div>
                <div className="text-[10px] flex items-center gap-2 mt-1 flex-wrap">
                  <span className="font-mono text-[var(--text-muted)]">
                    {r.cardinality}
                  </span>
                  <span className={`font-mono px-1 rounded border border-[var(--border)] ${
                    r.status === "confirmed" ? "text-[var(--accent)]"
                    : r.status === "rejected" ? "text-[var(--text-muted)] line-through"
                    : "text-[var(--text-muted)]"
                  }`}>
                    {r.status}
                  </span>
                  <span className="font-mono text-[var(--text-muted)]">
                    {BAND_LABEL[r.band] ?? r.band} · {Math.round((r.confidence ?? 0) * 100)}%
                  </span>
                </div>
                {r.explanation && (
                  <div className="text-[10px] text-[var(--text)] mt-1">
                    {r.explanation}
                  </div>
                )}
                {r.evidence?.length > 0 && (
                  <div className="text-[10px] text-[var(--text-muted)] mt-1">
                    {r.evidence.join(" · ")}
                  </div>
                )}
                {projectId != null && (
                  <div className="flex gap-1 mt-1.5 items-center flex-wrap">
                    <button
                      onClick={() => patchRel(r, { status: "confirmed" })}
                      disabled={busy || r.status === "confirmed"}
                      className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
                    >
                      Confirm
                    </button>
                    <button
                      onClick={() => patchRel(r, { status: "rejected" })}
                      disabled={busy || r.status === "rejected"}
                      className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
                    >
                      Reject
                    </button>
                    <button
                      onClick={() => patchRel(r, { status: "proposed", user_locked: false })}
                      disabled={busy || r.status === "proposed"}
                      className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
                      title="Reset to proposed and unlock for re-scoring"
                    >
                      Reset
                    </button>
                    <select
                      value={r.cardinality}
                      disabled={busy}
                      onChange={(e) => patchRel(r, { cardinality: e.target.value })}
                      className="text-[10px] font-mono px-1 py-0.5 rounded border border-[var(--border)] bg-[var(--surface)] text-[var(--text)] ml-auto"
                      aria-label="Edit join cardinality"
                      title="Edit cardinality"
                    >
                      {["1:1", "1:N", "N:1", "N:N"].map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ---- Open questions wired to the proactive question bar ---- */}
      {questions.length > 0 && (
        <div>
          <div className="font-mono text-[9px] uppercase tracking-widest text-[var(--text-muted)] mb-1">
            Open questions ({questions.length})
          </div>
          <div className="space-y-1.5">
            {questions.map((q) => (
              <QuestionRow
                key={q.id}
                q={q}
                projectId={projectId}
                busy={busy}
                onAnswer={(body) => patchQuestion(q, body)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function QuestionRow({
  q,
  projectId,
  busy,
  onAnswer,
}: {
  q: DataModelQuestion;
  projectId: number | null;
  busy: boolean;
  onAnswer: (body: Record<string, unknown>) => Promise<void> | void;
}) {
  const [freeText, setFreeText] = useState("");
  const [showFreeText, setShowFreeText] = useState(false);
  const opts = q.options ?? [];
  const hasOptions = opts.length > 0;

  return (
    <div className="border border-dashed border-[var(--border)] rounded p-2 text-[11px] leading-snug">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-[9px] text-[var(--text-muted)] uppercase">
          {q.kind}
        </span>
        {projectId != null && (
          <button
            onClick={() => onAnswer({ status: "dismissed" })}
            disabled={busy}
            className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
          >
            Dismiss
          </button>
        )}
      </div>
      <div className="mt-1">{q.prompt}</div>

      {projectId != null && hasOptions && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {opts.map((o) => (
            <button
              key={o.value}
              onClick={() =>
                onAnswer({
                  status: "answered",
                  answer: { value: o.value, label: o.label },
                })
              }
              disabled={busy}
              className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
            >
              {o.label}
            </button>
          ))}
        </div>
      )}

      {projectId != null && !hasOptions && !showFreeText && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          <button
            onClick={() => setShowFreeText(true)}
            disabled={busy}
            className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
          >
            Write an answer
          </button>
          <button
            onClick={() => {
              // Drop the question into the chat composer so the user
              // can discuss it conversationally. Question stays open
              // until they explicitly answer or dismiss.
              if (typeof window !== "undefined") {
                window.dispatchEvent(new CustomEvent("axiom:chat:prefill", {
                  detail: { text: q.prompt, send: false },
                }));
              }
            }}
            disabled={busy}
            className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
          >
            Discuss in chat
          </button>
        </div>
      )}

      {projectId != null && !hasOptions && showFreeText && (
        <div className="mt-1.5 space-y-1">
          <textarea
            value={freeText}
            onChange={(e) => setFreeText(e.target.value)}
            rows={2}
            placeholder="Your answer…"
            className="w-full text-[11px] p-1.5 rounded border border-[var(--border)] bg-[var(--surface)] font-sans"
          />
          <div className="flex gap-1 justify-end">
            <button
              onClick={() => {
                setShowFreeText(false);
                setFreeText("");
              }}
              disabled={busy}
              className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
            >
              Cancel
            </button>
            <button
              onClick={async () => {
                if (!freeText.trim()) return;
                await onAnswer({
                  status: "answered",
                  answer: { text: freeText.trim() },
                });
                setShowFreeText(false);
                setFreeText("");
              }}
              disabled={busy || !freeText.trim()}
              className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--surface-alt)] disabled:opacity-40"
            >
              Submit
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

type DataModelQueryResult = {
  rows: Record<string, unknown>[];
  columns: string[];
  warnings: string[];
  refusals: string[];
  inferred_joins: Array<{
    left_table: string; left_column: string;
    right_table: string; right_column: string;
  }>;
  used_relationships: Array<{
    left_table: string; left_column: string;
    right_table: string; right_column: string;
  }>;
  sql_like: string;
};

function DataModelQueryBody({ result }: { result: DataModelQueryResult }) {
  const rows = result?.rows ?? [];
  const cols = result?.columns ?? [];
  return (
    <div className="space-y-2">
      {(result?.refusals ?? []).map((m, i) => (
        <div key={`r${i}`} className="text-[11px] border border-[var(--border)] rounded p-2 text-red-500 bg-[var(--surface-alt)]/40">
          {m}
        </div>
      ))}
      {(result?.warnings ?? []).map((m, i) => (
        <div key={`w${i}`} className="text-[11px] border border-[var(--border)] rounded p-2 text-[var(--text-muted)] bg-[var(--surface-alt)]/40">
          ⚠ {m}
        </div>
      ))}
      {(result?.inferred_joins ?? []).length > 0 && (
        <div className="text-[10px] font-mono text-[var(--text-muted)]">
          Inferred joins:{" "}
          {result.inferred_joins
            .map((r) => `${r.left_table}.${r.left_column}↔${r.right_table}.${r.right_column}`)
            .join(", ")}
        </div>
      )}
      {rows.length > 0 && cols.length > 0 && (
        <div className="max-h-72 overflow-auto border border-[var(--border)] rounded">
          <table className="w-full text-[11px]">
            <thead className="sticky top-0 bg-[var(--surface-alt)]">
              <tr>
                {cols.map((c) => (
                  <th key={c} className="text-left px-2 py-1.5">{c}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.slice(0, 200).map((row, i) => (
                <tr key={i} className="border-t border-[var(--border)]/50">
                  {cols.map((c) => {
                    const v = row[c];
                    const display =
                      v == null ? ""
                      : typeof v === "number" ? Number(v).toLocaleString(undefined, { maximumFractionDigits: 3 })
                      : String(v);
                    return (
                      <td key={c} className="px-2 py-1 font-mono text-[10px] truncate max-w-[160px]">
                        {display}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {result?.sql_like && (
        <pre className="text-[10px] font-mono whitespace-pre-wrap text-[var(--text-muted)] border border-[var(--border)] rounded p-2 bg-[var(--surface-alt)]/30">
          {result.sql_like}
        </pre>
      )}
    </div>
  );
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

export const ArtifactDrawer = memo(ArtifactDrawerBase);
