"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  GuidedActionCard,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

type TransformOp = "rename" | "drop" | "fillna" | "uppercase" | "lowercase" | "filter";

type Step = { op: TransformOp; column?: string; target?: string; value?: string };

const OPS: TransformOp[] = ["rename", "drop", "fillna", "uppercase", "lowercase", "filter"];

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw = (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
}

export default function TransformPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const [columns, setColumns] = useState<string[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [draft, setDraft] = useState<Step>({ op: "rename" });
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Guided mode targets one column at a time for the quick actions.
  const [guidedColumn, setGuidedColumn] = useState<string>("");

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setError("No active dataset."); return; }
    api<AxiomDataset>(`/api/datasets/${id}`)
      .then((d) => {
        const cols = extractColumns(d);
        setColumns(cols);
        setDraft((s) => ({ ...s, column: cols[0] }));
        setGuidedColumn(cols[0] || "");
      })
      .catch((e: unknown) => setError(errMessage(e)));
  }, [router]);

  function addStep() {
    if (!draft.op || !draft.column) return;
    setSteps((s) => [...s, draft]);
    setDraft({ op: draft.op, column: draft.column });
  }

  async function runSteps(stepsToRun: Step[]) {
    const id = getActiveDatasetId();
    if (!id) return;
    setBusy(true); setError(null);
    try {
      const r = await api("/api/transform", { method: "POST", json: { dataset_id: id, steps: stepsToRun } });
      setResult(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  async function apply() {
    await runSteps(steps);
  }

  const expertEditor = (
    <>
      <div className="card mt-6 space-y-3">
        <div className="grid grid-cols-2 gap-2">
          <label className="text-sm">
            Operation
            <select
              value={draft.op}
              onChange={(e) => setDraft((s) => ({ ...s, op: e.target.value as TransformOp }))}
              className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
            >
              {OPS.map((o) => <option key={o} value={o}>{o}</option>)}
            </select>
          </label>
          <label className="text-sm">
            Column
            <select value={draft.column ?? ""} onChange={(e) => setDraft((s) => ({ ...s, column: e.target.value }))}
              className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
              {columns.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          {draft.op === "rename" && (
            <label className="text-sm col-span-2">
              New name
              <input value={draft.target ?? ""} onChange={(e) => setDraft((s) => ({ ...s, target: e.target.value }))}
                className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" />
            </label>
          )}
          {(draft.op === "fillna" || draft.op === "filter") && (
            <label className="text-sm col-span-2">
              Value
              <input value={draft.value ?? ""} onChange={(e) => setDraft((s) => ({ ...s, value: e.target.value }))}
                className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" />
            </label>
          )}
        </div>
        <button className="btn btn-ghost" onClick={addStep}>Add step</button>
      </div>

      {steps.length > 0 && (
        <ol className="card mt-4 list-decimal list-inside text-sm space-y-1">
          {steps.map((s, i) => (
            <li key={i} className="flex justify-between">
              <code>{s.op} · {s.column}{s.target ? ` → ${s.target}` : ""}{s.value !== undefined ? ` = ${s.value}` : ""}</code>
              <button className="text-xs text-red-600" onClick={() => setSteps((arr) => arr.filter((_, j) => j !== i))}>remove</button>
            </li>
          ))}
        </ol>
      )}

      <div className="mt-4 flex gap-2">
        <button className="btn btn-primary" onClick={apply} disabled={busy || steps.length === 0}>
          {busy ? "Applying…" : "Apply steps"}
        </button>
      </div>
    </>
  );

  return (
    <div className="max-w-3xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Data · Transform"
        guidedTitle="Tidy a column"
        expertTitle="Transform Toolkit"
        guidedSubtitle="Pick a column, then choose what to do with it. Stack as many transforms as you need in the advanced view."
        expertSubtitle="Build a chain of operations and apply them to the active dataset."
      />

      {mode === "guided" ? (
        <>
          <div className="card mt-6">
            <label className="text-sm block">
              Column
              <select
                value={guidedColumn}
                onChange={(e) => setGuidedColumn(e.target.value)}
                className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm"
              >
                {columns.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
            </label>
          </div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
            <GuidedActionCard
              title="Lowercase the values"
              description="Make every value in this column lowercase so they match consistently."
              cta="Apply"
              busy={busy}
              disabled={!guidedColumn}
              onAction={() => runSteps([{ op: "lowercase", column: guidedColumn }])}
            />
            <GuidedActionCard
              title="Uppercase the values"
              description="Make every value uppercase — handy for product codes and country labels."
              cta="Apply"
              busy={busy}
              disabled={!guidedColumn}
              onAction={() => runSteps([{ op: "uppercase", column: guidedColumn }])}
            />
            <GuidedActionCard
              title="Drop this column"
              description="Remove the column entirely. Use this for IDs and noisy fields."
              cta="Drop column"
              busy={busy}
              disabled={!guidedColumn}
              onAction={() => runSteps([{ op: "drop", column: guidedColumn }])}
            />
            <GuidedActionCard
              title="Fill empty cells with 0"
              description="Replace missing values with zero so calculations don't break."
              cta="Fill blanks"
              busy={busy}
              disabled={!guidedColumn}
              onAction={() => runSteps([{ op: "fillna", column: guidedColumn, value: "0" }])}
            />
          </div>
          <AdvancedExpander
            projectId={projectId}
            hint="Chain rename / drop / fillna / filter / uppercase / lowercase steps"
          >
            {expertEditor}
          </AdvancedExpander>
        </>
      ) : (
        expertEditor
      )}

      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {result !== null && (
        <div className="card mt-4">
          {mode === "guided" ? (
            <>
              <div className="font-semibold text-sm">Done — your column has been transformed.</div>
              <TechnicalDetails projectId={projectId}>
                <pre className="text-[11px] overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
              </TechnicalDetails>
            </>
          ) : (
            <pre className="text-xs overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
          )}
        </div>
      )}
    </div>
  );
}
