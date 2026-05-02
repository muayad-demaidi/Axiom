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
  // 1:1 / 1:N / N:1 / N:N from the join keys' uniqueness — surfaced
  // by the backend so we can warn before the user accidentally
  // persists a runaway N:N fan-out.
  cardinality?: string;
  // True when the projected row count tripped the backend's fan-out
  // guard. The save will be refused unless we re-submit with
  // confirm_large_join: true.
  large_join?: boolean;
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

type JoinSuggestion = {
  left_column: string;
  right_column: string;
  name_score: number;
  dtype_score: number;
  overlap_score: number;
  cardinality: string;
  confidence: number;
};

type JoinSuggestResponse = {
  left_dataset_id: number;
  right_dataset_id: number;
  suggestions: JoinSuggestion[];
};

/** Fallback when the backend has no real-value suggestions to offer:
 * rank shared column *names* by exact match first, then case-insensitive,
 * then "endswith id" affinity. We only fall back to this when the
 * /api/datasets/join/suggest endpoint returns an empty list (e.g.
 * neither side has any overlapping values), so the user can still
 * pick a column manually instead of being stuck. */
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
  const [suggestions, setSuggestions] = useState<JoinSuggestion[]>([]);
  const [suggestLoading, setSuggestLoading] = useState(false);
  const [suggestError, setSuggestError] = useState<string | null>(null);
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
  // Set when the user ticks the "yes, this huge join is intentional"
  // checkbox after the preview's fan-out warning. We forward it to
  // the backend as ``confirm_large_join`` to bypass the save guard.
  const [confirmLargeJoin, setConfirmLargeJoin] = useState(false);

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

  // Pull real-value-based suggestions from the backend whenever the
  // user picks a fresh pair of datasets. The endpoint runs the same
  // ``suggest_relationships`` engine the Data Model screen uses, so
  // value overlap (Jaccard) drives the ranking instead of name match
  // alone — a column whose name matches but whose values don't won't
  // be auto-picked anymore.
  useEffect(() => {
    if (leftId == null || rightId == null) {
      setSuggestions([]);
      setSuggestError(null);
      return;
    }
    let cancelled = false;
    setSuggestLoading(true);
    setSuggestError(null);
    api<JoinSuggestResponse>("/api/datasets/join/suggest", {
      method: "POST",
      json: { left_dataset_id: leftId, right_dataset_id: rightId },
    })
      .then((r) => {
        if (cancelled) return;
        setSuggestions(r.suggestions || []);
      })
      .catch((e) => {
        if (cancelled) return;
        setSuggestError(errMessage(e));
        setSuggestions([]);
      })
      .finally(() => {
        if (!cancelled) setSuggestLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [leftId, rightId]);

  // Promote any backend-suggested same-named column-pair to the top of
  // the manual list (in addition to the suggestion banner). When the
  // backend returns nothing — e.g. value overlap is null on every pair
  // — we fall back to the trivial name-only ranking so the user can
  // still pick something.
  const ranked = useMemo(() => {
    const named = suggestions
      .filter((s) => s.left_column === s.right_column)
      .map((s) => s.left_column);
    const fallback = rankCommonKeys(leftCols, rightCols);
    const merged = [...named, ...fallback.filter((c) => !named.includes(c))];
    return Array.from(new Set(merged));
  }, [suggestions, leftCols, rightCols]);

  // The strongest suggestion we'll surface in the banner. Only auto-pick
  // it when it actually has overlapping values — otherwise we leave the
  // join key empty so the user has to make a deliberate choice and we
  // can flag the warning instead of silently selecting a bad column.
  const topSuggestion = suggestions[0] || null;
  const topSuggestionUsable =
    topSuggestion != null && topSuggestion.overlap_score > 0;
  const topSuggestionSameName =
    topSuggestion != null &&
    topSuggestion.left_column === topSuggestion.right_column;

  useEffect(() => {
    if (joinKey) return;
    if (topSuggestionUsable && topSuggestion && topSuggestionSameName) {
      setJoinKey(topSuggestion.left_column);
    } else if (topSuggestionUsable && topSuggestion && !topSuggestionSameName) {
      // Different names on each side → fill the expert overrides so
      // the join is still ready to run with one click.
      setLeftKeyOverride(topSuggestion.left_column);
      setRightKeyOverride(topSuggestion.right_column);
    } else if (!topSuggestion && ranked.length > 0) {
      setJoinKey(ranked[0]);
    }
  }, [
    joinKey,
    topSuggestion,
    topSuggestionUsable,
    topSuggestionSameName,
    ranked,
  ]);

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
      // Only forward the confirm flag when the user has actually
      // acknowledged the warning AND we're saving (preview always
      // succeeds regardless).
      if (persist && confirmLargeJoin) body.confirm_large_join = true;
      const r = await api<PreviewResponse | SaveResponse>(
        "/api/datasets/join",
        { method: "POST", json: body },
      );
      if (r.preview_only) {
        setPreview(r);
        // A new preview invalidates any prior "yes I'm sure" tick —
        // the user must re-acknowledge for the new (possibly
        // different-shape) join before saving.
        setConfirmLargeJoin(false);
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

        {/* Suggestion banner — backed by suggest_relationships ----------*/}
        {suggestLoading && (
          <div className="text-xs text-[var(--text-muted)] mb-2">
            Scoring shared columns by actual values…
          </div>
        )}
        {!suggestLoading && topSuggestion && (
          <div
            className={`mb-3 rounded border px-3 py-2 text-xs ${
              topSuggestionUsable
                ? "border-[var(--accent)] bg-[var(--surface-2)]"
                : "border-amber-400 bg-amber-50 text-amber-800"
            }`}
          >
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="font-mono text-[11px] text-[var(--text-muted)]">
                  Suggested join
                </div>
                <div className="text-sm font-semibold mt-0.5">
                  {topSuggestionSameName ? (
                    <>{topSuggestion.left_column}</>
                  ) : (
                    <>
                      {topSuggestion.left_column}{" "}
                      <span className="text-[var(--text-muted)]">↔</span>{" "}
                      {topSuggestion.right_column}
                    </>
                  )}
                </div>
                <div className="mt-1 text-[11px]">
                  {Math.round(topSuggestion.overlap_score * 100)}% overlap ·{" "}
                  {topSuggestion.cardinality}
                  {!topSuggestionUsable && (
                    <>
                      {" "}
                      · <strong>no overlapping values</strong> — pick a
                      different column or confirm this is intentional.
                    </>
                  )}
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  if (topSuggestionSameName) {
                    setJoinKey(topSuggestion.left_column);
                    setLeftKeyOverride("");
                    setRightKeyOverride("");
                  } else {
                    setJoinKey("");
                    setLeftKeyOverride(topSuggestion.left_column);
                    setRightKeyOverride(topSuggestion.right_column);
                  }
                  setPreview(null);
                }}
                className="btn btn-ghost text-xs whitespace-nowrap"
              >
                Use this
              </button>
            </div>
          </div>
        )}
        {!suggestLoading && !topSuggestion && suggestions.length === 0 &&
          leftId != null && rightId != null && !suggestError && (
            <div className="mb-2 text-xs text-amber-700">
              No strong join candidate found by value overlap. Pick a column
              manually below.
            </div>
          )}
        {suggestError && (
          <div className="mb-2 text-xs text-red-600">
            Couldn't score join candidates: {suggestError}
          </div>
        )}

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
            {preview.summary.cardinality && (
              <span className="ml-2 text-xs text-[var(--text-muted)] font-mono">
                · {preview.summary.cardinality}
              </span>
            )}
          </div>
          {preview.summary.large_join && (
            <div className="mt-3 rounded border border-amber-400 bg-amber-50 p-3 text-xs text-amber-900">
              <div className="font-semibold">
                {mode === "guided"
                  ? "This combination is unusually big."
                  : `Fan-out warning (${preview.summary.cardinality ?? "N:N"} join)`}
              </div>
              <div className="mt-1">
                {mode === "guided"
                  ? `Joining "${preview.summary.left_key}" with "${preview.summary.right_key}" produces ${preview.summary.result_rows.toLocaleString()} rows from inputs of ${preview.summary.left_rows.toLocaleString()} and ${preview.summary.right_rows.toLocaleString()}. This usually means the column you picked isn't a unique identifier — double-check before saving.`
                  : `${preview.summary.result_rows.toLocaleString()} rows projected from ${preview.summary.left_rows.toLocaleString()} × ${preview.summary.right_rows.toLocaleString()} (>5× the larger input or >1M absolute). Likely caused by joining on a non-key column.`}
              </div>
              <label className="mt-2 flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={confirmLargeJoin}
                  onChange={(e) => setConfirmLargeJoin(e.target.checked)}
                />
                <span>Yes, save this large join anyway.</span>
              </label>
            </div>
          )}
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
          disabled={
            busy ||
            // Block save until the user explicitly confirms a known
            // fan-out — mirrors the 400 the backend would otherwise
            // return, but with friendlier in-page UX.
            (preview?.summary.large_join === true && !confirmLargeJoin)
          }
        >
          {busy && !preview ? "Saving…" : "Save as new dataset"}
        </button>
        {preview?.summary.large_join && !confirmLargeJoin && (
          <div className="mt-2 text-xs text-amber-700">
            Tick the confirmation above to save this large join.
          </div>
        )}
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
