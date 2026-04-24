"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { getActiveDatasetId } from "@/lib/projectContext";

const TASKS = [
  { key: "drop_duplicates", label: "Drop duplicate rows" },
  { key: "trim_whitespace", label: "Trim whitespace" },
  { key: "lowercase_text", label: "Lowercase text columns" },
  { key: "drop_empty_rows", label: "Drop empty rows" },
  { key: "drop_empty_cols", label: "Drop empty columns" },
];

export default function CleanPage() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Record<string, boolean>>({ drop_duplicates: true, trim_whitespace: true });
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!getToken()) router.push("/login");
  }, [router]);

  async function run() {
    const id = getActiveDatasetId();
    if (!id) { setError("No active dataset."); return; }
    setBusy(true); setError(null);
    try {
      const r = await api("/api/clean", { method: "POST", json: { dataset_id: id, enabled: tasks } });
      setResult(r);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Clean failed"); }
    finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl">
      <span className="eyebrow">Data · Clean</span>
      <h1 className="text-2xl font-bold mt-2">Clean dataset</h1>
      <ul className="card mt-6 space-y-2">
        {TASKS.map((t) => (
          <li key={t.key}>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={!!tasks[t.key]}
                onChange={(e) => setTasks((s) => ({ ...s, [t.key]: e.target.checked }))} />
              {t.label}
            </label>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex gap-2">
        <button className="btn btn-primary" onClick={run} disabled={busy}>{busy ? "Running…" : "Run cleaning"}</button>
      </div>
      {error && <div className="text-sm text-red-600 mt-3">{error}</div>}
      {result !== null && result !== undefined && (
        <pre className="card mt-4 text-xs overflow-auto max-h-[50vh]">{JSON.stringify(result, null, 2)}</pre>
      )}
    </div>
  );
}
