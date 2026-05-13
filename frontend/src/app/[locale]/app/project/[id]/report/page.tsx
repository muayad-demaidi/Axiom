"use client";
/**
 * Final Report side tab — live preview + Download PDF for one chat
 * session. Renders the same artifact payloads we render in the drawer
 * (charts, predictions, clusters, profile, insights), an LLM-synthesised
 * executive summary, ±10/±25 % what-if recommendations, a Q&A appendix,
 * and a literal PDF mini-preview that mirrors the export endpoint.
 *
 * Headings are bilingual (English / Levantine Arabic) per project spec.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { api, ApiError, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { ChartRenderer, type ChartPayload } from "@/components/product/Charts";
import { PredictionCard, type PredictionResult } from "@/components/product/PredictionCard";
import type { Artifact } from "@/components/product/ArtifactDrawer";

type WhatIfRow = {
  shift_pct: number;
  new_value: number;
  predicted_delta: number;
  predicted_value: number;
};
type WhatIfFeature = { feature: string; baseline_value: number; rows: WhatIfRow[] };
type WhatIf = { title: string; target: string | null; rows: WhatIfFeature[] };

type Synthesis = {
  executive_summary?: string;
  key_findings?: string[];
  recommendations?: string[];
};

type ReportPayload = {
  session: { id: number; project_id: number; title: string; created_at: string | null };
  datasets: { id: number; name: string; rows: number; cols: number }[];
  artifacts: Record<string, Artifact[]>;
  qa: { id: number; user: string; ai: string; ts: string | null }[];
  synthesis?: Synthesis;
  what_if?: WhatIf[];
  generated_at: string;
};

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const search = useSearchParams();
  const router = useRouter();
  const projectId = Number(params.id);
  const sessionId = Number(search.get("session"));

  const [pinnedOnly, setPinnedOnly] = useState(true);
  const [report, setReport] = useState<ReportPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const previewUrlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    if (!Number.isFinite(sessionId)) {
      setError("No chat session selected.");
      return;
    }
    let cancelled = false;
    setReport(null);
    api<ReportPayload>(
      `/api/chats/${sessionId}/report?pinned_only=${pinnedOnly ? "true" : "false"}`
    )
      .then((r) => {
        if (!cancelled) setReport(r);
      })
      .catch((e) => {
        if (cancelled) return;
        if (e instanceof ApiError && e.status === 401) router.push("/login");
        else setError(errMessage(e));
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, pinnedOnly, router]);

  // Live PDF mini-preview — fetch the same export the Download button
  // hits and embed it as a blob URL. Refreshes whenever the report
  // payload or pinned-only toggle changes.
  useEffect(() => {
    if (!Number.isFinite(sessionId) || !report) return;
    let cancelled = false;
    setPreviewLoading(true);
    const token = getToken();
    fetch(
      `/api/chats/${sessionId}/report.pdf?pinned_only=${pinnedOnly ? "true" : "false"}`,
      {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      }
    )
      .then(async (res) => {
        if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
        return res.blob();
      })
      .then((blob) => {
        if (cancelled) return;
        const url = URL.createObjectURL(blob);
        if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = url;
        setPreviewUrl(url);
      })
      .catch((e) => {
        if (!cancelled) setError(errMessage(e));
      })
      .finally(() => {
        if (!cancelled) setPreviewLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [sessionId, pinnedOnly, report]);

  useEffect(() => () => {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
  }, []);

  async function downloadPdf() {
    if (!Number.isFinite(sessionId)) return;
    setDownloading(true);
    try {
      const token = getToken();
      const res = await fetch(
        `/api/chats/${sessionId}/report.pdf?pinned_only=${pinnedOnly ? "true" : "false"}`,
        {
          method: "POST",
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        }
      );
      if (!res.ok) throw new Error(await res.text().catch(() => res.statusText));
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `axiom-final-report-${sessionId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setDownloading(false);
    }
  }

  const totalArtifacts = useMemo(() => {
    if (!report) return 0;
    return Object.values(report.artifacts || {}).reduce(
      (n, arr) => n + (arr?.length || 0),
      0
    );
  }, [report]);

  const pinnedCount = useMemo(() => {
    if (!report) return 0;
    return Object.values(report.artifacts || {}).reduce(
      (n, arr) => n + (arr || []).filter((a) => a.pinned).length,
      0
    );
  }, [report]);

  return (
    <div className="-m-6 min-h-[calc(100vh-3.5rem)] bg-[var(--surface)]">
      <div className="border-b border-[var(--border)] px-6 py-4 flex items-center justify-between gap-4 sticky top-14 bg-[var(--surface)]/95 backdrop-blur z-10">
        <div>
          <span className="eyebrow">Final report</span>
          <h1 className="text-xl font-semibold mt-0.5">
            {report?.session.title || "Loading…"}
          </h1>
          {report && (
            <div className="mt-1 flex items-center gap-2 text-[11px] font-mono">
              <span className="px-2 py-0.5 rounded-full border border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)]">
                📌 {pinnedCount} pinned
              </span>
              <span className="text-[var(--text-muted)]">
                of {totalArtifacts} total
              </span>
            </div>
          )}
        </div>
        <div className="flex items-center gap-3">
          <label className="text-xs flex items-center gap-1.5 text-[var(--text-muted)]">
            <input
              type="checkbox"
              checked={pinnedOnly}
              onChange={(e) => setPinnedOnly(e.target.checked)}
              className="accent-[var(--accent)]"
            />
            Pinned only
          </label>
          <Link
            href={`/app/project/${projectId}?session=${sessionId}`}
            className="btn btn-ghost text-xs"
          >
            Back to chat
          </Link>
          <button
            className="btn btn-primary text-sm"
            onClick={downloadPdf}
            disabled={downloading || !report}
          >
            {downloading ? "Building…" : "Download PDF"}
          </button>
        </div>
      </div>

      <div className="px-6 py-6 max-w-6xl mx-auto grid lg:grid-cols-[minmax(0,1fr)_420px] gap-6">
        <div className="space-y-6 min-w-0">
          {error && <div className="text-sm text-red-500">{error}</div>}
          {!report && !error && (
            <div className="text-sm text-[var(--text-muted)]">
              Loading report…
            </div>
          )}
          {report && (
            <>
              <section className="card">
                <div className="text-xs font-mono uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  Cover
                </div>
                <div className="text-sm">
                  Generated on {report.generated_at?.slice(0, 19)} UTC.
                </div>
                <div className="text-sm mt-1">
                  {report.datasets.length} dataset{report.datasets.length === 1 ? "" : "s"} ·{" "}
                  {totalArtifacts} artifact{totalArtifacts === 1 ? "" : "s"} ·{" "}
                  {report.qa.length} chat turn{report.qa.length === 1 ? "" : "s"}
                </div>
                {report.datasets.length > 0 && (
                  <ul className="mt-3 text-sm space-y-0.5">
                    {report.datasets.map((d) => (
                      <li key={d.id} className="text-[var(--text-muted)]">
                        • {d.name} — {d.rows.toLocaleString()} × {d.cols}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              {report.synthesis && (report.synthesis.executive_summary ||
                (report.synthesis.key_findings || []).length > 0) && (
                <Section title="Insights synthesis">
                  <div className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface)] space-y-3">
                    {report.synthesis.executive_summary && (
                      <p className="text-sm leading-relaxed">
                        {report.synthesis.executive_summary}
                      </p>
                    )}
                    {(report.synthesis.key_findings || []).length > 0 && (
                      <div>
                        <div className="text-xs uppercase tracking-widest font-mono text-[var(--text-muted)] mb-1">
                          Key findings
                        </div>
                        <ul className="text-sm space-y-1 list-disc list-inside">
                          {(report.synthesis.key_findings || []).map((k, i) => (
                            <li key={i}>{k}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {(report.synthesis.recommendations || []).length > 0 && (
                      <div>
                        <div className="text-xs uppercase tracking-widest font-mono text-[var(--text-muted)] mb-1">
                          Recommendations
                        </div>
                        <ul className="text-sm space-y-1 list-disc list-inside">
                          {(report.synthesis.recommendations || []).map((r, i) => (
                            <li key={i}>{r}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                </Section>
              )}

              {(report.artifacts.insight ?? []).length > 0 && (
                <Section title="Surprise insights">
                  {(report.artifacts.insight ?? []).map((art) => (
                    <ul key={art.id} className="text-sm space-y-1.5">
                      {((art.result as { items?: { headline: string; severity: string; subtitle?: string }[] }).items || []).map((it, i) => (
                        <li key={i}>
                          <span className="font-mono text-[10px] uppercase tracking-widest text-[var(--text-muted)] mr-1.5">
                            {it.severity}
                          </span>
                          <span className="font-semibold">{it.headline}</span>
                          {it.subtitle && (
                            <span className="text-[var(--text-muted)]"> — {it.subtitle}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  ))}
                </Section>
              )}

              {(report.artifacts.profile ?? []).length > 0 && (
                <Section title="Data profile">
                  {(report.artifacts.profile ?? []).map((art) => (
                    <ProfileBlock key={art.id} art={art} />
                  ))}
                </Section>
              )}

              {(report.artifacts.chart ?? []).length > 0 && (
                <Section title="Charts">
                  {(report.artifacts.chart ?? []).map((art) => (
                    <div key={art.id} className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface)]">
                      <div className="text-sm font-semibold mb-2">{art.title}</div>
                      <ChartRenderer payload={art.result as unknown as ChartPayload} height={260} />
                    </div>
                  ))}
                </Section>
              )}

              {(report.artifacts.prediction ?? []).length > 0 && (
                <Section title="Predictions">
                  {(report.artifacts.prediction ?? []).map((art) => (
                    <div key={art.id} className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface)]">
                      <PredictionCard
                        title={art.title}
                        result={art.result as unknown as PredictionResult}
                      />
                    </div>
                  ))}
                </Section>
              )}

              {(report.what_if ?? []).length > 0 && (
                <Section title="What-if recommendations">
                  {(report.what_if ?? []).map((w, i) => (
                    <WhatIfBlock key={i} w={w} />
                  ))}
                </Section>
              )}

              {(report.artifacts.cluster ?? []).length > 0 && (
                <Section title="Clusters">
                  {(report.artifacts.cluster ?? []).map((art) => (
                    <ClusterBlock key={art.id} art={art} />
                  ))}
                </Section>
              )}

              {report.qa.length > 0 && (
                <Section title="Conversation">
                  <div className="space-y-2 text-sm">
                    {report.qa.map((t) => (
                      <div key={t.id} className="border border-[var(--border)] rounded p-3 bg-[var(--surface-alt)]/50">
                        <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-mono mb-1">You</div>
                        <div className="whitespace-pre-wrap">{t.user}</div>
                        {t.ai && (
                          <>
                            <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)] font-mono mt-2 mb-1">AXIOM</div>
                            <div className="whitespace-pre-wrap">{t.ai}</div>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                </Section>
              )}

              {totalArtifacts === 0 && report.qa.length === 0 && (
                <div className="text-sm text-[var(--text-muted)] border border-dashed border-[var(--border)] rounded p-6 text-center">
                  Nothing pinned to this report yet.
                  Run some analysis in the chat or untick &ldquo;Pinned only&rdquo; to include
                  everything.
                </div>
              )}
            </>
          )}
        </div>

        <aside className="lg:sticky lg:top-32 self-start space-y-2 min-w-0">
          <div className="flex items-center justify-between text-xs uppercase tracking-widest font-mono text-[var(--text-muted)]">
            <span>PDF preview</span>
            {previewLoading && <span>building…</span>}
          </div>
          <div className="border border-[var(--border)] rounded-xl bg-[var(--surface-alt)]/30 overflow-hidden">
            {previewUrl ? (
              <iframe
                key={previewUrl}
                src={previewUrl}
                title="Final report PDF preview"
                className="w-full"
                style={{ height: 720 }}
              />
            ) : (
              <div className="h-[720px] flex items-center justify-center text-sm text-[var(--text-muted)]">
                {previewLoading ? "Generating preview…" : "Preview will appear here."}
              </div>
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <h2 className="text-sm font-semibold uppercase tracking-widest text-[var(--text-muted)] font-mono">
        {title}
      </h2>
      {children}
    </section>
  );
}

function ProfileBlock({ art }: { art: Artifact }) {
  const r = art.result as { rows: number; cols: number; columns: { name: string; dtype: string; missing_pct: number; unique: number }[] };
  return (
    <div className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface)]">
      <div className="text-sm font-semibold mb-2">{art.title}</div>
      <div className="text-xs text-[var(--text-muted)] font-mono mb-2">
        {r.rows.toLocaleString()} rows · {r.cols} cols
      </div>
      <div className="overflow-auto max-h-72 border border-[var(--border)] rounded">
        <table className="w-full text-[11px]">
          <thead className="bg-[var(--surface-alt)] sticky top-0">
            <tr>
              <th className="text-left px-2 py-1.5">Column</th>
              <th className="text-left px-2 py-1.5">Dtype</th>
              <th className="text-right px-2 py-1.5">Missing</th>
              <th className="text-right px-2 py-1.5">Unique</th>
            </tr>
          </thead>
          <tbody>
            {(r.columns || []).map((c) => (
              <tr key={c.name} className="border-t border-[var(--border)]/40">
                <td className="px-2 py-1 truncate max-w-[200px]" title={c.name}>{c.name}</td>
                <td className="px-2 py-1 text-[10px] font-mono text-[var(--text-muted)]">{c.dtype}</td>
                <td className="px-2 py-1 text-right font-mono text-[10px]">{c.missing_pct}%</td>
                <td className="px-2 py-1 text-right font-mono text-[10px]">{c.unique.toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ClusterBlock({ art }: { art: Artifact }) {
  const r = art.result as {
    k: number;
    cluster_sizes: Record<string, number>;
    centroids: { cluster: number; size: number; values: Record<string, number> }[];
  };
  const total = Object.values(r.cluster_sizes || {}).reduce((a, b) => a + b, 0) || 1;
  return (
    <div className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface)]">
      <div className="text-sm font-semibold mb-2">{art.title}</div>
      <div className="grid grid-cols-2 gap-3">
        {(r.centroids || []).map((c) => (
          <div key={c.cluster} className="border border-[var(--border)] rounded p-2">
            <div className="flex items-baseline justify-between mb-1">
              <div className="text-xs font-semibold">Cluster #{c.cluster}</div>
              <div className="text-[10px] font-mono text-[var(--text-muted)]">
                {c.size.toLocaleString()} ({Math.round((c.size / total) * 100)}%)
              </div>
            </div>
            <div className="grid grid-cols-1 gap-y-0.5 text-[10px] font-mono">
              {Object.entries(c.values).map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="truncate text-[var(--text-muted)]">{k}</span>
                  <span>{Number(v).toLocaleString(undefined, { maximumFractionDigits: 3 })}</span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function WhatIfBlock({ w }: { w: WhatIf }) {
  return (
    <div className="border border-[var(--border)] rounded-xl p-4 bg-[var(--surface)] space-y-3">
      <div className="flex items-baseline justify-between">
        <div className="text-sm font-semibold">{w.title}</div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
          target: {w.target || "—"}
        </div>
      </div>
      {w.rows.map((feat) => (
        <div key={feat.feature}>
          <div className="text-xs font-semibold mb-1">
            {feat.feature}{" "}
            <span className="text-[10px] font-mono text-[var(--text-muted)]">
              (baseline {feat.baseline_value})
            </span>
          </div>
          <div className="overflow-auto border border-[var(--border)] rounded">
            <table className="w-full text-[11px]">
              <thead className="bg-[var(--surface-alt)]">
                <tr>
                  <th className="text-left px-2 py-1.5">Shift</th>
                  <th className="text-right px-2 py-1.5">New value</th>
                  <th className="text-right px-2 py-1.5">Δ predicted</th>
                  <th className="text-right px-2 py-1.5">Predicted</th>
                </tr>
              </thead>
              <tbody>
                {feat.rows.map((r, i) => (
                  <tr key={i} className="border-t border-[var(--border)]/40">
                    <td className="px-2 py-1 font-mono">
                      {r.shift_pct > 0 ? "+" : ""}
                      {r.shift_pct}%
                    </td>
                    <td className="px-2 py-1 text-right font-mono">
                      {Number(r.new_value).toLocaleString(undefined, { maximumFractionDigits: 3 })}
                    </td>
                    <td className="px-2 py-1 text-right font-mono">
                      {r.predicted_delta > 0 ? "+" : ""}
                      {Number(r.predicted_delta).toLocaleString(undefined, { maximumFractionDigits: 3 })}
                    </td>
                    <td className="px-2 py-1 text-right font-mono">
                      {Number(r.predicted_value).toLocaleString(undefined, { maximumFractionDigits: 3 })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}
