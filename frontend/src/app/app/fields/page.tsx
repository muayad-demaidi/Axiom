"use client";
/**
 * Field settings — per-column metadata (role / default aggregation /
 * format / label) for the active dataset.
 *
 * Writes a partial PATCH to /api/bi/{id}/field-meta as the user
 * tweaks each row.  The pivot, dashboard, visualize page and chat
 * assistant all read this metadata so the picks land everywhere at
 * once.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import type {
  AxiomAggregation,
  AxiomFieldMeta,
  AxiomFieldMetaResponse,
  AxiomFormatKind,
  AxiomRole,
} from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import {
  MissingDatasetNotice,
  ModeAwareHeading,
} from "@/components/product/ModeAware";

const ROLE_LABELS: Record<AxiomRole, string> = {
  dimension: "Dimension",
  measure: "Measure",
  key: "Identifier",
  date: "Date",
};
const FMT_LABELS: Record<AxiomFormatKind, string> = {
  number: "Number",
  integer: "Integer",
  currency: "Currency",
  percent: "Percent",
  date: "Date",
  text: "Text",
};

export default function FieldSettingsPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const [meta, setMeta] = useState<AxiomFieldMetaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);
  const [filter, setFilter] = useState<"all" | AxiomRole>("all");
  const [pendingId, setPendingId] = useState<string | null>(null);

  const datasetId = typeof window !== "undefined" ? getActiveDatasetId() : null;

  const reload = useCallback(async () => {
    if (!datasetId) return;
    setLoading(true);
    try {
      const r = await api<AxiomFieldMetaResponse>(`/api/bi/${datasetId}/field-meta`);
      setMeta(r);
      setError(null);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setLoading(false);
    }
  }, [datasetId]);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    if (!datasetId) { setHasDataset(false); return; }
    setHasDataset(true);
    void reload();
  }, [datasetId, router, reload]);

  const patchOne = useCallback(
    async (col: string, patch: Partial<AxiomFieldMeta>) => {
      if (!datasetId) return;
      setPendingId(col);
      try {
        const r = await api<AxiomFieldMetaResponse>(`/api/bi/${datasetId}/field-meta`, {
          method: "PATCH",
          json: { fields: { [col]: patch } } as unknown as Record<string, unknown>,
        });
        setMeta(r);
      } catch (e) {
        setError(errMessage(e));
      } finally {
        setPendingId(null);
      }
    },
    [datasetId]
  );

  const reset = useCallback(
    async (col: string) => {
      if (!datasetId) return;
      setPendingId(col);
      try {
        await api(`/api/bi/${datasetId}/field-meta/${encodeURIComponent(col)}`, {
          method: "DELETE",
        });
        await reload();
      } catch (e) {
        setError(errMessage(e));
      } finally {
        setPendingId(null);
      }
    },
    [datasetId, reload]
  );

  const fieldEntries = useMemo(() => {
    if (!meta) return [] as Array<[string, AxiomFieldMeta]>;
    const all = Object.entries(meta.fields) as Array<[string, AxiomFieldMeta]>;
    return filter === "all" ? all : all.filter(([, v]) => v.role === filter);
  }, [meta, filter]);

  return (
    <div className="max-w-5xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Modeling · Field settings"
        guidedTitle="Tell us what each column means"
        expertTitle="Field metadata"
        guidedSubtitle="Mark which columns are measures (sum-able) vs. categories vs. dates. Charts and the dashboard pick this up automatically."
        expertSubtitle="Per-column role, default aggregation, format and label. The aggregation engine, pivot, dashboard, and chat assistant share these settings."
      />

      {hasDataset === false ? (
        <MissingDatasetNotice projectId={projectId} toolName="field settings" />
      ) : (
        <>
          <div className="mt-6 flex items-center gap-3 flex-wrap">
            <label className="text-xs text-[var(--text-muted)]">Filter</label>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as "all" | AxiomRole)}
              className="px-2 py-1 text-xs rounded border border-[var(--border)] bg-[var(--surface)]"
            >
              <option value="all">All columns</option>
              <option value="measure">Measures</option>
              <option value="dimension">Dimensions</option>
              <option value="date">Dates</option>
              <option value="key">Identifiers</option>
            </select>
            {meta && (
              <span className="text-xs text-[var(--text-muted)]">
                {fieldEntries.length} of {Object.keys(meta.fields).length} columns
                · {Object.keys(meta.overrides || {}).length} customised
              </span>
            )}
          </div>

          {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
          {loading && !meta && <div className="text-xs text-[var(--text-muted)] mt-3">Loading…</div>}

          {meta && (
            <div className="mt-4 overflow-auto card p-0">
              <table className="w-full text-xs">
                <thead className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest">
                  <tr className="border-b border-[var(--border)]">
                    <th className="text-left px-3 py-2 font-mono">Column</th>
                    <th className="text-left px-3 py-2">Role</th>
                    <th className="text-left px-3 py-2">Default agg</th>
                    <th className="text-left px-3 py-2">Format</th>
                    <th className="text-left px-3 py-2">Label</th>
                    <th className="text-left px-3 py-2">Description</th>
                    <th className="text-left px-3 py-2">Sort by</th>
                    <th className="text-center px-3 py-2">Visible</th>
                    <th className="text-left px-3 py-2">Notes</th>
                    <th className="text-right px-3 py-2">Reset</th>
                  </tr>
                </thead>
                <tbody>
                  {fieldEntries.map(([col, info]) => {
                    const isOverridden = !!meta.overrides[col];
                    const busy = pendingId === col;
                    return (
                      <tr
                        key={col}
                        className={`border-b border-[var(--border)]/60 ${busy ? "opacity-60" : ""}`}
                      >
                        <td className="px-3 py-2 font-mono align-top">
                          <div>{col}</div>
                          <div className="text-[10px] text-[var(--text-muted)]">
                            {info.dtype} · {info.unique?.toLocaleString()} unique
                          </div>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <select
                            value={info.role}
                            onChange={(e) =>
                              patchOne(col, { role: e.target.value as AxiomRole })
                            }
                            className="px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
                          >
                            {(meta.vocab.roles).map((r) => (
                              <option key={r} value={r}>{ROLE_LABELS[r]}</option>
                            ))}
                          </select>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <select
                            value={info.default_agg}
                            onChange={(e) =>
                              patchOne(col, { default_agg: e.target.value as AxiomAggregation })
                            }
                            className="px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
                          >
                            {meta.vocab.aggregations.map((a) => (
                              <option key={a} value={a}>{meta.vocab.agg_labels[a]}</option>
                            ))}
                          </select>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <div className="flex items-center gap-1">
                            <select
                              value={info.format_kind}
                              onChange={(e) =>
                                patchOne(col, { format_kind: e.target.value as AxiomFormatKind })
                              }
                              className="px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
                            >
                              {meta.vocab.format_kinds.map((f) => (
                                <option key={f} value={f}>{FMT_LABELS[f]}</option>
                              ))}
                            </select>
                            <input
                              type="number"
                              min={0}
                              max={6}
                              value={info.precision}
                              onChange={(e) =>
                                patchOne(col, { precision: Number(e.target.value) })
                              }
                              className="w-12 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
                            />
                          </div>
                        </td>
                        <td className="px-3 py-2 align-top">
                          <input
                            type="text"
                            defaultValue={info.label}
                            onBlur={(e) => {
                              const v = e.currentTarget.value.trim();
                              if (v && v !== info.label) patchOne(col, { label: v });
                            }}
                            className="w-44 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <input
                            type="text"
                            defaultValue={info.description || ""}
                            placeholder="What does this column mean?"
                            onBlur={(e) => {
                              const v = e.currentTarget.value;
                              if (v !== (info.description || "")) patchOne(col, { description: v });
                            }}
                            className="w-48 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <select
                            value={info.sort_by || ""}
                            onChange={(e) => patchOne(col, { sort_by: e.target.value || null })}
                            className="px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
                          >
                            <option value="">— natural —</option>
                            {meta && Object.keys(meta.fields).filter((c) => c !== col).map((c) => (
                              <option key={c} value={c}>{c}</option>
                            ))}
                          </select>
                        </td>
                        <td className="px-3 py-2 align-top text-center">
                          <input
                            type="checkbox"
                            checked={info.visible !== false}
                            onChange={(e) => patchOne(col, { visible: e.target.checked })}
                            title="Hide from pickers without deleting the column"
                          />
                        </td>
                        <td className="px-3 py-2 align-top text-[var(--text-muted)] max-w-xs">
                          {info.warnings && info.warnings.length > 0 ? (
                            <ul className="text-amber-600 list-disc list-inside">
                              {info.warnings.map((w, i) => <li key={i}>{w}</li>)}
                            </ul>
                          ) : (
                            <span className="text-[10px]">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 align-top text-right">
                          {isOverridden ? (
                            <button
                              onClick={() => reset(col)}
                              className="text-[11px] text-[var(--accent)] hover:underline"
                              disabled={busy}
                            >
                              Reset
                            </button>
                          ) : (
                            <span className="text-[10px] text-[var(--text-muted)]">auto</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
