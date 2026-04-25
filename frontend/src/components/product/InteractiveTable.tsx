"use client";
/**
 * Sortable, searchable table for the dataset preview. Clicking a cell
 * fires `onAskAboutCell` so the parent can pre-fill the chat input with
 * a natural-language question about that value.
 */
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
  onAskAboutCell?: (column: string, value: unknown) => void;
}) {
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState<{ col: string; dir: "asc" | "desc" } | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) =>
      columns.some((c) => String(r[c.name] ?? "").toLowerCase().includes(q))
    );
  }, [rows, columns, query]);

  const sorted = useMemo(() => {
    if (!sortBy) return filtered;
    const { col, dir } = sortBy;
    const factor = dir === "asc" ? 1 : -1;
    return filtered.slice().sort((a, b) => {
      const av = a[col];
      const bv = b[col];
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
      <div className="flex items-center justify-between gap-2 mb-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search rows…"
          className="px-2 py-1 text-xs rounded border border-[var(--border)] bg-[var(--surface)] w-48"
        />
        <span className="text-[10px] text-[var(--text-muted)] font-mono">
          {sorted.length.toLocaleString()} / {rows.length.toLocaleString()} rows
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
            {sorted.map((r, ri) => (
              <tr key={ri} className="odd:bg-[var(--surface)] even:bg-[var(--surface-alt)]/40">
                {columns.map((c) => {
                  const v = r[c.name];
                  return (
                    <td
                      key={c.name}
                      onClick={() => onAskAboutCell?.(c.name, v)}
                      className="px-2 py-1 border-b border-[var(--border)]/50 whitespace-nowrap cursor-pointer hover:bg-[var(--accent)]/10"
                      title="Ask about this value"
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
                  className="text-center text-[var(--text-muted)] py-4"
                >
                  No rows match.
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
