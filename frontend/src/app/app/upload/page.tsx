"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import type { AxiomDataset } from "@/lib/types";
import { getActiveProjectId, setActiveDatasetId } from "@/lib/projectContext";

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
  const [datasets, setDatasets] = useState<Dataset[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api<Dataset[]>("/api/datasets").then(setDatasets).catch((e: ApiError) => {
      if (e.status === 401) router.push("/login");
      else setError(e.message);
    });
  }, [router]);

  async function handleFile(file: File) {
    setBusy(true); setError(null); setProgress("Uploading…");
    try {
      const form = new FormData();
      form.append("file", file);
      const pid = getActiveProjectId();
      if (pid) form.append("project_id", String(pid));
      form.append("dataset_name", file.name.replace(/\.[^.]+$/, ""));
      const token = getToken();
      const res = await fetch("/api/datasets/upload", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const data = (await res.json()) as UploadResponse & { detail?: string };
      if (!res.ok) throw new Error(data?.detail || "Upload failed");
      setActiveDatasetId(data.id);
      setProgress(`Uploaded ${data.filename} — ${data.rows.toLocaleString()} rows × ${data.cols} cols.`);
      setDatasets((arr) => [{ id: data.id, filename: data.filename, dataset_name: data.dataset_name, rows: data.rows, cols: data.cols }, ...(arr ?? [])]);
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
      <span className="eyebrow block mt-2">Data · Upload</span>
      <h1 className="text-2xl font-bold mt-2">Upload a dataset</h1>
      <p className="text-[var(--text-muted)] mt-2">CSV or Excel, up to 200 MB on Tier 3.</p>

      <label className={`card mt-6 block border-dashed text-center py-12 cursor-pointer ${busy ? "opacity-50" : ""}`}>
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
        <p className="text-[var(--text-muted)]">Click to select or drag a CSV / .xlsx file</p>
        {progress && <p className="text-xs text-[var(--accent)] mt-2">{progress}</p>}
        {error && <p className="text-xs text-red-600 mt-2">{error}</p>}
      </label>

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
