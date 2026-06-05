"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
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

type AutoLinkNotification = {
  id: number;
  project_id: number;
  kind: string;
  summary: string;
  payload: {
    added_count?: number;
    relationship_ids?: number[];
    joins?: Array<{
      relationship_id: number;
      left_table: string;
      left_column: string;
      right_table: string;
      right_column: string;
      cardinality: string;
      confidence: number;
    }>;
    trigger_dataset_id?: number | null;
    trigger_dataset_name?: string | null;
  };
  dismissed: boolean;
  created_at: string | null;
};

export default function UploadPage() {
  const router = useRouter();
  const t = useTranslations("upload");
  const locale = useLocale();
  const dir: "rtl" | "ltr" = locale === "ar" ? "rtl" : "ltr";
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
  const [autoLink, setAutoLink] = useState<AutoLinkNotification | null>(null);
  const seenNotificationIdsRef = useRef<Set<number>>(new Set());
  const pollTimersRef = useRef<number[]>([]);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    api<Dataset[]>("/api/datasets").then(setDatasets).catch((e: ApiError) => {
      if (e.status === 401) router.push("/login");
      else setError(e.message);
    });
  }, [router]);

  useEffect(() => {
    const pid = projectId;
    if (!pid) return;
    api<{ items: AutoLinkNotification[] }>(
      `/api/projects/${pid}/upload-notifications`,
    )
      .then(({ items }) => {
        for (const n of items) seenNotificationIdsRef.current.add(n.id);
      })
      .catch(() => {});
  }, [projectId]);

  useEffect(() => {
    return () => {
      for (const tid of pollTimersRef.current) window.clearTimeout(tid);
      pollTimersRef.current = [];
    };
  }, []);

  function pollForAutoLink(pid: number) {
    const delays = [600, 1500, 3000, 6000];
    for (const tid of pollTimersRef.current) window.clearTimeout(tid);
    pollTimersRef.current = delays.map((ms) =>
      window.setTimeout(async () => {
        try {
          const { items } = await api<{ items: AutoLinkNotification[] }>(
            `/api/projects/${pid}/upload-notifications`,
          );
          const fresh = items.find(
            (n) =>
              n.kind === "auto_link" &&
              !seenNotificationIdsRef.current.has(n.id),
          );
          if (fresh) {
            seenNotificationIdsRef.current.add(fresh.id);
            setAutoLink(fresh);
            for (const tid of pollTimersRef.current) {
              window.clearTimeout(tid);
            }
            pollTimersRef.current = [];
          }
        } catch {}
      }, ms),
    );
  }

  async function dismissAutoLink() {
    const note = autoLink;
    if (!note) return;
    setAutoLink(null);
    try {
      await api(
        `/api/projects/${note.project_id}/upload-notifications/${note.id}/dismiss`,
        { method: "POST" },
      );
    } catch {}
  }

  function openAutoLinkInWorkspace() {
    const note = autoLink;
    if (!note) return;
    const ids = (note.payload.relationship_ids ?? []).join(",");
    const qs = new URLSearchParams({ open_drawer: "model" });
    if (ids) qs.set("highlight_rels", ids);
    if (note.id) qs.set("notification", String(note.id));
    router.push(`/app/project/${note.project_id}?${qs.toString()}`);
  }

  async function handleFile(file: File) {
    setBusy(true); setError(null); setProgress(t("uploading"));
    setPreviewMeta(null); setPreviewError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const pid = getActiveProjectId();
      if (pid) form.append("project_id", String(pid));
      form.append("dataset_name", file.name.replace(/\.[^.]+$/, ""));
      if (caption.trim()) form.append("description", caption.trim());
      const token = getToken();
      const res = await fetch("/api/datasets/upload", {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      const data = (await res.json()) as UploadResponse & { detail?: string };
      if (!res.ok) throw new Error(data?.detail || t("uploadFailed"));
      setActiveDatasetId(data.id);
      setLastUploaded(data);
      const captionNote = caption.trim() ? t("savedNote", { caption: caption.trim() }) : "";
      setProgress(
        t("savedOk", {
          filename: data.filename,
          rows: data.rows.toLocaleString(),
          cols: data.cols,
          captionNote,
        }),
      );
      const boundProjectId = pid ? Number(pid) : null;
      if (boundProjectId) pollForAutoLink(boundProjectId);
      setDatasets((arr) => [
        { id: data.id, filename: data.filename, dataset_name: data.dataset_name, rows: data.rows, cols: data.cols },
        ...(arr ?? []),
      ]);
      if (mode !== "guided") {
        api<AxiomFieldMetaResponse>(`/api/bi/${data.id}/field-meta`)
          .then(setPreviewMeta)
          .catch((err: ApiError) => setPreviewError(err.message));
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("uploadFailedGeneric")); setProgress(null);
    } finally {
      setBusy(false);
    }
  }

  async function loadSample() {
    setBusy(true); setError(null); setProgress(t("trySampleLoading"));
    try {
      const pid = getActiveProjectId();
      const data = await api<UploadResponse>(
        `/api/datasets/sample${pid ? `?project_id=${pid}` : ""}`,
        { method: "POST" },
      );
      setActiveDatasetId(data.id);
      setDatasets((arr) => [
        { id: data.id, filename: data.filename, dataset_name: data.dataset_name, rows: data.rows, cols: data.cols },
        ...(arr ?? []),
      ]);
      // Straight to the analysis surface — the whole point is a fast aha.
      router.push(pid ? `/app/project/${pid}` : "/app/statistics");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : t("uploadFailedGeneric"));
      setProgress(null);
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
    <div className="max-w-3xl" dir={dir}>
      <button
        type="button"
        onClick={backToProject}
        className="text-[12px] text-[var(--text-muted)] hover:text-[var(--accent)] inline-flex items-center"
        style={{ minHeight: 32, paddingInline: 8 }}
      >
        {t("backToProject")}
      </button>
      <div className="mt-2">
        <ModeAwareHeading
          projectId={projectId}
          eyebrow={t("eyebrow")}
          guidedTitle={t("guidedTitle")}
          expertTitle={t("expertTitle")}
          guidedSubtitle={t("guidedSubtitle")}
          expertSubtitle={t("expertSubtitle")}
        />
      </div>

      {mode === "guided" && (
        <div className="card mt-6">
          <label className="block text-[12px] font-medium mb-1">
            {t("captionLabel")}
          </label>
          <input
            type="text"
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder={t("captionPlaceholder")}
            className="w-full border border-[var(--border)] rounded px-3 py-2 text-sm bg-transparent"
            style={{ minHeight: 44 }}
            disabled={busy}
          />
          <p className="text-[12px] text-[var(--text-muted)] mt-1">
            {t("captionHelp")}
          </p>
        </div>
      )}

      {autoLink && (
        <AutoLinkToast
          notification={autoLink}
          onOpen={openAutoLinkInWorkspace}
          onDismiss={dismissAutoLink}
          dir={dir}
        />
      )}

      <label
        className={`card mt-4 block border-dashed text-center py-12 cursor-pointer ${busy ? "opacity-50" : ""}`}
        style={{ minHeight: 160 }}
      >
        <input
          type="file"
          accept=".csv,.xlsx,.xls"
          className="hidden"
          disabled={busy}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
        <p className="text-[var(--text-muted)] text-sm">
          {mode === "guided" ? t("dropAreaGuided") : t("dropAreaExpert")}
        </p>
        {progress && <p className="text-[12px] text-[var(--accent)] mt-2" role="status" aria-live="polite">{progress}</p>}
        {error && <p className="text-[12px] text-red-600 mt-2" role="alert">{error}</p>}
      </label>

      <div className="mt-3 flex flex-col items-center gap-1.5 text-center">
        <button
          type="button"
          onClick={loadSample}
          disabled={busy}
          className="btn btn-ghost text-[13px]"
          style={{ minHeight: 40 }}
        >
          ✨ {t("trySample")}
        </button>
        <p className="text-[12px] text-[var(--text-muted)] max-w-md">
          {t("trySampleHelp")}
        </p>
      </div>

      {mode !== "guided" && lastUploaded && (
        <UploadPreview
          dataset={lastUploaded}
          meta={previewMeta}
          error={previewError}
          dir={dir}
        />
      )}

      <h2 className="text-lg font-semibold mt-10 mb-3">{t("yourDatasets")}</h2>
      {datasets === null ? (
        <div
          className="card text-[var(--text-muted)] text-sm inline-flex items-center gap-2"
          role="status"
          aria-live="polite"
        >
          <span
            className="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]"
            aria-hidden="true"
          />
          {t("loading")}
        </div>
      ) : datasets.length === 0 ? (
        <div className="card text-[var(--text-muted)] text-sm text-center py-8">
          <div className="text-2xl mb-2" aria-hidden="true">📂</div>
          <div className="font-medium text-[var(--text)]">{t("noDatasetsTitle")}</div>
          <div className="text-[12px] mt-1">{t("noDatasetsSubtitle")}</div>
        </div>
      ) : (
        <ul className="space-y-2">
          {datasets.map((d) => {
            const p = d.join_provenance ?? null;
            const left = p?.left_dataset_name || (p ? `#${p.left_dataset_id}` : "");
            const right = p?.right_dataset_name || (p ? `#${p.right_dataset_id}` : "");
            const keyLabel = p
              ? p.left_key === p.right_key
                ? p.left_key
                : `${p.left_key} = ${p.right_key}`
              : "";
            return (
              <li key={d.id} className="card flex items-center justify-between gap-3">
                <div>
                  <div className="font-semibold flex items-center gap-2 flex-wrap">
                    {d.dataset_name}
                    {p && (
                      <span
                        title={t("linkedTooltip", { left, right, keyLabel, joinType: p.join_type })}
                        className="text-[12px] uppercase tracking-wide font-mono px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)]"
                      >
                        {t("linkedBadge")}
                      </span>
                    )}
                  </div>
                  <div className="text-[12px] text-[var(--text-muted)]">
                    {t("rowsCols", { filename: d.filename, rows: d.rows.toLocaleString(), cols: d.cols })}
                  </div>
                  {p && (
                    <div className="text-[12px] text-[var(--text-muted)] mt-1">
                      {t("linkedFrom")} <strong>{left}</strong> ⋈ <strong>{right}</strong> {t("linkedJoinOn")}{" "}
                      <code className="font-mono">{keyLabel}</code> · {p.join_type}
                    </div>
                  )}
                </div>
                <button className="btn btn-primary text-[12px]" style={{ minHeight: 44 }} onClick={() => pick(d)}>
                  {t("openCta")}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function AutoLinkToast({
  notification,
  onOpen,
  onDismiss,
  dir,
}: {
  notification: AutoLinkNotification;
  onOpen: () => void;
  onDismiss: () => void;
  dir: "rtl" | "ltr";
}) {
  const t = useTranslations("upload");
  const joins = notification.payload.joins ?? [];
  const head = joins.slice(0, 2);
  const moreCount = Math.max(0, joins.length - head.length);
  return (
    <div
      role="status"
      aria-live="polite"
      className="card mt-4 border-[var(--accent)]/40 bg-[var(--accent)]/5"
      dir={dir}
    >
      <div className="flex items-start gap-3">
        <div className="text-[var(--accent)] text-base leading-none mt-0.5" aria-hidden>
          ↔
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[12px] uppercase tracking-widest font-mono text-[var(--accent)] mb-1">
            {t("autoLinkEyebrow")}
          </div>
          <div className="text-sm">
            {head.length === 0
              ? notification.summary
              : (
                <>
                  {t("autoLinkLeadIn")}
                  {head.map((j, i) => (
                    <span key={j.relationship_id}>
                      {i > 0 ? ` ${t("autoLinkConnector")} ` : " "}
                      <span className="font-mono text-[12px]">
                        {j.left_table}.{j.left_column}
                      </span>{" "}
                      <span className="text-[var(--text-muted)]">↔</span>{" "}
                      <span className="font-mono text-[12px]">
                        {j.right_table}.{j.right_column}
                      </span>
                    </span>
                  ))}
                  {moreCount > 0 ? (
                    <span className="text-[var(--text-muted)]">
                      {" "}{t("autoLinkMore", { count: moreCount })}
                    </span>
                  ) : null}{" "}
                  {t("autoLinkAuto")}
                </>
              )}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={onOpen}
              className="text-[12px] px-2 py-1 rounded border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)]/10"
              style={{ minHeight: 32 }}
            >
              {t("autoLinkReview")}
            </button>
            <button
              type="button"
              onClick={onDismiss}
              className="text-[12px] px-2 py-1 rounded border border-[var(--border)] text-[var(--text-muted)] hover:bg-[var(--surface-alt)]"
              style={{ minHeight: 32 }}
            >
              {t("autoLinkClose")}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function UploadPreview({
  dataset,
  meta,
  error,
  dir,
}: {
  dataset: UploadResponse;
  meta: AxiomFieldMetaResponse | null;
  error: string | null;
  dir: "rtl" | "ltr";
}) {
  const t = useTranslations("upload");
  return (
    <div className="card mt-4" dir={dir}>
      <div className="text-[12px] uppercase tracking-widest text-[var(--text-muted)] mb-2">
        {t("previewEyebrow", { name: dataset.dataset_name })}
      </div>
      {error && (
        <div className="text-[12px] text-red-600 mb-2" role="alert">
          {t("previewError", { error })}
        </div>
      )}
      {!meta && !error && (
        <div
          className="text-[12px] text-[var(--text-muted)] inline-flex items-center gap-2"
          role="status"
          aria-live="polite"
        >
          <span
            className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-[var(--accent)]/30 border-t-[var(--accent)]"
            aria-hidden="true"
          />
          {t("previewLoading")}
        </div>
      )}
      {meta && (
        <div className="overflow-auto">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="text-[var(--text-muted)] text-[12px] uppercase tracking-widest border-b border-[var(--border)]">
                <th className="text-start px-2 py-1">{t("colHeader")}</th>
                <th className="text-start px-2 py-1">{t("typeHeader")}</th>
                <th className="text-start px-2 py-1">{t("roleHeader")}</th>
                <th className="text-start px-2 py-1">{t("uniqueHeader")}</th>
                <th className="text-start px-2 py-1">{t("diversityHeader")}</th>
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
                    <td className="px-2 py-1 text-end tabular-nums">
                      {typeof fm.unique === "number" ? fm.unique.toLocaleString() : "—"}
                    </td>
                    <td className="px-2 py-1 text-end tabular-nums">{card}</td>
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
