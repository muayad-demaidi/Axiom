"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type Question = {
  id: number;
  kind: string;
  prompt: string;
  status: string;
  options?: { value: string; label: string }[] | null;
};

type Bundle = {
  questions?: Question[];
  tables?: { dataset_name: string }[];
};

export function OpenQuestionsBar({
  projectId,
  onAskQuestion,
  refreshKey = 0,
}: {
  projectId: number | null;
  onAskQuestion: (q: string) => void;
  refreshKey?: number;
}) {
  const [questions, setQuestions] = useState<Question[]>([]);
  const [enoughDatasets, setEnoughDatasets] = useState(false);

  useEffect(() => {
    if (projectId == null) return;
    let cancel = false;
    (async () => {
      try {
        const b = await api<Bundle>(
          `/api/projects/${projectId}/data-model`
        );
        if (cancel) return;
        setEnoughDatasets((b.tables?.length ?? 0) >= 2);
        setQuestions(
          (b.questions ?? [])
            .filter((q) => q.status === "open")
            .slice(0, 6)
        );
      } catch {
        if (!cancel) {
          setQuestions([]);
          setEnoughDatasets(false);
        }
      }
    })();
    return () => {
      cancel = true;
    };
  }, [projectId, refreshKey]);

  if (!enoughDatasets || questions.length === 0) return null;

  return (
    <div className="px-1 pb-2">
      <div className="text-[10px] font-mono uppercase tracking-[0.18em] text-[var(--text-muted)] mb-1.5">
        Open questions about your data
      </div>
      <div className="flex flex-wrap gap-1.5">
        {questions.map((q) => (
          <button
            key={q.id}
            type="button"
            onClick={() => onAskQuestion(q.prompt)}
            className="text-[11px] px-2 py-1 rounded-full border border-[var(--border)] bg-[var(--surface)] hover:bg-[var(--surface-alt)] text-[var(--text)] max-w-[420px] truncate"
            title={q.prompt}
          >
            {q.prompt}
          </button>
        ))}
      </div>
    </div>
  );
}
