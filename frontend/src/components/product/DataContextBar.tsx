"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { Database, Loader2, Sparkles, Table2 } from "lucide-react";
import { api } from "@/lib/api";
import { errMessage, type AxiomDataset } from "@/lib/types";

type Preview = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
  columns: { name: string; dtype: string }[];
  preview: Record<string, unknown>[];
};

export function DataContextBar({
  projectName,
  projectId,
  datasets,
  activeDatasetId,
  onPickDataset,
  streaming,
  rightSlot,
}: {
  projectName: string;
  projectId: number;
  datasets: AxiomDataset[];
  activeDatasetId: number | null;
  onPickDataset?: (id: number) => void;
  streaming: boolean;
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
  const visible = showAll ? ordered : ordered.slice(0, 1);
  const extra = Math.max(0, ordered.length - visible.length);

  return (
    <div className="sticky top-0 z-30 bg-[var(--surface)]/85 backdrop-blur supports-[backdrop-filter]:bg-[var(--surface)]/75 border-b border-[var(--border)]">
      <div className="px-4 sm:px-6 py-2.5 flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--text-muted)] hidden sm:inline">
            Project
          </span>
          <span className="text-sm font-semibold text-[var(--text)] truncate max-w-[180px]">
            {projectName}
          </span>
        </div>

        <span className="h-4 w-px bg-[var(--border)] hidden sm:inline-block" />

        <div className="flex items-center gap-2 flex-wrap min-w-0">
          {datasets.length === 0 ? (
            <div className="text-xs text-[var(--text-muted)] inline-flex items-center gap-1.5">
              <Database className="h-3.5 w-3.5" />
              <span>
                No dataset attached —{" "}
                <Link
                  href={`/app/upload?back=/app/project/${projectId}`}
                  className="text-[var(--accent)] hover:underline"
                >
                  upload one to start
                </Link>
              </span>
            </div>
          ) : (
            <>
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
                  className="text-[11px] px-2 py-1 rounded-full border border-dashed border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
                >
                  +{extra} more
                </button>
              )}
              {showAll && ordered.length > 1 && (
                <button
                  type="button"
                  onClick={() => setShowAll(false)}
                  className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] hover:text-[var(--text)]"
                >
                  collapse
                </button>
              )}
            </>
          )}
        </div>

        <div className="ml-auto flex items-center gap-3">
          {rightSlot}
          <StatusPill streaming={streaming} />
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
    <div className="relative" ref={wrapRef}>
      <motion.button
        type="button"
        layoutId={layoutId}
        onClick={onToggle}
        className={`inline-flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1 rounded-full border transition-colors ${
          active
            ? "border-[var(--accent)] text-[var(--accent)] bg-[var(--accent)]/10"
            : "border-[var(--border)] text-[var(--text)] hover:border-[var(--accent)] hover:text-[var(--accent)]"
        }`}
        title={`${dataset.dataset_name || dataset.filename} · click to peek at the first rows`}
        aria-expanded={open}
      >
        <Table2 className="h-3 w-3" />
        <span className="max-w-[180px] truncate">
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

function QuickPreview({ dataset }: { dataset: AxiomDataset }) {
  const [data, setData] = useState<Preview | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    setData(null);
    api<Preview>(`/api/datasets/${dataset.id}/preview?rows=5`)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .catch((e) => {
        if (!cancelled) setError(errMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [dataset.id]);

  return (
    <div className="text-xs">
      <div className="px-3 py-2 border-b border-[var(--border)] bg-[var(--surface-alt)] flex items-center justify-between gap-2">
        <div className="font-semibold truncate">
          {dataset.dataset_name || dataset.filename}
        </div>
        <div className="font-mono text-[10px] text-[var(--text-muted)] shrink-0">
          peek · first 5 rows
        </div>
      </div>
      {error ? (
        <div className="px-3 py-4 text-[var(--text-muted)]">
          Couldn&apos;t load a preview right now.{" "}
          <span className="text-[10px] block mt-1 font-mono">{error}</span>
        </div>
      ) : !data ? (
        <div className="px-3 py-4 text-[var(--text-muted)] inline-flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Loading preview…
        </div>
      ) : data.preview.length === 0 ? (
        <div className="px-3 py-4 text-[var(--text-muted)]">
          This dataset is empty.
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

function StatusPill({ streaming }: { streaming: boolean }) {
  const reduceMotion = useReducedMotion();
  const layoutId = reduceMotion ? undefined : "axiom-status-pill";
  return (
    <AnimatePresence mode="wait" initial={false}>
      {streaming ? (
        <motion.span
          key="busy"
          layoutId={layoutId}
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest px-2.5 py-1 rounded-full bg-[var(--accent)]/12 text-[var(--accent)] border border-[var(--accent)]/30"
        >
          <Sparkles className="h-3 w-3" />
          Analyzing…
        </motion.span>
      ) : (
        <motion.span
          key="idle"
          layoutId={layoutId}
          initial={reduceMotion ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={reduceMotion ? { opacity: 0 } : { opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="inline-flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-widest px-2.5 py-1 rounded-full bg-[var(--surface-alt)] text-[var(--text-muted)] border border-[var(--border)]"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--text-muted)]" />
          Idle
        </motion.span>
      )}
    </AnimatePresence>
  );
}
