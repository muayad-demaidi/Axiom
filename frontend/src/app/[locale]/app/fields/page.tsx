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
  dimension: "بُعد",
  measure: "مقياس",
  key: "معرّف",
  date: "تاريخ",
};
const FMT_LABELS: Record<AxiomFormatKind, string> = {
  number: "رقم",
  integer: "عدد صحيح",
  currency: "عملة",
  percent: "نسبة مئوية",
  date: "تاريخ",
  text: "نص",
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
        <div dir="rtl">
          <div className="mt-6 flex items-center gap-3 flex-wrap">
            <label className="text-[12px] text-[var(--text-muted)]">تصفية</label>
            <select
              value={filter}
              onChange={(e) => setFilter(e.target.value as "all" | AxiomRole)}
              className="px-2 py-1 text-[12px] rounded border border-[var(--border)] bg-[var(--surface)]"
              style={{ minHeight: 32 }}
            >
              <option value="all">كل الأعمدة</option>
              <option value="measure">المقاييس</option>
              <option value="dimension">الأبعاد</option>
              <option value="date">التواريخ</option>
              <option value="key">المعرّفات</option>
            </select>
            {meta && (
              <span className="text-[12px] text-[var(--text-muted)]">
                {fieldEntries.length} من أصل {Object.keys(meta.fields).length} عمود
                · {Object.keys(meta.overrides || {}).length} مخصّص
              </span>
            )}
          </div>

          {error && (
            <div
              className="text-sm text-red-600 mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2"
              role="alert"
            >
              {error}
            </div>
          )}
          {loading && !meta && (
            <div
              className="text-[12px] text-[var(--text-muted)] mt-3 inline-flex items-center gap-2"
              role="status"
              aria-live="polite"
            >
              <span
                className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]"
                aria-hidden="true"
              />
              جاري التحميل…
            </div>
          )}

          {meta && (
            <div className="mt-4 overflow-auto card p-0">
              <table className="w-full text-[12px]">
                <thead className="text-[var(--text-muted)] text-[12px] uppercase tracking-widest">
                  <tr className="border-b border-[var(--border)]">
                    <th className="text-right px-3 py-2 font-mono">العمود</th>
                    <th className="text-right px-3 py-2">الدور</th>
                    <th className="text-right px-3 py-2">التجميع الافتراضي</th>
                    <th className="text-right px-3 py-2">التنسيق</th>
                    <th className="text-right px-3 py-2">المسمّى</th>
                    <th className="text-right px-3 py-2">الوصف</th>
                    <th className="text-right px-3 py-2">الفرز حسب</th>
                    <th className="text-center px-3 py-2">مرئي</th>
                    <th className="text-right px-3 py-2">ملاحظات</th>
                    <th className="text-left px-3 py-2">إعادة تعيين</th>
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
                          <div className="text-[12px] text-[var(--text-muted)]">
                            {info.dtype} · {info.unique?.toLocaleString()} قيمة فريدة
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
                              className="w-12 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[12px]"
                              aria-label={`عدد المنازل العشرية للعمود ${col}`}
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
                            className="w-44 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[12px]"
                            aria-label={`مسمّى العمود ${col}`}
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <input
                            type="text"
                            defaultValue={info.description || ""}
                            placeholder="ماذا يمثّل هذا العمود؟"
                            onBlur={(e) => {
                              const v = e.currentTarget.value;
                              if (v !== (info.description || "")) patchOne(col, { description: v });
                            }}
                            className="w-48 px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[12px]"
                            aria-label={`وصف العمود ${col}`}
                          />
                        </td>
                        <td className="px-3 py-2 align-top">
                          <select
                            value={info.sort_by || ""}
                            onChange={(e) => patchOne(col, { sort_by: e.target.value || null })}
                            className="px-2 py-1 rounded border border-[var(--border)] bg-[var(--surface)] text-[12px]"
                            aria-label={`الفرز حسب للعمود ${col}`}
                          >
                            <option value="">— الافتراضي —</option>
                            {meta && Object.keys(meta.fields).filter((c) => c !== col).map((c) => (
                              <option key={c} value={c}>{c}</option>
                            ))}
                          </select>
                        </td>
                        <td className="px-3 py-2 align-top text-center">
                          <input
                            type="checkbox"
                            className="h-4 w-4"
                            checked={info.visible !== false}
                            onChange={(e) => patchOne(col, { visible: e.target.checked })}
                            title="إخفاء العمود من القوائم دون حذفه"
                            aria-label={`إظهار العمود ${col}`}
                          />
                        </td>
                        <td className="px-3 py-2 align-top text-[var(--text-muted)] max-w-xs">
                          {info.warnings && info.warnings.length > 0 ? (
                            <ul className="text-amber-600 list-disc list-inside" role="alert">
                              {info.warnings.map((w, i) => <li key={i}>{w}</li>)}
                            </ul>
                          ) : (
                            <span className="text-[12px]">—</span>
                          )}
                        </td>
                        <td className="px-3 py-2 align-top text-left">
                          {isOverridden ? (
                            <button
                              onClick={() => reset(col)}
                              className="text-[12px] text-[var(--accent)] hover:underline"
                              style={{ minHeight: 32, paddingInline: 8 }}
                              disabled={busy}
                            >
                              إعادة تعيين
                            </button>
                          ) : (
                            <span className="text-[12px] text-[var(--text-muted)]">تلقائي</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
