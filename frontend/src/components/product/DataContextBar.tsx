"use client";
import Link from "next/link";
import { memo, useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Database, Loader2, Sparkles, Table2 } from "lucide-react";
import { api } from "@/lib/api";
import { errMessage, type AxiomDataset } from "@/lib/types";
import { cacheKeys, getCached, setCached } from "@/lib/workspaceCache";

type Preview = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
  columns: { name: string; dtype: string }[];
  preview: Record<string, unknown>[];
};

const PREVIEW_ROWS = 5;

function DataContextBarBase({
  projectName,
  projectId,
  datasets,
  activeDatasetId,
  onPickDataset,
  streaming,
  predictionRunning,
  rightSlot,
}: {
  projectName: string;
  projectId: number;
  datasets: AxiomDataset[];
  activeDatasetId: number | null;
  onPickDataset?: (id: number) => void;
  streaming: boolean;
  predictionRunning?: boolean;
  rightSlot?: React.ReactNode;
}) {
  const reduceMotion = useReducedMotion();
  const [openId, setOpenId] = useState<number | null>(null);
  const [showAll, setShowAll] = useState(false);

  // Order: active dataset first, then the rest by id desc.
  const ordered = [...datasets].sort((a, b) => {
    if (activeDatasetId === a.id) return -1;
    if (activeDatasetId === b.id) return 1;
    return b.id - a.id;
  });
  // When the chat hasn't picked a dataset yet (a brand-new chat), show
  // every chip up-front so the user can pick one without first having
  // to click "+N more". With one selected, collapse back to the
  // active-only chip + "+N more" affordance to keep the bar compact.
  const noneSelected = activeDatasetId == null;
  const visible = showAll || noneSelected ? ordered : ordered.slice(0, 1);
  const extra = Math.max(0, ordered.length - visible.length);

  return (
    <div className="sticky top-0 z-30 bg-[var(--surface)]/85 backdrop-blur supports-[backdrop-filter]:bg-[var(--surface)]/75 border-b border-[var(--border)]">
      <div className="px-4 sm:px-5 py-1.5 flex items-center gap-2 min-w-0">
        <div className="flex items-center gap-1.5 min-w-0 shrink-0">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)] hidden sm:inline">
            مشروع
          </span>
          <span className="text-xs font-semibold text-[var(--text)] truncate max-w-[160px]">
            {projectName}
          </span>
        </div>

        <span className="h-3.5 w-px bg-[var(--border)] hidden sm:inline-block shrink-0" />

        <div className="flex items-center gap-1.5 min-w-0 overflow-x-auto no-scrollbar">
          {datasets.length === 0 ? (
            <div className="text-[12px] text-[var(--text-muted)] inline-flex items-center gap-1.5 whitespace-nowrap" dir="rtl">
              <Database className="h-3 w-3" aria-hidden="true" />
              <span>
                لا توجد مجموعة بيانات مرتبطة —{" "}
                <Link
                  href={`/app/upload?back=/app/project/${projectId}`}
                  className="text-[var(--accent)] hover:underline"
                >
                  ارفع ملفًا الآن
                </Link>
              </span>
            </div>
          ) : (
            <>
              {noneSelected && (
                <span className="text-[12px] text-[var(--text-muted)] inline-flex items-center gap-1 whitespace-nowrap shrink-0" dir="rtl">
                  <Database className="h-3 w-3" aria-hidden="true" />
                  اختر مجموعة بيانات:
                </span>
              )}
              {visible.map((d) => (
                <DatasetChip
                  key={d.id}
                  dataset={d}
                  open={openId === d.id}
                  active={d.id === activeDatasetId}
                  onToggle={() => {
                    setOpenId((cur) => (cur === d.id ? null : d.id));
                    onPickDataset?.(d.id);
                  }}
                  onClose={() => setOpenId((cur) => (cur === d.id ? null : cur))}
                  reduceMotion={!!reduceMotion}
                />
              ))}
              {extra > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAll(true)}
                  className="text-[12px] px-2 py-0.5 rounded-full border border-dashed border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] whitespace-nowrap shrink-0"
                  aria-label={`عرض ${extra} مجموعة أخرى`}
                >
                  + {extra} أخرى
                </button>
              )}
              {showAll && ordered.length > 1 && (
                <button
                  type="button"
                  onClick={() => setShowAll(false)}
                  className="text-[12px] uppercase tracking-widest text-[var(--text-muted)] hover:text-[var(--text)] whitespace-nowrap shrink-0"
                >
                  طيّ
                </button>
              )}
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          {rightSlot}
          <StatusPill
            streaming={streaming}
            predictionRunning={!!predictionRunning}
          />
        </div>
      </div>
    </div>
  );
}

