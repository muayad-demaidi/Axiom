"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveProjectId, setActiveDatasetId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  MissingDatasetNotice,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

type DatasetListItem = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
  project_id: number | null;
};

type JoinType = "inner" | "left" | "right" | "outer";

type JoinSummary = {
  join_type: string;
  left_rows: number;
  right_rows: number;
  result_rows: number;
  result_cols: number;
  left_key: string;
  right_key: string;
  null_counts?: Record<string, number>;
  collisions: string[];
};

type PreviewResponse = {
  preview_only: true;
  summary: JoinSummary;
  columns: { name: string; dtype: string }[];
  preview_rows: Record<string, unknown>[];
};

type SaveResponse = {
  preview_only: false;
  summary: JoinSummary;
  dataset_id: number;
  dataset_name: string;
  project_id: number | null;
  rows: number;
  cols: number;
};

const GUIDED_OPTIONS: {
  key: JoinType;
  label: string;
  hint: string;
  venn: string;
}[] = [
  {
    key: "inner",
    label: "Only rows that match in both",
    hint: "Drop anything that doesn't have a match on the other side.",
    venn: "● ◐ ●",
  },
  {
    key: "left",
    label: "Every row from the first dataset",
    hint: "Keep all rows of the left dataset, even if no match was found.",
    venn: "●━─",
  },
  {
    key: "right",
    label: "Every row from the second dataset",
    hint: "Keep all rows of the right dataset, even if no match was found.",
    venn: "─━●",
  },
  {
    key: "outer",
    label: "Everything from both",
    hint: "Keep every row from either side; missing values become blank.",
    venn: "●━●",
  },
];

const EXPERT_OPTIONS: { key: JoinType; sql: string; hint: string }[] = [
  { key: "inner", sql: "INNER JOIN", hint: "Intersection of the keys." },
  { key: "left", sql: "LEFT JOIN", hint: "All left rows; right is NULL when absent." },
  { key: "right", sql: "RIGHT JOIN", hint: "All right rows; left is NULL when absent." },
  { key: "outer", sql: "FULL OUTER JOIN", hint: "Union of all keys; NULL where either side is missing." },
];

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw =
    (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
}

/** Trivial overlap heuristic: rank shared column names by exact match
 * first, then case-insensitive, then "endswith id" affinity. Mirrors the
 * server-side suggest_relationships scoring without re-fetching the
 * full payload — we only need a starting suggestion. */
function rankCommonKeys(left: string[], right: string[]): string[] {
  const rightSet = new Set(right);
  const rightLower = new Map(right.map((c) => [c.toLowerCase(), c] as const));
  const exact = left.filter((c) => rightSet.has(c));
  const ciOnly = left.filter(
    (c) => !rightSet.has(c) && rightLower.has(c.toLowerCase()),
  );
  const merged = [...exact, ...ciOnly];
  // Promote anything that looks like an id to the front.
  merged.sort((a, b) => {
    const ai = a.toLowerCase().endsWith("id") ? -1 : 0;
    const bi = b.toLowerCase().endsWith("id") ? -1 : 0;
    return ai - bi;
  });
  return Array.from(new Set(merged));
}

