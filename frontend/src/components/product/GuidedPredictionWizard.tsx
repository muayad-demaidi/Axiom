"use client";
/**
 * Guided predictive flow — Task #212.
 *
 * Three-phase wizard rendered inside the Predictions tab of the
 * Artifact Drawer:
 *   1. Scanning   — dispatches POST /api/predict/guided/analyze and
 *                   shows the dataset profile while it works.
 *   2. Questioning — collects 3–5 Arabic clarifying answers ONE AT A
 *                    TIME (slider / yes-no / dropdown). The wizard
 *                    also previews the partial confidence breakdown
 *                    returned by analyze so the user can see "where
 *                    confidence will come from" before they run.
 *   3. Result     — POST /api/predict/guided/run, then renders the
 *                   confidence gauge, key numbers and Arabic
 *                   narrative through <GuidedPredictionCard />. The
 *                   wizard STAYS in the result phase until the user
 *                   explicitly chooses "Run new forecast" or closes
 *                   it — `onArtifactCreated` only refreshes the
 *                   drawer's artifact list so the just-saved
 *                   prediction also appears in the legacy artifact
 *                   stream below.
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
      flow: "guided";
    }
  | {
      ok: false;
      kind: string;
      message_ar: string;
      rows_available?: number;
      rows_required?: number;
    };

type Phase = "scanning" | "questioning" | "running" | "result" | "error";

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
  const reloadTokenRef = useRef(0);

  const startAnalyze = useCallback(() => {
    const myToken = ++reloadTokenRef.current;
    setPhase("scanning");
    setError(null);
    setResult(null);
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
        setPhase("questioning");
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
      // Bump the token so any in-flight request is ignored.
      reloadTokenRef.current += 1;
      emitState("idle");
    };
  }, [startAnalyze]);

  const submit = useCallback(async () => {
    if (!analysis || !("ok" in analysis) || !analysis.ok) return;
    setPhase("running");
    setError(null);
    emitState("running");
    try {
      const horizon = Number(answers["horizon_periods"] ?? 30) || 30;
      const driverCols = analysis.drivers.map((d) => d.column);
      const resp = await api<{
        result: GuidedPredictionResult;
        artifact: unknown | null;
      }>("/api/predict/guided/run", {
        method: "POST",
        json: {
          dataset_id: datasetId,
          target: analysis.target,
          time_column: analysis.time_column,
          drivers: driverCols,
          answers,
          periods: horizon,
          session_id: sessionId,
        },
      });
      setResult(resp.result);
      setPhase("result");
      // Refresh the drawer's artifact list so the saved prediction
      // also appears below — but DO NOT close the wizard. The
      // Result phase is a first-class step the user must read and
      // can dismiss explicitly via "Run new forecast" or the X.
      onArtifactCreated?.();
    } catch (e) {
      setError(errMessage(e));
      setPhase("error");
    } finally {
      emitState("idle");
    }
  }, [analysis, answers, datasetId, sessionId, onArtifactCreated]);

  return (
    <div
      dir="rtl"
      className="border border-[var(--border)] rounded-xl bg-[var(--surface-alt)]/40 p-4 space-y-4 text-right"
    >
      <Header phase={phase} onClose={onClose} />
      {phase === "scanning" && <ScanningPhase datasetName={datasetName} />}
      {phase === "questioning" && analysis && "ok" in analysis && analysis.ok && (
        <QuestioningPhase
          analysis={analysis}
          answers={answers}
          setAnswers={setAnswers}
          index={questionIndex}
          setIndex={setQuestionIndex}
          onSubmit={submit}
        />
      )}
      {phase === "running" && (
        <RunningPhase
          target={(analysis && "ok" in analysis && analysis.ok && analysis.target) || ""}
        />
      )}
      {phase === "result" && result && (
        <GuidedPredictionCard
          result={result}
          onRestart={startAnalyze}
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
      case "scanning": return "Step 1 of 3 · Scanning";
      case "questioning": return "Step 2 of 3 · Clarifying questions";
      case "running": return "Step 3 of 3 · Computing forecast";
      case "result": return "Result";
      case "error": return "Alert";
    }
  }, [phase]);
  const step = phase === "scanning" ? 1 : phase === "questioning" ? 2 : 3;
  return (
    <div className="flex items-center justify-between gap-2">
      <div>
        <div className="text-[10px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
          AXIOM · Guided forecast
        </div>
        <div className="text-sm font-semibold">{label}</div>
      </div>
      <div className="flex items-center gap-2">
        <PhaseDots step={phase === "error" ? 1 : step} />
        {onClose && (
          <button
            onClick={onClose}
            className="text-[10px] text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1 rounded"
            aria-label="Close"
          >
            ✕
          </button>
        )}
      </div>
    </div>
  );
}

function PhaseDots({ step }: { step: number }) {
  return (
    <div className="flex items-center gap-1">
      {[1, 2, 3].map((i) => (
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
        We're scanning your data
        {datasetName ? (
          <span className="font-semibold"> «{datasetName}» </span>
        ) : " "}
        to identify the best metrics to forecast.
      </div>
      <div className="space-y-2">
        <Bar w="80%" />
        <Bar w="55%" />
        <Bar w="65%" />
      </div>
      <div className="text-[11px] text-[var(--text-muted)]">
        Looking for time columns, numeric targets and driving factors…
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

const SUB_SCORE_LABELS_AR: Record<string, string> = {
  data_volume: "Data volume",
  data_quality: "Data quality",
  signal_strength: "Signal strength",
  time_coverage: "Time coverage",
};

function QuestioningPhase({
  analysis,
  answers,
  setAnswers,
  index,
  setIndex,
  onSubmit,
}: {
  analysis: Extract<AnalyzePayload, { ok: true }>;
  answers: Record<string, string | number>;
  setAnswers: (next: Record<string, string | number>) => void;
  index: number;
  setIndex: (n: number) => void;
  onSubmit: () => void;
}) {
  const total = analysis.questions.length;
  const safeIndex = Math.max(0, Math.min(index, total - 1));
  const current = analysis.questions[safeIndex];
  const isLast = safeIndex >= total - 1;
  const progress = total > 0 ? ((safeIndex + 1) / total) * 100 : 100;

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-[var(--border)]/60 bg-[var(--surface)] p-3">
        <div className="text-[11px] text-[var(--text-muted)] mb-1">
          What we found:
        </div>
        <div className="text-sm">
          We'll forecast <span className="font-semibold text-[var(--accent)]">{analysis.target}</span>
          {analysis.time_column ? (
            <>
              {" "}over time using column{" "}
              <span className="font-mono text-[11px]">{analysis.time_column}</span>.
            </>
          ) : analysis.drivers.length ? (
            <>
              {" "}based on {analysis.drivers.length} driving factors:{" "}
              <span className="font-mono text-[11px]">
                {analysis.drivers.slice(0, 3).map((d) => d.column).join(" · ")}
              </span>
              {analysis.drivers.length > 3 ? "…" : ""}
            </>
          ) : (
            <> based on the available data.</>
          )}
        </div>
      </div>

      {analysis.partial_confidence && (
        <PartialConfidencePreview pc={analysis.partial_confidence} />
      )}

      {current && (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <span className="text-[10px] font-mono text-[var(--text-muted)]">
              Question {safeIndex + 1} from {total}
            </span>
            <div className="flex-1 mx-3 h-1 bg-[var(--border)]/40 rounded overflow-hidden">
              <div
                className="h-full bg-[var(--accent)] transition-all"
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
          ← Back
        </button>
        <div className="text-[10px] text-[var(--text-muted)]">
          {analysis.row_count.toLocaleString("ar-EG")} rows
        </div>
        {isLast ? (
          <button
            onClick={onSubmit}
            className="text-xs font-semibold px-4 py-1.5 rounded-full bg-[var(--accent)] text-white hover:opacity-90"
          >
            Run forecast →
          </button>
        ) : (
          <button
            onClick={() => setIndex(Math.min(total - 1, safeIndex + 1))}
            className="text-xs font-semibold px-4 py-1.5 rounded-full bg-[var(--accent)] text-white hover:opacity-90"
          >
            Next →
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
        Preliminary confidence before running (updates after the forecast):
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
  if (question.kind === "slider") {
    const min = question.min ?? -50;
    const max = question.max ?? 50;
    const v = typeof value === "number" ? value : Number(value ?? 0);
    return (
      <div className="space-y-1.5">
        <label className="text-sm font-medium block leading-relaxed">{question.text}</label>
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
      <div className="space-y-1.5">
        <label className="text-sm font-medium block leading-relaxed">{question.text}</label>
        <div className="flex items-center gap-2">
          {(["yes", "no"] as const).map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => onChange(opt)}
              className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                v === opt
                  ? "border-[var(--accent)] bg-[var(--accent)]/10 text-[var(--accent)]"
                  : "border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--accent)]"
              }`}
            >
              {opt === "yes" ? "Yes" : "No"}
            </button>
          ))}
        </div>
      </div>
    );
  }
  // dropdown
  const v = String(value ?? "");
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium block leading-relaxed">{question.text}</label>
      <select
        value={v}
        onChange={(e) => onChange(e.target.value)}
        className="w-full text-xs px-3 py-1.5 rounded-md border border-[var(--border)] bg-[var(--surface)] text-[var(--text)]"
      >
        {(question.options ?? []).map((opt) => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    </div>
  );
}

function RunningPhase({ target }: { target: string }) {
  return (
    <div className="space-y-3">
      <div className="text-sm">
        Running the model to forecast{" "}
        <span className="font-semibold text-[var(--accent)]">{target || "Data"}</span>…
      </div>
      <div className="space-y-2">
        <Bar w="92%" />
        <Bar w="76%" />
      </div>
      <div className="text-[11px] text-[var(--text-muted)]">
        We're combining the statistical model with driver analysis and computing the confidence score.
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
          Try again
        </button>
      </div>
    </div>
  );
}
