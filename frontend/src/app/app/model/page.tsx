"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId } from "@/lib/projectContext";

type Method = "kmeans" | "randomforest";

type ModelRequestBody = {
  dataset_id: number;
  method: Method;
  k?: number;
  target?: string;
};

function extractColumns(d: AxiomDataset): string[] {
  const summary = d.summary;
  const raw = (summary?.columns as Array<DatasetSummaryColumn | string> | undefined) ?? [];
  return raw.map((c) => (typeof c === "string" ? c : c.name));
}

export default function ModelPage() {
  const router = useRouter();
  const [columns, setColumns] = useState<string[]>([]);
  const [method, setMethod] = useState<Method>("kmeans");
  const [k, setK] = useState(3);
  const [target, setTarget] = useState("");
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
        setTarget(cols[0] || "");
      })
      .catch((e: unknown) => setError(errMessage(e)));
  }, [router]);

  async function run() {
    const id = getActiveDatasetId();
    if (!id) return;
    setBusy(true); setError(null);
    try {
      const body: ModelRequestBody = { dataset_id: id, method };
      if (method === "kmeans") body.k = k;
      if (method === "randomforest") body.target = target;
      const r = await api("/api/model", { method: "POST", json: body as unknown as Record<string, unknown> });
      setResult(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl">
      <span className="eyebrow">Analysis · Model</span>
      <h1 className="text-2xl font-bold mt-2">ML &amp; clustering</h1>
      <div className="card mt-6 space-y-3">
        <label className="block text-sm">
          Method
          <select value={method} onChange={(e) => setMethod(e.target.value as Method)}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
            <option value="kmeans">K-Means clustering</option>
            <option value="randomforest">Random Forest</option>
          </select>
        </label>
        {method === "kmeans" ? (
          <label className="block text-sm">
            k (clusters)
            <input type="number" min={2} max={10} value={k}
              onChange={(e) => setK(Number(e.target.value))}
              className="block mt-1 w-32 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" />
          </label>
        ) : (
          <label className="block text-sm">
            Target column
            <select value={target} onChange={(e) => setTarget(e.target.value)}
              className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm">
              {columns.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
        )}
        <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? "Running…" : "Run model"}</button>
      </div>
      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {result !== null && <pre className="card mt-4 text-xs overflow-auto max-h-[50vh]">{JSON.stringify(result, null, 2)}</pre>}
    </div>
  );
}
