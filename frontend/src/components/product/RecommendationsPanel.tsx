"use client";
/**
 * Mode-aware Recommendations panel (Task #251).
 *
 * Renders the rule-based recommendation engine output for the active
 * project. Guided mode shows priority-sorted action cards (one per
 * recommendation) with a single primary action button; Expert mode
 * shows the same data as a dense, sortable table.
 */
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { api } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { ModeAwareSection } from "./ModeAware";

type RecommendationStatus = "open" | "dismissed" | "applied" | "all";

type Recommendation = {
  id: number;
  type:
    | "discount" | "reorder" | "bundle"
    | "clearance" | "promote" | "investigate";
  product: string;
  reason: string;
  suggested_action: string;
  expected_impact?: string | null;
  priority: "high" | "medium" | "low";
  deadline?: string | null;
  confidence: number;
  dismissed: boolean;
  dismissed_at?: string | null;
  applied: boolean;
  applied_at?: string | null;
  created_at: string;
};

type RecommendationsResponse = {
  mode: "guided" | "expert";
  status: RecommendationStatus;
  recommendations: Recommendation[];
};

const PRIORITY_WEIGHT: Record<Recommendation["priority"], number> = {
  high: 0, medium: 1, low: 2,
};

const TYPE_ICON: Record<Recommendation["type"], string> = {
  discount: "%",
  reorder: "⟳",
  bundle: "+",
  clearance: "↓",
  promote: "★",
  investigate: "?",
};

function priorityBadge(p: Recommendation["priority"]): string {
  if (p === "high") return "bg-red-500/10 text-red-600";
  if (p === "medium") return "bg-amber-500/10 text-amber-600";
  return "bg-slate-500/10 text-slate-600";
}

function fmtDate(iso?: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString();
  } catch {
    return iso;
  }
}