export default function JoinPage() {
  const router = useRouter();
  const projectId =
    typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);

  const [datasets, setDatasets] = useState<DatasetListItem[]>([]);
  const [leftId, setLeftId] = useState<number | null>(null);
  const [rightId, setRightId] = useState<number | null>(null);
  const [leftCols, setLeftCols] = useState<string[]>([]);
  const [rightCols, setRightCols] = useState<string[]>([]);
  const [joinKey, setJoinKey] = useState<string>("");
  // Expert users may want different keys on each side ("customer_id"
  // joined to "id" on the customers table). We fall back to joinKey
  // for both if the user only sets the simple field.
  const [leftKeyOverride, setLeftKeyOverride] = useState<string>("");
  const [rightKeyOverride, setRightKeyOverride] = useState<string>("");
  const [joinType, setJoinType] = useState<JoinType>("inner");
  const [resultName, setResultName] = useState<string>("");
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [saved, setSaved] = useState<SaveResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api<DatasetListItem[]>("/api/datasets")
      .then((rows) => {
        const scoped = projectId
          ? rows.filter((r) => r.project_id === projectId)
          : rows;
        setDatasets(scoped);
        if (scoped.length >= 1 && leftId == null) setLeftId(scoped[0].id);
        if (scoped.length >= 2 && rightId == null) setRightId(scoped[1].id);
      })
      .catch((e) => setBootError(errMessage(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router, projectId]);

  // Fetch column lists for whichever pair is selected.
  useEffect(() => {
    if (leftId == null) {
      setLeftCols([]);
      return;
    }
    api<AxiomDataset>(`/api/datasets/${leftId}`)
      .then((d) => setLeftCols(extractColumns(d)))
      .catch((e) => setError(errMessage(e)));
  }, [leftId]);
  useEffect(() => {
    if (rightId == null) {
      setRightCols([]);
      return;
    }
    api<AxiomDataset>(`/api/datasets/${rightId}`)
      .then((d) => setRightCols(extractColumns(d)))
      .catch((e) => setError(errMessage(e)));
  }, [rightId]);

  const ranked = useMemo(
    () => rankCommonKeys(leftCols, rightCols),
    [leftCols, rightCols],
  );
  // Auto-pick the strongest suggestion the first time we have one.
  useEffect(() => {
    if (!joinKey && ranked.length > 0) {
      setJoinKey(ranked[0]);
    }
  }, [ranked, joinKey]);

  const leftDs = datasets.find((d) => d.id === leftId) || null;
  const rightDs = datasets.find((d) => d.id === rightId) || null;

  async function runJoin(persist: boolean) {
    if (leftId == null || rightId == null) {
      setError("Pick two datasets first.");
      return;
    }
    if (!joinKey && (!leftKeyOverride || !rightKeyOverride)) {
      setError("Pick a column to join on.");
      return;
    }
    setBusy(true);
    setError(null);
    if (persist) setSaved(null);
    try {
      const body: Record<string, unknown> = {
        left_dataset_id: leftId,
        right_dataset_id: rightId,
        join_key: joinKey || leftKeyOverride,
        join_type: joinType,
        preview_only: !persist,
      };
      if (leftKeyOverride) body.left_key = leftKeyOverride;
      if (rightKeyOverride) body.right_key = rightKeyOverride;
      if (persist && resultName.trim()) body.result_name = resultName.trim();
      const r = await api<PreviewResponse | SaveResponse>(
        "/api/datasets/join",
        { method: "POST", json: body },
      );
      if (r.preview_only) {
        setPreview(r);
      } else {
        setSaved(r);
        setActiveDatasetId(r.dataset_id);
      }
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  // Boot guards: not enough datasets in the project to even attempt.
  if (bootError) {
    return <div className="card mt-6 text-sm text-red-600">{bootError}</div>;
  }
  if (datasets.length < 2) {
    return (
      <div className="max-w-3xl">
        <ModeAwareHeading
          projectId={projectId}
          eyebrow="Data · Join"
          guidedTitle="Combine two datasets"
          expertTitle="Dataset join builder"
          guidedSubtitle="Pick two datasets, tell us the column they share, and we'll merge them into one."
          expertSubtitle="pandas.merge with explicit join_key, suffixes=('_left','_right')."
        />
        <MissingDatasetNotice
          projectId={projectId}
          toolName="joins"
          guidedHint="Joining needs two datasets in the same project. Upload another file and come back."
        />
      </div>
    );
  }

  const guidedOption = GUIDED_OPTIONS.find((o) => o.key === joinType)!;

  return (
    <div className="max-w-4xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Data · Join"
        guidedTitle="Combine two datasets"
        expertTitle="Dataset join builder"
        guidedSubtitle="Pick two datasets, tell us the column they share, and we'll merge them into one."
        expertSubtitle="pandas.merge with explicit join_key, suffixes=('_left','_right')."
      />

      {/* Step 1+2: pick the two datasets ----------------------------- */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-6">
        <div className="card">
          <div className="text-xs font-mono text-[var(--text-muted)] mb-1">
            Step 1 · Left dataset
          </div>
          <select
            value={leftId ?? ""}
            onChange={(e) => {
              setLeftId(Number(e.target.value) || null);
              setJoinKey("");
              setPreview(null);
              setSaved(null);
            }}
            className="block w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.dataset_name} · {d.rows} rows
              </option>
            ))}
          </select>
          {leftDs && (
            <div className="text-xs text-[var(--text-muted)] mt-2">
              {leftCols.length} columns
            </div>
          )}
        </div>
        <div className="card">
          <div className="text-xs font-mono text-[var(--text-muted)] mb-1">
            Step 2 · Right dataset
          </div>
          <select
            value={rightId ?? ""}
            onChange={(e) => {
              setRightId(Number(e.target.value) || null);
              setJoinKey("");
              setPreview(null);
              setSaved(null);
            }}
            className="block w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          >
            {datasets.map((d) => (
              <option key={d.id} value={d.id}>
                {d.dataset_name} · {d.rows} rows
              </option>
            ))}
          </select>
          {rightDs && (
            <div className="text-xs text-[var(--text-muted)] mt-2">
              {rightCols.length} columns
            </div>
          )}
        </div>
      </div>

      {/* Step 3: pick the shared key ---------------------------------- */}
      <div className="card mt-4">
        <div className="text-xs font-mono text-[var(--text-muted)] mb-1">
          Step 3 · Shared column
        </div>
        {ranked.length === 0 ? (
          <div className="text-sm text-amber-600">
            No exact column-name match. Pick a column on each side below.
          </div>
        ) : (
          <select
            value={joinKey}
            onChange={(e) => {
              setJoinKey(e.target.value);
              setLeftKeyOverride("");
              setRightKeyOverride("");
              setPreview(null);
            }}
            className="block w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
          >
            {ranked.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        )}
        {mode === "expert" && (
          <div className="grid grid-cols-2 gap-2 mt-3">
            <label className="text-xs">
              Left key (override)
              <select
                value={leftKeyOverride}
                onChange={(e) => setLeftKeyOverride(e.target.value)}
                className="block mt-1 w-full px-2 py-1.5 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
              >
                <option value="">(use shared)</option>
                {leftCols.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-xs">
              Right key (override)
              <select
                value={rightKeyOverride}
                onChange={(e) => setRightKeyOverride(e.target.value)}
                className="block mt-1 w-full px-2 py-1.5 rounded border border-[var(--border)] bg-[var(--surface)] text-xs"
              >
                <option value="">(use shared)</option>
                {rightCols.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}
      </div>

      {/* Step 4: pick join type --------------------------------------- */}
      <div className="card mt-4">
        <div className="text-xs font-mono text-[var(--text-muted)] mb-2">
          Step 4 · What do you want to keep?
        </div>
        {mode === "guided" ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {GUIDED_OPTIONS.map((o) => (
              <button
                type="button"
                key={o.key}
                onClick={() => {
                  setJoinType(o.key);
                  setPreview(null);
                }}
                className={`text-left card p-3 hover:border-[var(--accent)] ${
                  joinType === o.key
                    ? "border-[var(--accent)] ring-1 ring-[var(--accent)]"
                    : ""
                }`}
              >
                <div className="text-lg font-mono">{o.venn}</div>
                <div className="text-sm font-semibold mt-1">{o.label}</div>
                <div className="text-xs text-[var(--text-muted)] mt-1">
                  {o.hint}
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {EXPERT_OPTIONS.map((o) => (
              <button
                type="button"
                key={o.key}
                onClick={() => {
                  setJoinType(o.key);
                  setPreview(null);
                }}
                className={`text-left card p-3 ${
                  joinType === o.key
                    ? "border-[var(--accent)] ring-1 ring-[var(--accent)]"
                    : ""
                }`}
              >
                <div className="font-mono text-xs">{o.sql}</div>
                <div className="text-xs text-[var(--text-muted)] mt-1">
                  {o.hint}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Step 5: preview ---------------------------------------------- */}
      <div className="card mt-4 flex items-center justify-between">
        <div>
          <div className="text-xs font-mono text-[var(--text-muted)]">
            Step 5 · Preview
          </div>
          <div className="text-xs text-[var(--text-muted)] mt-1">
            {mode === "guided"
              ? `${guidedOption.label.toLowerCase()} on “${joinKey || leftKeyOverride}”.`
              : `${joinType.toUpperCase()} on ${leftKeyOverride || joinKey} = ${rightKeyOverride || joinKey}`}
          </div>
        </div>
        <button
          className="btn btn-ghost text-sm"
          onClick={() => runJoin(false)}
          disabled={busy}
        >
          {busy && !saved ? "Computing…" : "Preview join"}
        </button>
      </div>

      {preview && (
        <div className="card mt-3">
          <div className="text-sm">
            {mode === "guided" ? (
              <>
                Result: <strong>{preview.summary.result_rows}</strong> rows ·{" "}
                <strong>{preview.summary.result_cols}</strong> columns.
              </>
            ) : (
              <>
                {preview.summary.left_rows} ⋈ {preview.summary.right_rows} →{" "}
                {preview.summary.result_rows} rows × {preview.summary.result_cols} cols
              </>
            )}
          </div>
          {preview.summary.collisions.length > 0 && (
            <div className="text-xs text-amber-700 mt-2">
              {mode === "guided"
                ? `These columns appear on both sides — we'll add "_left" / "_right" so nothing gets overwritten: ${preview.summary.collisions.join(", ")}.`
                : `Suffix collision (_left/_right): ${preview.summary.collisions.join(", ")}`}
            </div>
          )}
          {mode === "expert" && preview.summary.null_counts && (
            <details className="mt-2">
              <summary className="text-xs cursor-pointer text-[var(--text-muted)]">
                null counts per column
              </summary>
              <pre className="text-[11px] overflow-auto max-h-40 mt-1">
                {JSON.stringify(preview.summary.null_counts, null, 2)}
              </pre>
            </details>
          )}
          <div className="overflow-auto max-h-[40vh] mt-3">
            <table className="text-xs w-full">
              <thead>
                <tr className="text-left">
                  {preview.columns.map((c) => (
                    <th
                      key={c.name}
                      className="px-2 py-1 border-b border-[var(--border)] font-mono"
                    >
                      {c.name}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {preview.preview_rows.map((row, i) => (
                  <tr key={i} className="odd:bg-[var(--surface-2)]">
                    {preview.columns.map((c) => (
                      <td key={c.name} className="px-2 py-1 align-top">
                        {row[c.name] == null ? (
                          <span className="text-[var(--text-muted)]">—</span>
                        ) : (
                          String(row[c.name])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Step 6: name & save ----------------------------------------- */}
      <div className="card mt-4">
        <div className="text-xs font-mono text-[var(--text-muted)] mb-2">
          Step 6 · Name & save
        </div>
        <input
          value={resultName}
          onChange={(e) => setResultName(e.target.value)}
          placeholder={
            leftDs && rightDs
              ? `${leftDs.dataset_name} ⋈ ${rightDs.dataset_name}`
              : "joined dataset"
          }
          className="block w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
        />
        <button
          className="btn btn-primary text-sm mt-3"
          onClick={() => runJoin(true)}
          disabled={busy}
        >
          {busy && !preview ? "Saving…" : "Save as new dataset"}
        </button>
        {saved && (
          <div className="mt-3 text-sm text-green-700">
            Saved as “{saved.dataset_name}” ({saved.rows} rows ·{" "}
            {saved.cols} cols).{" "}
            <button
              className="underline"
              onClick={() => router.push("/app/upload")}
            >
              Open in Files
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="card mt-3 text-sm text-red-600">{error}</div>
      )}

      <AdvancedExpander
        projectId={projectId}
        hint="See the raw response payload (summary, columns, null counts)"
      >
        <TechnicalDetails projectId={projectId}>
          <pre className="text-[11px] overflow-auto max-h-[40vh] whitespace-pre-wrap">
            {JSON.stringify({ preview, saved }, null, 2)}
          </pre>
        </TechnicalDetails>
      </AdvancedExpander>
    </div>
  );
}
