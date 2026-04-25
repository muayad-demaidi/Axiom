"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import type { AxiomDataset, AxiomModelingSafeguards, DatasetSummaryColumn } from "@/lib/types";
import { errMessage } from "@/lib/types";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  GuidedActionCard,
  MissingDatasetNotice,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

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
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const [columns, setColumns] = useState<string[]>([]);
  const [method, setMethod] = useState<Method>("kmeans");
  const [k, setK] = useState(3);
  const [target, setTarget] = useState("");
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);
  const [safeguards, setSafeguards] = useState<AxiomModelingSafeguards | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    const id = getActiveDatasetId();
    if (!id) { setHasDataset(false); return; }
    setHasDataset(true);
    api<AxiomDataset>(`/api/datasets/${id}`)
      .then((d) => {
        const cols = extractColumns(d);
        setColumns(cols);
        setTarget(cols[0] || "");
      })
      .catch((e: unknown) => setError(errMessage(e)));
    // Modeling safeguards run alongside the dataset load — they
    // surface fan-out / non-unique grain risks before the user trains.
    api<AxiomModelingSafeguards>(`/api/bi/${id}/modeling`)
      .then(setSafeguards)
      .catch(() => setSafeguards(null));
  }, [router]);

  async function runWith(body: Omit<ModelRequestBody, "dataset_id">) {
    const id = getActiveDatasetId();
    if (!id) return;
    setBusy(true); setError(null);
    try {
      const r = await api("/api/model", { method: "POST", json: { dataset_id: id, ...body } as unknown as Record<string, unknown> });
      setResult(r);
    } catch (e: unknown) { setError(errMessage(e)); }
    finally { setBusy(false); }
  }

  async function run() {
    const body: Omit<ModelRequestBody, "dataset_id"> = { method };
    if (method === "kmeans") body.k = k;
    if (method === "randomforest") body.target = target;
    await runWith(body);
  }

  const expertControls = (
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
  );

  return (
    <div className="max-w-3xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Analysis · Model"
        guidedTitle="Find groups & patterns"
        expertTitle="ML & clustering"
        guidedSubtitle="Pick what you'd like to learn about your data. Open the advanced view to choose the algorithm yourself."
        expertSubtitle="K-Means clustering and Random Forest classification served from the active dataset."
      />

      {safeguards && (safeguards.fanout.length > 0 || !safeguards.grain.is_unique) && (
        <div className="mt-4 card border-amber-500/60">
          <div className="text-xs font-semibold text-amber-600 mb-1">
            Modeling safeguards
          </div>
          <ul className="text-xs space-y-0.5 list-disc list-inside text-amber-700">
            {!safeguards.grain.is_unique && (
              <li>
                Grain is not unique — {safeguards.grain.duplicate_count.toLocaleString()} duplicate rows.
                Train/test splits and cluster sizes may be skewed.
              </li>
            )}
            {safeguards.grain.is_unique && safeguards.grain.keys.length > 0 && (
              <li className="text-[var(--text-muted)]">
                Grain: <span className="font-mono">{safeguards.grain.keys.join(" + ")}</span>
              </li>
            )}
            {safeguards.fanout.map((f, i) => <li key={i}>{f.warning}</li>)}
          </ul>
        </div>
      )}

      {hasDataset === false ? (
        <MissingDatasetNotice
          projectId={projectId}
          toolName="modeling"
          guidedHint="Upload a CSV or Excel file and we'll find groups and patterns inside it."
        />
      ) : mode === "guided" ? (
        <>
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-3">
            <GuidedActionCard
              title="Group similar rows together"
              description="Auto-discover 3 natural segments in the data — useful for customer or product clustering."
              cta="Find 3 groups"
              busy={busy}
              onAction={() => runWith({ method: "kmeans", k: 3 })}
            />
            <GuidedActionCard
              title="Find a finer breakdown"
              description="Same idea, but split into 5 segments to surface smaller pockets."
              cta="Find 5 groups"
              busy={busy}
              onAction={() => runWith({ method: "kmeans", k: 5 })}
            />
            <GuidedActionCard
              title="Predict a column"
              description="Train a Random Forest to predict the chosen column from the rest of the data."
              cta="Train predictor"
              busy={busy}
              disabled={!target}
              onAction={() => runWith({ method: "randomforest", target })}
            />
          </div>
          {target && (
            <div className="text-xs text-[var(--text-muted)] mt-2">
              The predictor will model <strong>{target}</strong>. Pick a different target in the advanced view.
            </div>
          )}
          <AdvancedExpander projectId={projectId} hint="Choose method, k and target manually">
            {expertControls}
          </AdvancedExpander>
        </>
      ) : (
        expertControls
      )}

      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {result !== null && (
        <div className="card mt-4">
          {mode === "guided" ? (
            <>
              <div className="font-semibold text-sm">Model trained.</div>
              <p className="text-xs text-[var(--text-muted)] mt-1">
                Open the technical view for cluster centroids, feature importances and metrics.
              </p>
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
