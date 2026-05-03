"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { getActiveDatasetId, getActiveProjectId } from "@/lib/projectContext";
import { useMode } from "@/lib/modeContext";
import {
  AdvancedExpander,
  GuidedActionCard,
  MissingDatasetNotice,
  ModeAwareHeading,
  TechnicalDetails,
} from "@/components/product/ModeAware";

const TASKS = [
  { key: "drop_duplicates", label: "Drop duplicate rows" },
  { key: "trim_whitespace", label: "Trim whitespace" },
  { key: "lowercase_text", label: "Lowercase text" },
  { key: "drop_empty_rows", label: "Drop empty rows" },
  { key: "drop_empty_cols", label: "Drop empty columns" },
];

// Guided one-click presets — opinionated bundles of the same checklist
// the Expert view exposes. Keeping them inline keeps the wiring trivial.
const PRESETS: Record<string, { label: string; tasks: Record<string, boolean>; desc: string }> = {
  tidy: {
    label: "Tidy data",
    desc: "Drop duplicates, trim whitespace, drop empty rows/columns. Safe defaults for most files.",
    tasks: { drop_duplicates: true, trim_whitespace: true, drop_empty_rows: true, drop_empty_cols: true },
  },
  text: {
    label: "Normalize text",
    desc: "Lowercase text and trim whitespace for consistent label matching across rows.",
    tasks: { trim_whitespace: true, lowercase_text: true },
  },
  shrink: {
    label: "Shrink file",
    desc: "Drop duplicate rows and empty columns to make the data lighter and faster to view.",
    tasks: { drop_duplicates: true, drop_empty_cols: true },
  },
};

export default function CleanPage() {
  const router = useRouter();
  const projectId = typeof window !== "undefined" ? getActiveProjectId() : null;
  const { mode } = useMode(projectId);
  const [tasks, setTasks] = useState<Record<string, boolean>>({ drop_duplicates: true, trim_whitespace: true });
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [hasDataset, setHasDataset] = useState<boolean | null>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    setHasDataset(getActiveDatasetId() != null);
  }, [router]);

  async function run(overrideTasks?: Record<string, boolean>) {
    const id = getActiveDatasetId();
    if (!id) { setHasDataset(false); return; }
    const enabled = overrideTasks ?? tasks;
    setBusy(true); setError(null);
    try {
      const r = await api("/api/clean", { method: "POST", json: { dataset_id: id, enabled } });
      setResult(r);
    } catch (e: unknown) { setError(e instanceof Error ? e.message : "Clean failed"); }
    finally { setBusy(false); }
  }

  const expertControls = (
    <ul className="card mt-6 space-y-2" dir="rtl">
      {TASKS.map((t) => (
        <li key={t.key}>
          <label className="flex items-center gap-2 text-sm" style={{ minHeight: 32 }}>
            <input type="checkbox" checked={!!tasks[t.key]} className="h-4 w-4"
              onChange={(e) => setTasks((s) => ({ ...s, [t.key]: e.target.checked }))} />
            {t.label}
          </label>
        </li>
      ))}
    </ul>
  );

  const expertControlsCompact = (
    <ul className="space-y-2" dir="rtl">
      {TASKS.map((t) => (
        <li key={t.key}>
          <label className="flex items-center gap-2 text-sm" style={{ minHeight: 32 }}>
            <input type="checkbox" checked={!!tasks[t.key]} className="h-4 w-4"
              onChange={(e) => setTasks((s) => ({ ...s, [t.key]: e.target.checked }))} />
            {t.label}
          </label>
        </li>
      ))}
      <li>
        <button className="btn btn-ghost text-[12px]" style={{ minHeight: 32 }} onClick={() => run()} disabled={busy}>
          {busy ? "Running…" : "Run with these options"}
        </button>
      </li>
    </ul>
  );

  return (
    <div className="max-w-3xl">
      <ModeAwareHeading
        projectId={projectId}
        eyebrow="Data · Clean"
        guidedTitle="Clean up your data"
        expertTitle="Clean dataset"
        guidedSubtitle="Pick a one-click clean-up. We'll show you exactly what changed."
        expertSubtitle="Toggle individual cleaning steps and run them against the active dataset."
      />

      {hasDataset === false ? (
        <MissingDatasetNotice
          projectId={projectId}
          toolName="cleaning"
          guidedHint="Upload a CSV or Excel file and we'll show one-click cleaning options."
        />
      ) : mode === "guided" ? (
        <>
          <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-3" dir="rtl">
            {Object.entries(PRESETS).map(([key, p]) => (
              <GuidedActionCard
                key={key}
                title={p.label}
                description={p.desc}
                cta="Run"
                busy={busy}
                onAction={() => run(p.tasks)}
              />
            ))}
          </div>
          <AdvancedExpander
            projectId={projectId}
            hint="Pick cleaning steps precisely"
          >
            {expertControlsCompact}
          </AdvancedExpander>
        </>
      ) : (
        <>
          {expertControls}
          <div className="mt-4 flex gap-2" dir="rtl">
            <button className="btn btn-primary" style={{ minHeight: 44 }} onClick={() => run()} disabled={busy}>
              {busy ? "Cleaning…" : "Start cleaning"}
            </button>
          </div>
        </>
      )}

      {error && (
        <div
          className="text-sm text-red-600 mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2"
          role="alert"
          dir="rtl"
        >
          {error}
        </div>
      )}
      {result !== null && result !== undefined && (
        <div className="card mt-4" dir="rtl">
          <div className="font-semibold text-sm">Cleaned ✓</div>
          <p className="text-[12px] text-[var(--text-muted)] mt-1">
            {mode === "guided"
              ? "Your data is cleaned. Technical details below if needed."
              : "Cleaning complete. Full server response below."}
          </p>
          <TechnicalDetails projectId={projectId}>
            <pre className="text-[11px] overflow-auto max-h-[50vh] whitespace-pre-wrap">{JSON.stringify(result, null, 2)}</pre>
          </TechnicalDetails>
        </div>
      )}
    </div>
  );
}
