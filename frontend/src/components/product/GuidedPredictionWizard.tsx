"use client";
/**
 * Guided predictive flow — Task #212.
 *
 * Five-phase wizard rendered inside the Predictions tab of the
 * Artifact Drawer:
 *   1. Scanning   — dispatches POST /api/predict/guided/analyze and
 *                   shows the dataset profile while it works.
 *   2. Summary    — shows a "Here's what we understood" card so the
 *                   user can confirm target, drivers and date range
 *                   before any questions are asked (Task #291).
 *   3. Questioning — collects 3–5 Arabic clarifying answers ONE AT A
 *                    TIME with contextual "Why are we asking this?"
 *                    hints and plain-language option descriptions
 *                    (Task #291).
 *   4. Result     — POST /api/predict/guided/run, then renders the
 *                   confidence gauge, key numbers and Arabic
 *                   narrative through <GuidedPredictionCard />.
 *                   The wizard STAYS in the result phase until the
 *                   user explicitly chooses "Run new forecast" or
 *                   closes it.
 *
 * Strings are Arabic + RTL; the component sets `dir="rtl"` on its
 * own root so it renders correctly even inside an LTR drawer.
 *
 * The wizard fires `axiom:guided-predict:state` window events
 * ({ phase: "scanning" | "running" | "idle" }) so the Data Context
 * Bar can surface a "Predicting…" pill without prop-drilling.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { errMessage } from "@/lib/types";
import {
  GuidedPredictionCard,
  ConfidenceGauge,
  type GuidedPredictionResult,
} from "./GuidedPredictionCard";

type WizardQuestion = {
  id: string;
  text: string;
  kind: "slider" | "yesno" | "dropdown";
  min?: number;
  max?: number;
  default?: number | string;
  unit?: string;
  options?: string[];
  hint?: string;
  option_hints?: Record<string, string>;
};

type PartialConfidence = {
  score: number;
  band: "low" | "medium" | "high";
  weights: Record<string, number>;
  sub_scores: Record<string, number>;
  preliminary?: boolean;
};

type AnalyzePayload =
  | {
      ok: true;
      dataset_id: number;
      dataset_name: string;
      row_count: number;
      time_column: string | null;
      target: string;
      drivers: { column: string; correlation: number; abs_correlation: number }[];
      questions: WizardQuestion[];
      partial_confidence: PartialConfidence;
      domain?: string;
      target_reason?: string;
      problem_type?: string;
      numeric_columns?: string[];
      date_start?: string | null;
      date_end?: string | null;
      flow: "guided";
    }
  | {
      ok: false;
      kind: string;
      message_ar: string;
      rows_available?: number;
      rows_required?: number;
    };

type Phase = "scanning" | "summary" | "questioning" | "running" | "result" | "error";

function emitState(phase: "scanning" | "running" | "idle") {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent("axiom:guided-predict:state", { detail: { phase } })
  );
}

function seedAnswersFor(questions: WizardQuestion[]): Record<string, string | number> {
  const seed: Record<string, string | number> = {};
  for (const q of questions) {
    if (q.default !== undefined) seed[q.id] = q.default;
    else if (q.kind === "slider") seed[q.id] = 0;
    else if (q.kind === "yesno") seed[q.id] = "no";
    else if (q.kind === "dropdown" && q.options?.length) seed[q.id] = q.options[0];
  }
  return seed;
}

export function GuidedPredictionWizard({
  datasetId,
  datasetName,
  sessionId,
  onArtifactCreated,
  onClose,
}: {
  datasetId: number;
  datasetName?: string;
  sessionId: number | null;
  onArtifactCreated?: () => void;
  onClose?: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("scanning");
  const [error, setError] = useState<string | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzePayload | null>(null);
  const [answers, setAnswers] = useState<Record<string, string | number>>({});
  const [questionIndex, setQuestionIndex] = useState(0);
  const [result, setResult] = useState<GuidedPredictionResult | null>(null);
  const [selectedTarget, setSelectedTarget] = useState<string | null>(null);
  const reloadTokenRef = useRef(0);

  const startAnalyze = useCallback(() => {
    const myToken = ++reloadTokenRef.current;
    setPhase("scanning");
    setError(null);
    setResult(null);
    setSelectedTarget(null);
    emitState("scanning");
    api<AnalyzePayload>("/api/predict/guided/analyze", {
      method: "POST",
      json: { dataset_id: datasetId },
    })
      .then((data) => {
        if (myToken !== reloadTokenRef.current) return;
        setAnalysis(data);
        if (!("ok" in data) || !data.ok) {
          setPhase("error");
          return;
        }
        setAnswers(seedAnswersFor(data.questions));
        setQuestionIndex(0);
        setPhase("summary");
      })
      .catch((e) => {
        if (myToken !== reloadTokenRef.current) return;
        setError(errMessage(e));
        setPhase("error");
      })
      .finally(() => {
        if (myToken === reloadTokenRef.current) emitState("idle");
      });
  }, [datasetId]);

  // Phase 1 — Scanning (initial mount)
  useEffect(() => {
    startAnalyze();
    return () => {
      reloadTokenRef.current += 1;
      emitState("idle");
    };
  }, [startAnalyze]);

  const goBackToQuestioning = useCallback(() => {
    setQuestionIndex(0);
    setPhase("questioning");
  }, []);

  const submit = useCallback(async () => {
    if (!analysis || !("ok" in analysis) || !analysis.ok) return;
    setPhase("running");
    setError(null);
    emitState("running");
    try {
      const horizon = Number(answers["horizon_periods"] ?? 30) || 30;
      const effectiveTarget = selectedTarget || analysis.target;
      const driverCols =
        selectedTarget && selectedTarget !== analysis.target
          ? (analysis.numeric_columns ?? []).filter((c) => c !== effectiveTarget)
          : analysis.drivers.map((d) => d.column).filter((c) => c !== effectiveTarget);
      const resp = await api<{
        result: GuidedPredictionResult;
        artifact: unknown | null;
      }>("/api/predict/guided/run", {
        method: "POST",
        json: {
          dataset_id: datasetId,
          target: effectiveTarget,
          time_column: analysis.time_column,
          drivers: driverCols,
          answers,
          periods: horizon,
          session_id: sessionId,
        },
      });
      setResult(resp.result);
      setPhase("result");
      onArtifactCreated?.();
    } catch (e) {
      setError(errMessage(e));
      setPhase("error");
    } finally {
      emitState("idle");
    }
  }, [analysis, answers, selectedTarget, datasetId, sessionId, onArtifactCreated]);

  return (
    <div
      dir="rtl"
      className="border border-[var(--border)] rounded-xl bg-[var(--surface-alt)]/40 p-4 space-y-4 text-right"
    >
      <Header phase={phase} onClose={onClose} />
      {phase === "scanning" && <ScanningPhase datasetName={datasetName} />}
      {phase === "summary" && analysis && "ok" in analysis && analysis.ok && (
        <SummaryPhase
          analysis={analysis}
          selectedTarget={selectedTarget}
          onTargetChange={setSelectedTarget}
          onContinue={() => setPhase("questioning")}
        />
      )}
      {phase === "questioning" && analysis && "ok" in analysis && analysis.ok && (
        <QuestioningPhase
          analysis={analysis}
          answers={answers}
          setAnswers={setAnswers}
          index={questionIndex}
          setIndex={setQuestionIndex}
          onSubmit={submit}
          selectedTarget={selectedTarget}
        />
      )}
      {phase === "running" && (
        <RunningPhase
          target={
            (analysis && "ok" in analysis && analysis.ok &&
              (selectedTarget || analysis.target)) || ""
          }
        />
      )}
      {phase === "result" && result && (
        <GuidedPredictionCard
          result={result}
          onRestart={startAnalyze}
          onEditAnswers={goBackToQuestioning}
        />
      )}
      {phase === "error" && (
        <ErrorPhase
          message={
            error
              || (analysis && "message_ar" in analysis ? analysis.message_ar : null)
              || "An error occurred during the forecast. Please try again."
          }
          onRetry={startAnalyze}
        />
      )}
    </div>
  );
}

function Header({ phase, onClose }: { phase: Phase; onClose?: () => void }) {
  const label = useMemo(() => {
    switch (phase) {
      case "scanning": return "الخطوة 1 من 4 · فحص البيانات";
      case "summary": return "الخطوة 2 من 4 · ما فهمناه من بياناتك";
      case "questioning": return "الخطوة 3 من 4 · أسئلة التوضيح";
      case "running": return "الخطوة 4 من 4 · احتساب التوقع";
      case "result": return "النتيجة";
      case "error": return "تنبيه";
    }
  }, [phase]);
  const step =
    phase === "scanning" ? 1
    : phase === "summary" ? 2
    : phase === "questioning" ? 3
    : 4;
  return (
    <div className="flex items-center justify-between gap-2">
      <div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
          AXIOM · التوقع الموجّه
        </div>
        <div className="text-sm font-semibold">{label}</div>
      </div>
      <div className="flex items-center gap-2">
        <PhaseDots step={phase === "error" ? 1 : step} total={4} />
        {onClose && (
          <button
            onClick={onClose}
            className="text-[10px] text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1 rounded"
            aria-label="إغلاق"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

function PhaseDots({ step, total = 3 }: { step: number; total?: number }) {
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: total }, (_, i) => i + 1).map((i) => (
        <span
          key={i}
          className={`inline-block h-1.5 w-4 rounded-full transition-colors ${
            i <= step ? "bg-[var(--accent)]" : "bg-[var(--border)]"
          }`}
        />
      ))}
    </div>
  );
}

function ScanningPhase({ datasetName }: { datasetName?: string }) {
  return (
    <div className="space-y-3">
      <div className="text-sm">
        نحن نفحص بياناتك
        {datasetName ? (
          <span className="font-semibold"> «{datasetName}» </span>
        ) : " "}
        لتحديد أفضل المؤشرات للتوقع.
      </div>
      <div className="space-y-2">
        <Bar w="80%" />
        <Bar w="55%" />
        <Bar w="65%" />
      </div>
      <div className="text-[11px] text-[var(--text-muted)]">
        نبحث عن أعمدة الزمن، الأهداف الرقمية والعوامل المؤثرة…
      </div>
    </div>
  );
}

function Bar({ w }: { w: string }) {
  return (
    <div className="h-2 bg-[var(--border)]/40 rounded overflow-hidden">
      <div
        className="h-full bg-[var(--accent)]/60 animate-pulse"
        style={{ width: w }}
      />
    </div>
  );
}

function SummaryPhase({
  analysis,
  selectedTarget,
  onTargetChange,
  onContinue,
}: {
  analysis: Extract<AnalyzePayload, { ok: true }>;
  selectedTarget: string | null;
  onTargetChange: (t: string | null) => void;
  onContinue: () => void;
}) {
  const effectiveTarget = selectedTarget || analysis.target;
  const numericCols = analysis.numeric_columns ?? [];
  const [showTargetPicker, setShowTargetPicker] = useState(false);

  return (
    <div className="space-y-4">
      <div className="text-[11px] text-[var(--text-muted)] leading-relaxed">
        قبل أن نبدأ الأسئلة، دعنا نتأكد أن النظام قرأ ملفك بشكل صحيح.
      </div>

      <div className="rounded-lg border border-[var(--accent)]/30 bg-[var(--accent)]/5 p-4 space-y-3">
        <div className="font-semibold text-sm">ما فهمناه من بياناتك</div>

        {analysis.domain && (
          <div className="flex items-start gap-2">
            <span className="text-[var(--text-muted)] text-[11px] w-20 shrink-0 pt-0.5">المجال</span>
            <span className="text-[11px] font-semibold text-[var(--accent)]">{analysis.domain}</span>
          </div>
        )}

        <div className="flex items-start gap-2">
          <span className="text-[var(--text-muted)] text-[11px] w-20 shrink-0 pt-0.5">هدف التوقع</span>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm font-semibold text-[var(--accent)]">{effectiveTarget}</span>
            {numericCols.length > 1 && (
              <button
                type="button"
                onClick={() => setShowTargetPicker((p) => !p)}
                className="text-[10px] px-1.5 py-0.5 rounded border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors"
              >
                تغيير
              </button>
            )}
          </div>
        </div>

        {showTargetPicker && numericCols.length > 1 && (
          <div className="pr-[5.5rem]">
            <select
              value={effectiveTarget}
              onChange={(e) => {
                onTargetChange(e.target.value === analysis.target ? null : e.target.value);
                setShowTargetPicker(false);
              }}
              className="w-full text-xs px-2 py-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
            >
              {numericCols.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
          </div>
        )}

        {analysis.target_reason && (
          <div className="flex items-start gap-2">
            <span className="text-[var(--text-muted)] text-[11px] w-20 shrink-0 pt-0.5">السبب</span>
            <span className="text-[11px] text-[var(--text-muted)] leading-relaxed">{analysis.target_reason}</span>
          </div>
        )}

        {analysis.drivers.length > 0 && (
          <div className="flex items-start gap-2">
            <span className="text-[var(--text-muted)] text-[11px] w-20 shrink-0 pt-0.5">أبرز العوامل</span>
            <div className="flex flex-wrap gap-1">
              {analysis.drivers.slice(0, 3).map((d) => (
                <span
                  key={d.column}
                  className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[var(--border)]/40 text-[var(--text)]"
                >
                  {d.column}
                </span>
              ))}
              {analysis.drivers.length > 3 && (
                <span className="text-[10px] text-[var(--text-muted)]">+{analysis.drivers.length - 3} أخرى</span>
              )}
            </div>
          </div>
        )}

        {(analysis.date_start || analysis.date_end) && (
          <div className="flex items-start gap-2">
            <span className="text-[var(--text-muted)] text-[11px] w-20 shrink-0 pt-0.5">نطاق التواريخ</span>
            <span className="text-[11px] font-mono text-[var(--text)]">
              {analysis.date_start} → {analysis.date_end}
            </span>
          </div>
        )}

        <div className="flex items-start gap-2">
          <span className="text-[var(--text-muted)] text-[11px] w-20 shrink-0 pt-0.5">عدد الصفوف</span>
          <span className="text-[11px] font-mono text-[var(--text)]">
            {analysis.row_count.toLocaleString("ar-EG")} صف
          </span>
        </div>
      </div>

      <div className="flex justify-end">
        <button
          onClick={onContinue}
          className="text-sm font-semibold px-5 py-2 rounded-full bg-[var(--accent)] text-white hover:opacity-90"
        >
          يبدو صحيحاً، نكمل ←
        </button>
      </div>
    </div>
  );
}

const SUB_SCORE_LABELS_AR: Record<string, string> = {
  data_volume: "حجم البيانات",
  data_quality: "جودة البيانات",
  signal_strength: "قوة الإشارة",
  time_coverage: "تغطية الزمن",
};

function QuestioningPhase({
  analysis,
  answers,
  setAnswers,
  index,
  setIndex,
  onSubmit,
  selectedTarget,
}: {
  analysis: Extract<AnalyzePayload, { ok: true }>;
  answers: Record<string, string | number>;
  setAnswers: (next: Record<string, string | number>) => void;
  index: number;
  setIndex: (n: number) => void;
  onSubmit: () => void;
  selectedTarget: string | null;
}) {
  const total = analysis.questions.length;
  const safeIndex = Math.max(0, Math.min(index, total - 1));
  const current = analysis.questions[safeIndex];
  const isLast = safeIndex >= total - 1;
  const progress = total > 0 ? ((safeIndex + 1) / total) * 100 : 100;
  const effectiveTarget = selectedTarget || analysis.target;

  return (
    <div className="space-y-4">
      {current && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-semibold text-[var(--text-muted)]">
              السؤال {safeIndex + 1} من {total}
            </span>
            <div className="flex-1 h-1.5 bg-[var(--border)]/40 rounded-full overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] transition-all rounded-full"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
          <QuestionInput
            question={current}
            value={answers[current.id]}
            onChange={(v) => setAnswers({ ...answers, [current.id]: v })}
          />
        </div>
      )}

      <div className="flex items-center justify-between gap-2 pt-2 border-t border-[var(--border)]/60">
        <button
          onClick={() => setIndex(Math.max(0, safeIndex - 1))}
          disabled={safeIndex === 0}
          className="text-xs px-3 py-1.5 rounded-full border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ← السابق
        </button>
        <div className="text-[10px] text-[var(--text-muted)]">
          هدف: <span className="font-semibold text-[var(--accent)]">{effectiveTarget}</span>
        </div>
        {isLast ? (
          <button
            onClick={onSubmit}
            className="text-xs font-semibold px-4 py-1.5 rounded-full bg-[var(--accent)] text-white hover:opacity-90"
          >
            تشغيل التوقع →
          </button>
        ) : (
          <button
            onClick={() => setIndex(Math.min(total - 1, safeIndex + 1))}
            className="text-xs font-semibold px-4 py-1.5 rounded-full bg-[var(--accent)] text-white hover:opacity-90"
          >
            التالي →
          </button>
        )}
      </div>
    </div>
  );
}

function PartialConfidencePreview({ pc }: { pc: PartialConfidence }) {
  return (
    <div className="rounded-lg border border-[var(--border)]/60 bg-[var(--surface)] p-3">
      <div className="text-[11px] text-[var(--text-muted)] mb-2">
        الثقة التقديرية قبل التشغيل (ستُحدَّث بعد التوقع):
      </div>
      <div className="flex items-center gap-3">
        <ConfidenceGauge score={pc.score} band={pc.band} size={64} />
        <div className="flex-1 grid grid-cols-2 gap-1.5">
          {Object.entries(pc.sub_scores).map(([k, v]) => {
            const w = Math.max(0, Math.min(100, Number(v) || 0));
            return (
              <div key={k}>
                <div className="flex items-center justify-between text-[10px] mb-0.5">
                  <span className="text-[var(--text-muted)]">
                    {SUB_SCORE_LABELS_AR[k] ?? k}
                  </span>
                  <span className="font-mono tabular-nums">{Math.round(w)}</span>
                </div>
                <div className="h-1 bg-[var(--border)]/40 rounded">
                  <div
                    className="h-full bg-[var(--accent)] rounded"
                    style={{ width: `${w}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function QuestionInput({
  question,
  value,
  onChange,
}: {
  question: WizardQuestion;
  value: string | number | undefined;
  onChange: (v: string | number) => void;
}) {
  const [showHint, setShowHint] = useState(false);

  // Deterministic fallback hints ensure the collapsible is always available,
  // even when a cached LLM response pre-dates the hint field.
  const HINT_FALLBACKS: Record<WizardQuestion["kind"], string> = {
    slider: "اضبط القيمة بناءً على معرفتك بالبيانات — يمكنك دائماً تعديل الإجابة لاحقاً.",
    yesno: "اختر الإجابة الأنسب بناءً على سياق بياناتك.",
    dropdown: "اختر الخيار الذي يصف بياناتك بشكل أدق.",
  };
  const resolvedHint = question.hint ?? HINT_FALLBACKS[question.kind];

  // Fallback descriptions for yes/no options when option_hints is absent.
  const YESNO_FALLBACK_HINTS: Record<string, string> = {
    yes: "نعم — ينطبق هذا على بياناتي.",
    no: "لا — لا ينطبق هذا على بياناتي.",
  };

  const hintBlock = (
    <div>
      <button
        type="button"
        onClick={() => setShowHint((v) => !v)}
        className="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] flex items-center gap-1 transition-colors"
      >
        <span>{showHint ? "▲" : "▼"}</span>
        <span>لماذا نسأل هذا؟</span>
      </button>
      {showHint && (
        <div className="mt-1.5 text-[11px] text-[var(--text-muted)] leading-relaxed rounded-md border border-[var(--border)]/40 bg-[var(--surface)] px-3 py-2">
          {resolvedHint}
        </div>
      )}
    </div>
  );

  if (question.kind === "slider") {
    const min = question.min ?? -50;
    const max = question.max ?? 50;
    const v = typeof value === "number" ? value : Number(value ?? 0);
    return (
      <div className="space-y-2">
        <label className="text-sm font-medium block leading-relaxed">{question.text}</label>
        {hintBlock}
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={min}
            max={max}
            value={v}
            onChange={(e) => onChange(Number(e.target.value))}
            className="flex-1 accent-[var(--accent)]"
          />
          <div className="text-xs font-mono w-14 text-left tabular-nums">
            {v}{question.unit ?? ""}
          </div>
        </div>
      </div>
    );
  }

  if (question.kind === "yesno") {
    const v = String(value ?? "no");
    return (
      <div className="space-y-2">
        <label className="text-sm font-medium block leading-relaxed">{question.text}</label>
        {hintBlock}
        <div className="flex items-start gap-3 pt-0.5">
          {(["yes", "no"] as const).map((opt) => {
            const optHint = question.option_hints?.[opt] ?? YESNO_FALLBACK_HINTS[opt];
            const isSelected = v === opt;
            return (
              <button
                key={opt}
                type="button"
                onClick={() => onChange(opt)}
                className={`flex-1 text-right rounded-lg border p-2.5 transition-colors ${
                  isSelected
                    ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                    : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)]/60"
                }`}
              >
                <div className="text-xs font-semibold mb-0.5">
                  {opt === "yes" ? "نعم" : "لا"}
                </div>
                <div className="text-[10px] leading-snug opacity-80">{optHint}</div>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  // dropdown
  const v = String(value ?? "");
  const opts = question.options ?? [];
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium block leading-relaxed">{question.text}</label>
      {hintBlock}
      <div className="space-y-1.5 pt-0.5">
        {opts.map((opt) => {
          const optHint = question.option_hints?.[opt];
          const isSelected = v === opt;
          return (
            <button
              key={opt}
              type="button"
              onClick={() => onChange(opt)}
              className={`w-full text-right rounded-lg border px-3 py-2 transition-colors ${
                isSelected
                  ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--text)] hover:border-[var(--accent)]/60"
              }`}
            >
              <div className="text-xs font-semibold">{opt}</div>
              {optHint && (
                <div className="text-[10px] text-[var(--text-muted)] mt-0.5 leading-snug">{optHint}</div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function RunningPhase({ target }: { target: string }) {
  return (
    <div className="space-y-3">
      <div className="text-sm">
        نشغّل النموذج للتنبؤ بـ{" "}
        <span className="font-semibold text-[var(--accent)]">{target || "البيانات"}</span>…
      </div>
      <div className="space-y-2">
        <Bar w="92%" />
        <Bar w="76%" />
      </div>
      <div className="text-[11px] text-[var(--text-muted)]">
        نجمع النموذج الإحصائي مع تحليل العوامل المؤثرة ونحسب درجة الثقة.
      </div>
    </div>
  );
}

function ErrorPhase({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="text-sm leading-relaxed text-[var(--text)]">{message}</div>
      <div className="flex items-center gap-2 justify-end">
        <button
          onClick={onRetry}
          className="text-xs font-semibold px-3 py-1.5 rounded-full border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)]/10"
        >
          إعادة المحاولة
        </button>
      </div>
    </div>
  );
}