function DatasetChip({
  dataset,
  open,
  active,
  onToggle,
  onClose,
  reduceMotion,
}: {
  dataset: AxiomDataset;
  open: boolean;
  active: boolean;
  onToggle: () => void;
  onClose: () => void;
  reduceMotion: boolean;
}) {
  const wrapRef = useRef<HTMLDivElement | null>(null);

  // Outside click + Escape close.
  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (!wrapRef.current) return;
      if (!wrapRef.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  const layoutId = reduceMotion ? undefined : `dataset-chip-${dataset.id}`;

  return (
    <div className="relative shrink-0" ref={wrapRef}>
      <motion.button
        type="button"
        layoutId={layoutId}
        onClick={onToggle}
        className={`inline-flex items-center gap-1.5 text-[10px] font-medium px-2 py-0.5 rounded-full border transition-colors whitespace-nowrap ${
          active
            ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10"
            : "border-[var(--border)] text-[var(--text)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        }`}
        title={`${dataset.dataset_name || dataset.filename} — اضغط لمعاينة أول صفوف`}
        aria-expanded={open}
        aria-label={`${dataset.dataset_name || dataset.filename} — معاينة`}
      >
        <Table2 className="h-2.5 w-2.5" aria-hidden="true" />
        <span className="max-w-[160px] truncate">
          {dataset.dataset_name || dataset.filename}
        </span>
        <span className="font-mono text-[10px] text-[var(--text-muted)]">
          {dataset.rows.toLocaleString()} × {dataset.cols}
        </span>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            layoutId={layoutId}
            initial={reduceMotion ? false : { opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -4 }}
            transition={{ duration: 0.16, ease: [0.4, 0, 0.2, 1] }}
            className="absolute left-0 top-full mt-2 z-40 min-w-[320px] max-w-[min(640px,90vw)] rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-lg overflow-hidden"
          >
            <QuickPreview dataset={dataset} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/**
 * Lazy-loaded preview popover.
 *
 * Defers the network request until this component mounts (i.e. the
 * popover is actually opened) and caches the result per dataset. On
 * subsequent opens of the same dataset's preview the cached payload is
 * shown instantly with no loading flicker.
 */
function QuickPreview({ dataset }: { dataset: AxiomDataset }) {
  const cacheKey = cacheKeys.datasetPreview(dataset.id, PREVIEW_ROWS);
  const [data, setData] = useState<Preview | null>(
    () => (getCached<Preview>(cacheKey) as Preview | undefined) ?? null
  );
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(() => !getCached<Preview>(cacheKey));

  useEffect(() => {
    let cancelled = false;
    const cached = getCached<Preview>(cacheKey);
    if (cached) {
      setData(cached);
      setLoading(false);
      return;
    }
    setError(null);
    setData(null);
    setLoading(true);
    api<Preview>(`/api/datasets/${dataset.id}/preview?rows=${PREVIEW_ROWS}`)
      .then((d) => {
        if (cancelled) return;
        setCached(cacheKey, d);
        setData(d);
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
  }, [dataset.id, cacheKey]);

  return (
    <div className="text-xs" dir="rtl">
      <div className="px-3 py-2 border-b border-[var(--border)] bg-[var(--surface-alt)] flex flex-row-reverse items-center justify-between gap-2">
        <div className="font-semibold truncate">
          {dataset.dataset_name || dataset.filename}
        </div>
        <div className="font-mono text-[10px] text-[var(--text-muted)] shrink-0">
          معاينة · أول {PREVIEW_ROWS} صفوف
        </div>
      </div>
      {error ? (
        <div className="px-3 py-4 text-[var(--text-muted)]" role="alert">
          تعذّر تحميل المعاينة الآن.{" "}
          <span className="text-[10px] block mt-1 font-mono">{error}</span>
        </div>
      ) : loading || !data ? (
        <div className="px-3 py-4 text-[var(--text-muted)] inline-flex items-center gap-2" role="status" aria-live="polite">
          <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
          جاري تحضير المعاينة…
        </div>
      ) : data.preview.length === 0 ? (
        <div className="px-3 py-4 text-[var(--text-muted)]">
          مجموعة البيانات فارغة.
        </div>
      ) : (
        <div className="max-h-[260px] overflow-auto">
          <table className="text-[11px] w-max min-w-full">
            <thead>
              <tr className="bg-[var(--surface-alt)]">
                {data.columns.map((c) => (
                  <th
                    key={c.name}
                    className="px-2 py-1.5 text-left font-semibold border-b border-[var(--border)] sticky top-0 bg-[var(--surface-alt)]"
                  >
                    {c.name}
                    <div className="font-mono text-[9px] text-[var(--text-muted)] font-normal">
                      {c.dtype}
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.preview.map((row, i) => (
                <tr key={i} className="border-b border-[var(--border)] last:border-b-0">
                  {data.columns.map((c) => {
                    const v = row[c.name];
                    return (
                      <td
                        key={c.name}
                        className="px-2 py-1.5 align-top text-[var(--text)] whitespace-nowrap"
                      >
                        {formatCell(v)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") return Number.isFinite(v) ? String(v) : "—";
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

/**
 * Right-side status pill.
 *
 * Only renders when something is actually happening (assistant
 * streaming a reply, or a prediction is running). The previous
 * "IDLE" resting state was being misread as "the chat was
 * disconnected" on every fresh chat, so we now hide the pill
 * entirely at rest and reserve the slot for real, transient
 * activity. The "Analyzing…" and "جاري التنبؤ…" states keep
 * working exactly as before.
 */
function StatusPill({
  streaming,
  predictionRunning,
}: {
  streaming: boolean;
  predictionRunning: boolean;
}) {
  const reduceMotion = useReducedMotion();
  const layoutId = reduceMotion ? undefined : "axiom-status-pill";
  return (
    <AnimatePresence mode="wait" initial={false}>
      {predictionRunning ? (
        <motion.span
          key="predicting"
          dir="rtl"
          layoutId={layoutId}
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-[var(--accent)]/12 text-[var(--accent)] border border-[var(--accent)]/30 whitespace-nowrap"
        >
          <Sparkles className="h-2.5 w-2.5" />
          جاري التنبؤ…
        </motion.span>
      ) : streaming ? (
        <motion.span
          key="busy"
          layoutId={layoutId}
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="inline-flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded-full bg-[var(--accent)]/12 text-[var(--accent)] border border-[var(--accent)]/30 whitespace-nowrap"
          role="status"
          aria-live="polite"
        >
          <Sparkles className="h-2.5 w-2.5" aria-hidden="true" />
          جاري التحليل…
        </motion.span>
      ) : null}
    </AnimatePresence>
  );
}

export const DataContextBar = memo(DataContextBarBase);
