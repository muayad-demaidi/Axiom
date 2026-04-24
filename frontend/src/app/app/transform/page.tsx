"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId } from "@/lib/projectContext";

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
  const [columns, setColumns] = useState<string[]>([]);
  const [steps, setSteps] = useState<Step[]>([]);
  const [draft, setDraft] = useState<Step>({ op: "rename" });
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setError("No active dataset."); return; }
    api<AxiomDataset>(`/api/datasets/${id}`)
      .then((d) => {
        const cols = extractColumns(d);
        setColumns(cols);
        setDraft((s) => ({ ...s, column: cols[0] }));
      })
      .catch((e: unknown) => setError(errMessage(e)));
  }, [router]);

  function addStep() {
    if (!draft.op || !draft.column) return;
    setSteps((s) => [...s, draft]);
    setDraft({ op: draft.op, column: draft.column });
  }

  async function apply() {
    const id = getActiveDatasetId();
    if (!id) return;
    setBusy(true); setError(null);
    try {
      const r = await api("/api/transform", { method: "POST", json: { dataset_id: id, steps } });
      setResult(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl">
      <span className="eyebrow">Data · Transform</span>
      <h1 className="text-2xl font-bold mt-2">Transform Toolkit</h1>

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

      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {result !== null && <pre className="card mt-4 text-xs overflow-auto max-h-[50vh]">{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
}
