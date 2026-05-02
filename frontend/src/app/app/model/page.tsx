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
    <div className="card mt-6 space-y-3" dir="rtl">
      <label className="block text-sm">
        الطريقة
        <select value={method} onChange={(e) => setMethod(e.target.value as Method)}
          className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" style={{ minHeight: 44 }}>
          <option value="kmeans">تجميع K-Means</option>
          <option value="randomforest">غابة عشوائية (Random Forest)</option>
        </select>
      </label>
      {method === "kmeans" ? (
        <label className="block text-sm">
          k (عدد التجمعات)
          <input type="number" min={2} max={10} value={k}
            onChange={(e) => setK(Number(e.target.value))}
            className="block mt-1 w-32 px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" style={{ minHeight: 44 }} />
        </label>
      ) : (
        <label className="block text-sm">
          العمود الهدف
          <select value={target} onChange={(e) => setTarget(e.target.value)}
            className="block mt-1 w-full px-3 py-2 rounded border border-[var(--border)] bg-[var(--surface)] text-sm" style={{ minHeight: 44 }}>
            {columns.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </label>
      )}
      <button className="btn btn-primary" onClick={run} disabled={busy} style={{ minHeight: 44 }}>{busy ? "جاري التشغيل…" : "تشغيل النموذج"}</button>
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
        <div className="mt-4 card border-amber-500/60" role="alert" dir="rtl">
          <div className="text-[12px] font-semibold text-amber-600 mb-1">
            تنبيهات حول جودة النمذجة
          </div>
          <ul className="text-[12px] space-y-0.5 list-disc list-inside text-amber-700">
            {!safeguards.grain.is_unique && (
              <li>
                مفتاح الصف غير فريد — {safeguards.grain.duplicate_count.toLocaleString()} صف مكرّر.
                قد تتأثر دقّة تقسيم التدريب/الاختبار وحجم التجمعات.
              </li>
            )}
            {safeguards.grain.is_unique && safeguards.grain.keys.length > 0 && (
              <li className="text-[var(--text-muted)]">
                مفتاح الصف: <span className="font-mono">{safeguards.grain.keys.join(" + ")}</span>
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
          guidedHint="ارفع ملف CSV أو Excel وسنبحث عن المجموعات والأنماط داخله."
        />
      ) : mode === "guided" ? (
        <>
          <div className="mt-6 grid grid-cols-1 md:grid-cols-2 gap-3" dir="rtl">
            <GuidedActionCard
              title="جمّع الصفوف المتشابهة"
              description="اكتشف تلقائيًا 3 شرائح طبيعية في البيانات — مفيد لتجزئة العملاء أو المنتجات."
              cta="جد 3 مجموعات"
              busy={busy}
              onAction={() => runWith({ method: "kmeans", k: 3 })}
            />
            <GuidedActionCard
              title="تقسيم أدق"
              description="الفكرة نفسها مع تقسيم إلى 5 شرائح لإبراز الفئات الأصغر."
              cta="جد 5 مجموعات"
              busy={busy}
              onAction={() => runWith({ method: "kmeans", k: 5 })}
            />
            <GuidedActionCard
              title="تنبّأ بقيمة عمود"
              description="درّب نموذج Random Forest للتنبؤ بالعمود المختار من بقية البيانات."
              cta="درّب النموذج"
              busy={busy}
              disabled={!target}
              onAction={() => runWith({ method: "randomforest", target })}
            />
          </div>
          {target && (
            <div className="text-[12px] text-[var(--text-muted)] mt-2" dir="rtl">
              سيتنبّأ النموذج بـ <strong>{target}</strong>. اختر هدفًا آخر من العرض المتقدّم.
            </div>
          )}
          <AdvancedExpander projectId={projectId} hint="اختر الطريقة وعدد التجمعات والهدف يدويًا">
            {expertControls}
          </AdvancedExpander>
        </>
      ) : (
        expertControls
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
      {result !== null && (
        <div className="card mt-4" dir="rtl">
          {mode === "guided" ? (
            <>
              <div className="font-semibold text-sm">تم تدريب النموذج بنجاح ✓</div>
              <p className="text-[12px] text-[var(--text-muted)] mt-1">
                افتح العرض الفنّي لمشاهدة مراكز التجمعات وأهمية المتغيّرات والمقاييس.
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
