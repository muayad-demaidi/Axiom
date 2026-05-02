"use client";
import { useMemo, useState } from "react";

type Row = Record<string, unknown>;
type Column = { name: string; dtype: string };

export function InteractiveTable({
  columns,
  rows,
  maxHeight = 320,
  onAskAboutCell,
}: {
  columns: Column[];
  rows: Row[];
  maxHeight?: number;
  onAskAboutCell?: (rowIndex: number, column: string, value: unknown) => void;
}) {
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<{ col: string; dir: "asc" | "desc" } | null>(null);
  const [highlight, setHighlight] = useState<{ ri: number; col: string } | null>(null);

  const indexed = useMemo(
    () => rows.map((r, i) => ({ row: r, origIdx: i })),
    [rows]
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return indexed;
    return indexed.filter(({ row }) =>
      columns.some((c) => String(row[c.name] ?? "").toLowerCase().includes(q))
    );
  }, [indexed, columns, query]);

  const sorted = useMemo(() => {
    if (!sortBy) return filtered;
    const { col, dir } = sortBy;
    const factor = dir === "asc" ? 1 : -1;
    return filtered.slice().sort((a, b) => {
      const av = a.row[col];
      const bv = b.row[col];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      const an = Number(av);
      const bn = Number(bv);
      if (!Number.isNaN(an) && !Number.isNaN(bn)) return (an - bn) * factor;
      return String(av).localeCompare(String(bv)) * factor;
    });
  }, [filtered, sortBy]);

  function toggleSort(col: string) {
    setSortBy((cur) => {
      if (!cur || cur.col !== col) return { col, dir: "asc" };
      if (cur.dir === "asc") return { col, dir: "desc" };
      return null;
    });
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-2" dir="rtl">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ابحث في الصفوف…"
          aria-label="البحث في صفوف الجدول"
          className="px-2 py-1 text-[12px] rounded border border-[var(--border)] bg-[var(--surface)] w-48"
          style={{ minHeight: 32 }}
        />
        <span className="text-[12px] text-[var(--text-muted)] font-mono">
          {sorted.length.toLocaleString()} / {rows.length.toLocaleString()} صف
        </span>
      </div>
      <div
        className="overflow-auto border border-[var(--border)] rounded"
        style={{ maxHeight }}
      >
        <table className="w-full text-[11px] border-collapse">
          <thead className="bg-[var(--surface-alt)] sticky top-0">
            <tr>
              {columns.map((c) => {
                const dir = sortBy?.col === c.name ? sortBy.dir : null;
                return (
                  <th
                    key={c.name}
                    onClick={() => toggleSort(c.name)}
                    className="cursor-pointer text-left px-2 py-1.5 font-semibold border-b border-[var(--border)] whitespace-nowrap"
                    title={`${c.name} · ${c.dtype}`}
                  >
                    <span>{c.name}</span>
                    <span className="text-[var(--text-muted)] ml-1">
                      {dir === "asc" ? "▲" : dir === "desc" ? "▼" : ""}
                    </span>
                    <div className="text-[9px] text-[var(--text-muted)] font-mono normal-case">
                      {c.dtype}
                    </div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {sorted.map(({ row: r, origIdx }) => (
              <tr key={origIdx} className="odd:bg-[var(--surface)] even:bg-[var(--surface-alt)]/40">
                {columns.map((c) => {
                  const v = r[c.name];
                  const isHL =
                    highlight?.ri === origIdx && highlight?.col === c.name;
                  return (
                    <td
                      key={c.name}
                      onClick={() => {
                        setHighlight({ ri: origIdx, col: c.name });
                        onAskAboutCell?.(origIdx, c.name, v);
                      }}
                      className={
                        "px-2 py-1 border-b border-[var(--border)]/50 whitespace-nowrap cursor-pointer transition-colors " +
                        (isHL
                          ? "bg-[var(--accent)]/25 ring-1 ring-inset ring-[var(--accent)]"
                          : "hover:bg-[var(--accent)]/10")
                      }
                      title={`الصف ${origIdx + 1} · ${c.name} — انقر للسؤال`}
                    >
                      {formatCell(v)}
                    </td>
                  );
                })}
              </tr>
            ))}
            {sorted.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length || 1}
                  className="text-center text-[var(--text-muted)] py-6 text-[12px]"
                >
                  لا توجد صفوف مطابقة.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v == null) return "—";
  if (typeof v === "number") {
    if (!Number.isFinite(v)) return "—";
    if (Number.isInteger(v)) return v.toLocaleString();
    return v.toLocaleString(undefined, { maximumFractionDigits: 4 });
  }
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
