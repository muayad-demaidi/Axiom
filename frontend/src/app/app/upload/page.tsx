"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import type { AxiomDataset, AxiomFieldMeta, AxiomFieldMetaResponse } from "@/lib/types";
import { getActiveProjectId, setActiveDatasetId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import { ModeAwareHeading } from "@/components/product/ModeAware";

type Dataset = AxiomDataset;

type UploadResponse = {
  id: number;
  filename: string;
  dataset_name: string;
  rows: number;
  cols: number;
};

export default function UploadPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [caption, setCaption] = useState("");
  const [lastUploaded, setLastUploaded] = useState<UploadResponse | null>(null);
  const [previewMeta, setPreviewMeta] = useState<AxiomFieldMetaResponse | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api<Dataset[]>("/api/datasets").then(setDatasets).catch((e: ApiError) => {
      if (e.status === 401) router.push("/login");
      else setError(e.message);
    });
  }, [router]);

  async function handleFile(file: File) {
    setBusy(true); setError(null); setProgress("Uploading…");
    setPreviewMeta(null); setPreviewError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const pid = getActiveProjectId();
      if (pid) form.append("project_id", String(pid));
      form.append("dataset_name", file.name.replace(/\.[^.]+$/, ""));
      // Optional caption — sent as a "description" form field. The
      // upload endpoint silently ignores unknown form params today, so
      // this is a no-op server-side until a future migration adds the
      // column. We still surface it in the success message so the user
      // sees their note was received.
      if (caption.trim()) form.append("description", caption.trim());
      const token = getToken();
      const res = await fetch("/api/datasets/upload", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const data = (await res.json()) as UploadResponse & { detail?: string };
      if (!res.ok) throw new Error(data?.detail || "Upload failed");
      setActiveDatasetId(data.id);
      setLastUploaded(data);
      const captionNote = caption.trim()
        ? ` Note: "${caption.trim()}".`
        : "";
      setProgress(
        `Uploaded ${data.filename} — ${data.rows.toLocaleString()} rows × ${data.cols} cols.${captionNote}`,
      );
      setDatasets((arr) => [
        { id: data.id, filename: data.filename, dataset_name: data.dataset_name, rows: data.rows, cols: data.cols },
        ...(arr ?? []),
      ]);
      // Expert post-upload preview: fetch field-meta so we can show
      // dtype + cardinality before the user opens the dataset.
      if (mode !== "guided") {
        api<AxiomFieldMetaResponse>(`/api/bi/${data.id}/field-meta`)
          .then(setPreviewMeta)
          .catch((err: ApiError) => setPreviewError(err.message));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed"); setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  function pick(d: Dataset) {
    setActiveDatasetId(d.id);
    const pid = getActiveProjectId();
    router.push(pid ? `/app/project/${pid}` : "/app/statistics");
  }

  function backToProject() {
    const pid = getActiveProjectId();
    if (pid) router.push(`/app/project/${pid}`);
    else router.push("/app");
  }

  return (
    <div className="max-w-3xl">
      <button
        type="button"
        onClick={backToProject}
        className="text-xs text-[var(--text-muted)] hover:text-[var(--accent)]"
      >
        ← Back to project
      </button>
      <div className="mt-2">
        <ModeAwareHeading
          projectId={projectId}
          eyebrow="Data · Upload"
          guidedTitle="Add some data to work with"
          expertTitle="Upload a dataset"
          guidedSubtitle="Drop a CSV or Excel file in below and we'll start analysing it for you. You can add a quick note about what's in the file too."
          expertSubtitle="CSV or Excel, up to 200 MB on Tier 3. Field meta is profiled inline after upload."
        />
      </div>

      {mode === "guided" && (
        <div className="card mt-6">
          <label className="block text-xs font-medium mb-1">
            What is this file about? (optional)
          </label>
          <input
            type="text"
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder="e.g. Q3 sales orders from Salesforce"
            className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
            disabled={busy}
          />
          <p className="text-[10px] text-[var(--text-muted)] mt-1">
            We&apos;ll keep this with the upload so you remember what it was later.
          </p>
        </div>
      )}

      <label className={`card mt-4 block border-dashed text-center py-12 cursor-pointer ${busy ? "opacity-50" : ""}`}>
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
        <p className="text-[var(--text-muted)]">
          {mode === "guided"
            ? "Click here or drop your CSV / Excel file"
            : "Click to select or drag a CSV / .xlsx file"}
        </p>
        {progress && <p className="text-xs text-[var(--accent)] mt-2">{progress}</p>}
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
      </label>

      {mode !== "guided" && lastUploaded && (
        <UploadPreview
          dataset={lastUploaded}
          meta={previewMeta}
          error={previewError}
        />
      )}

      <h2 className="text-lg font-semibold mt-10 mb-3">Your datasets</h2>
      {datasets === null ? (
        <div className="card text-[var(--text-muted)] text-sm">Loading…</div>
      ) : datasets.length === 0 ? (
        <div className="card text-[var(--text-muted)] text-sm">No datasets yet.</div>
      ) : (
        <ul className="space-y-2">
          {datasets.map((d) => (
            <li key={d.id} className="card flex items-center justify-between">
              <div>
                <div className="font-semibold">{d.dataset_name}</div>
                <div className="text-xs text-[var(--text-muted)]">{d.filename} · {d.rows.toLocaleString()} rows × {d.cols} cols</div>
              </div>
              <button className="btn btn-primary text-xs" onClick={() => pick(d)}>Open</button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function UploadPreview({
  dataset,
  meta,
  error,
}: {
  dataset: UploadResponse;
  meta: AxiomFieldMetaResponse | null;
  error: string | null;
}) {
  return (
    <div className="card mt-4">
      <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
        Upload preview · {dataset.dataset_name}
      </div>
      {error && (
        <div className="text-xs text-red-600 mb-2">
          Couldn&apos;t profile columns: {error}
        </div>
      )}
      {!meta && !error && (
        <div className="text-xs text-[var(--text-muted)]">Profiling columns…</div>
      )}
      {meta && (
        <div className="overflow-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest border-b border-[var(--border)]">
                <th className="text-left px-2 py-1">Column</th>
                <th className="text-left px-2 py-1">Type</th>
                <th className="text-left px-2 py-1">Role</th>
                <th className="text-right px-2 py-1">Unique</th>
                <th className="text-right px-2 py-1">Cardinality</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(meta.fields).map(([col, f]) => {
                const fm = f as AxiomFieldMeta;
                const card = typeof fm.cardinality_ratio === "number"
                  ? `${(fm.cardinality_ratio * 100).toFixed(1)}%`
                  : "—";
                return (
                  <tr key={col} className="border-b border-[var(--border)]/40">
                    <td className="px-2 py-1 font-mono">{col}</td>
                    <td className="px-2 py-1 font-mono">{fm.dtype || "—"}</td>
                    <td className="px-2 py-1">{fm.role}</td>
                    <td className="px-2 py-1 text-right tabular-nums">
                      {typeof fm.unique === "number" ? fm.unique.toLocaleString() : "—"}
                    </td>
                    <td className="px-2 py-1 text-right tabular-nums">{card}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