export function RecommendationsPanel({
  projectId,
}: {
  projectId: number | null;
}) {
  const t = useTranslations("recommendations");
  const [status, setStatus] = useState<RecommendationStatus>("open");
  const [items, setItems] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);

  const TYPE_LABEL: Record<Recommendation["type"], string> = useMemo(() => ({
    discount: t("typeDiscount"),
    reorder: t("typeReorder"),
    bundle: t("typeBundle"),
    clearance: t("typeClearance"),
    promote: t("typePromote"),
    investigate: t("typeInvestigate"),
  }), [t]);

  const STATUS_LABEL: Record<RecommendationStatus, string> = useMemo(() => ({
    open: t("filterOpen"),
    applied: t("filterApplied"),
    dismissed: t("filterDismissed"),
    all: t("filterAll"),
  }), [t]);

  const PRIORITY_LABEL: Record<Recommendation["priority"], string> = useMemo(() => ({
    high: t("priorityHigh"),
    medium: t("priorityMedium"),
    low: t("priorityLow"),
  }), [t]);

  const reload = useCallback(async () => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await api<RecommendationsResponse>(
        `/api/projects/${projectId}/recommendations?status=${status}`,
      );
      setItems(r.recommendations || []);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setLoading(false);
    }
  }, [projectId, status]);

  useEffect(() => { void reload(); }, [reload]);

  const sorted = useMemo(() => {
    return [...items].sort((a, b) => {
      const pa = PRIORITY_WEIGHT[a.priority] ?? 9;
      const pb = PRIORITY_WEIGHT[b.priority] ?? 9;
      if (pa !== pb) return pa - pb;
      return (b.created_at || "").localeCompare(a.created_at || "");
    });
  }, [items]);

  const act = useCallback(async (id: number, action: "apply" | "dismiss") => {
    if (!projectId) return;
    setBusyId(id);
    try {
      await api(
        `/api/projects/${projectId}/recommendations/${id}/${action}`,
        { method: "POST" },
      );
      await reload();
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusyId(null);
    }
  }, [projectId, reload]);

  if (!projectId) {
    return (
      <div className="card mt-6 text-xs text-[var(--text-muted)]" role="status">
        {t("needProject")}
      </div>
    );
  }

  const StatusBar = (
    <div className="flex items-center gap-2 flex-wrap">
      {(["open", "applied", "dismissed", "all"] as RecommendationStatus[]).map(
        (s) => (
          <button
            key={s}
            onClick={() => setStatus(s)}
            className={
              "text-xs px-3 py-1 rounded border min-h-[32px] " +
              (status === s
                ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10"
                : "border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text)]")
            }
          >
            {STATUS_LABEL[s]}
          </button>
        ),
      )}
      <button
        onClick={() => void reload()}
        disabled={loading}
        className="ms-auto text-xs text-[var(--text-muted)] hover:text-[var(--accent)] min-h-[32px] px-2"
      >
        {loading ? t("refreshing") : t("refresh")}
      </button>
    </div>
  );

  const Empty = (
    <div className="card text-xs text-[var(--text-muted)]" role="status">
      {status === "all" ? t("empty") : t("emptyWithStatus", { status: STATUS_LABEL[status] })}
    </div>
  );

  const guided = (
    <div className="space-y-3">
      {StatusBar}
      {error && <div className="text-xs text-red-600">{error}</div>}
      {sorted.length === 0 ? Empty : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {sorted.map((r) => (
            <GuidedCard
              key={r.id}
              rec={r}
              busy={busyId === r.id}
              onApply={() => act(r.id, "apply")}
              onDismiss={() => act(r.id, "dismiss")}
              typeLabel={TYPE_LABEL[r.type]}
              priorityLabel={PRIORITY_LABEL[r.priority]}
              priorityBadgeClass={priorityBadge(r.priority)}
            />
          ))}
        </div>
      )}
    </div>
  );

  const expert = (
    <div className="space-y-3">
      {StatusBar}
      {error && <div className="text-xs text-red-600">{error}</div>}
      {sorted.length === 0 ? Empty : (
        <div className="card overflow-auto p-0">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest border-b border-[var(--border)]">
                <th className="text-start px-2 py-1.5">{t("tableHeaderPriority")}</th>
                <th className="text-start px-2 py-1.5">{t("tableHeaderType")}</th>
                <th className="text-start px-2 py-1.5">{t("tableHeaderProduct")}</th>
                <th className="text-start px-2 py-1.5">{t("tableHeaderReason")}</th>
                <th className="text-start px-2 py-1.5">{t("tableHeaderAction")}</th>
                <th className="text-end px-2 py-1.5">{t("tableHeaderConfidence")}</th>
                <th className="text-start px-2 py-1.5">{t("tableHeaderDeadline")}</th>
                <th className="text-end px-2 py-1.5">{t("tableHeaderActions")}</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((r) => (
                <tr key={r.id} className="border-b border-[var(--border)]/40">
                  <td className="px-2 py-1.5">
                    <span className={
                      "inline-block px-1.5 py-0.5 rounded text-[10px] font-medium " +
                      priorityBadge(r.priority)
                    }>{PRIORITY_LABEL[r.priority]}</span>
                  </td>
                  <td className="px-2 py-1.5 font-mono text-[11px]">
                    {TYPE_LABEL[r.type]}
                  </td>
                  <td className="px-2 py-1.5 font-mono text-[11px]">{r.product}</td>
                  <td className="px-2 py-1.5 text-[11px]">{r.reason}</td>
                  <td className="px-2 py-1.5 text-[11px]">{r.suggested_action}</td>
                  <td className="px-2 py-1.5 text-end tabular-nums">
                    {(r.confidence * 100).toFixed(0)}%
                  </td>
                  <td className="px-2 py-1.5 text-[11px]">{fmtDate(r.deadline)}</td>
                  <td className="px-2 py-1.5 text-end whitespace-nowrap">
                    {!r.applied && (
                      <button
                        onClick={() => act(r.id, "apply")}
                        disabled={busyId === r.id}
                        className="text-xs text-[var(--accent)] hover:underline me-2 disabled:opacity-50 min-h-[32px] px-1"
                      >
                        {t("applyCta")}
                      </button>
                    )}
                    {!r.dismissed && (
                      <button
                        onClick={() => act(r.id, "dismiss")}
                        disabled={busyId === r.id}
                        className="text-xs text-[var(--text-muted)] hover:text-red-500 disabled:opacity-50 min-h-[32px] px-1"
                      >
                        {t("dismissCta")}
                      </button>
                    )}
                    {(r.applied || r.dismissed) && (
                      <span className="text-[10px] text-[var(--text-muted)]">
                        {r.applied ? t("applied") : t("dismissed")}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );

  return (
    <div className="mt-6">
      <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
        {t("title")}
      </div>
      <ModeAwareSection projectId={projectId} guided={guided} expert={expert} />
    </div>
  );
}

function GuidedCard({
  rec, busy, onApply, onDismiss, typeLabel, priorityLabel, priorityBadgeClass,
}: {
  rec: Recommendation;
  busy: boolean;
  onApply: () => void;
  onDismiss: () => void;
  typeLabel: string;
  priorityLabel: string;
  priorityBadgeClass: string;
}) {
  const t = useTranslations("recommendations");
  return (
    <div className="card p-4 flex flex-col h-full">
      <div className="flex items-start gap-3">
        <div
          aria-hidden
          className="h-9 w-9 rounded-md bg-[var(--accent)]/10 text-[var(--accent)] flex items-center justify-center shrink-0 text-base"
        >
          {TYPE_ICON[rec.type]}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className={
              "inline-block px-1.5 py-0.5 rounded text-[10px] font-medium " +
              priorityBadgeClass
            }>{priorityLabel}</span>
            <span className="text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
              {typeLabel}
            </span>
          </div>
          <div className="font-semibold text-sm mt-1 truncate" title={rec.product}>
            {rec.product}
          </div>
          <div className="text-xs text-[var(--text-muted)] mt-1">
            {rec.reason}
          </div>
          <div className="text-xs mt-2">
            <span className="font-medium">{t("suggestedAction")}</span>{" "}
            {rec.suggested_action}
          </div>
          {rec.expected_impact && (
            <div className="text-[11px] text-[var(--text-muted)] mt-1 italic">
              {rec.expected_impact}
            </div>
          )}
          {rec.deadline && (
            <div className="text-[10px] text-[var(--text-muted)] mt-1">
              {t("deadline")} {fmtDate(rec.deadline)}
            </div>
          )}
        </div>
      </div>
      <div className="flex-1" />
      <div className="mt-3 flex items-center gap-2">
        {!rec.applied ? (
          <button
            type="button"
            onClick={onApply}
            disabled={busy}
            className="btn btn-primary text-xs disabled:opacity-50 min-h-[44px]"
          >
            {busy ? t("applyingCta") : t("markApplied")}
          </button>
        ) : (
          <span className="text-[11px] text-[var(--text-muted)] italic">
            {t("appliedAt", { date: fmtDate(rec.applied_at) })}
          </span>
        )}
        {!rec.dismissed ? (
          <button
            type="button"
            onClick={onDismiss}
            disabled={busy}
            className="btn text-xs disabled:opacity-50 min-h-[44px]"
          >
            {t("dismissCta")}
          </button>
        ) : (
          <span className="text-[11px] text-[var(--text-muted)] italic ms-auto">
            {t("dismissedAt", { date: fmtDate(rec.dismissed_at) })}
          </span>
        )}
      </div>
    </div>
  );
}

export default RecommendationsPanel;
