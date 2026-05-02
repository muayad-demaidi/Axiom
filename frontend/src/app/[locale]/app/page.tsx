"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { api, ApiError, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { useMode } from "@/lib/modeContext";
import { ModeToggle } from "@/components/product/ModeToggle";
import { FloatingComposer } from "@/components/product/FloatingComposer";

type QuickStartResponse = {
  project_id: number;
  session_id: number;
};

export default function ProductHome() {
  const router = useRouter();
  const t = useTranslations("productHome");
  const locale = useLocale();
  const dir: "rtl" | "ltr" = locale === "ar" ? "rtl" : "ltr";
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { mode } = useMode();

  const suggestions = useMemo(
    () =>
      mode === "expert"
        ? [
            t("expertSuggestion1"),
            t("expertSuggestion2"),
            t("expertSuggestion3"),
            t("expertSuggestion4"),
          ]
        : [
            t("guidedSuggestion1"),
            t("guidedSuggestion2"),
            t("guidedSuggestion3"),
            t("guidedSuggestion4"),
          ],
    [mode, t]
  );
  const placeholder = mode === "expert" ? t("expertPlaceholder") : t("guidedPlaceholder");

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
  }, [router]);

  async function start(text: string) {
    const trimmed = text.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api<QuickStartResponse>("/api/chats/quick", {
        method: "POST",
        json: {},
      });
      router.push(
        `/app/project/${res.project_id}?session=${res.session_id}&q=${encodeURIComponent(trimmed)}`
      );
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setError(errMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      dir={dir}
      className="min-h-[calc(100vh-7rem)] flex items-start justify-center pt-16 px-4"
    >
      <div className="w-full max-w-3xl text-center">
        <div className="text-[12px] font-mono uppercase tracking-[0.25em] text-[var(--text-muted)] mb-3">
          {t("eyebrow")}
        </div>
        <h1 className="text-3xl md:text-4xl font-semibold tracking-tight">
          {mode === "expert" ? t("expertTitle") : t("guidedTitle")}
        </h1>
        <p className="text-[var(--text-muted)] mt-3 text-sm">
          {mode === "expert" ? t("expertSubtitle") : t("guidedSubtitle")}
        </p>
        <div className="mt-4 flex items-center justify-center gap-2">
          <ModeToggle size="sm" />
          <span className="text-[12px] font-mono uppercase tracking-widest text-[var(--text-muted)]">
            {t("appliesToNew")}
          </span>
        </div>

        <div className="mt-8 mx-auto">
          <FloatingComposer
            value={input}
            onValueChange={setInput}
            onSubmit={(text) => {
              setInput(text);
              start(text);
            }}
            placeholder={placeholder}
            busy={busy}
            attachHref="/app/upload?back=/app"
            connectorsHref="/app/connectors"
            sendLayoutId="axiom-composer-send"
          />
        </div>

        {error && (
          <div
            role="alert"
            className="text-red-600 text-sm mt-3 rounded border border-red-500/30 bg-red-500/10 px-3 py-2 text-start"
          >
            {error}
          </div>
        )}

        <div className="mt-6 flex flex-wrap justify-center gap-2">
          {suggestions.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => start(s)}
              disabled={busy}
              className="text-[12px] text-[var(--text-muted)] hover:text-[var(--text)] border border-[var(--border)] hover:border-[var(--accent)] rounded-full px-3 py-1.5 transition-colors"
              style={{ minHeight: 32 }}
            >
              {s}
            </button>
          ))}
        </div>

        <div className="mt-10 text-[12px] text-[var(--text-muted)]">
          {t("lookingForProject")}{" "}
          <Link href="/app/projects" className="text-[var(--accent)] hover:underline">
            {t("openProjectsIndex")}
          </Link>
          .
        </div>
      </div>
    </div>
  );
}
