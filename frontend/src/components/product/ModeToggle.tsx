"use client";
/**
 * Pill-shaped Guided/Expert toggle.
 *
 * Used in the global app header and in any inline "switch mode" CTAs.
 * Lives outside any project workspace by default (writes the user-level
 * preference); pass ``projectId`` when rendering inside a project to
 * edit that project's per-project mode override.
 */
import { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { useMode, type Mode } from "@/lib/modeContext";

type Size = "md" | "sm";

type ModeToggleProps = {
  /** When provided, the toggle edits the project-level mode override. */
  projectId?: number | null;
  /** Visual size — "sm" used for inline switchers in chat bubbles. */
  size?: Size;
  /** Optional label to render before the segments. */
  label?: string | null;
  /** Optional callback invoked after a mode change settles. */
  onChange?: (m: Mode) => void;
  className?: string;
};

export function ModeToggle({
  projectId = null,
  size = "md",
  label = null,
  onChange,
  className = "",
}: ModeToggleProps) {
  const { mode, setMode } = useMode(projectId);
  const t = useTranslations("appShell");

  // The resolved mode comes from a context whose state is rehydrated
  // from localStorage / the API inside an effect. Until that first
  // post-mount tick lands, the active segment may differ between the
  // server-rendered HTML and the client's eventual choice. Render a
  // stable placeholder for that first paint to keep React's hydration
  // happy and avoid a Guided→Expert flash.
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  const padding =
    size === "sm" ? "px-2.5 py-1 text-[12px]" : "px-3 py-1.5 text-[12px]";
  const dot = size === "sm" ? "h-1.5 w-1.5" : "h-2 w-2";

  function pick(m: Mode) {
    if (m === mode) return;
    void setMode(m).then(() => onChange?.(m));
  }

  return (
    <div
      role="group"
      aria-label={t("modeAria")}
      suppressHydrationWarning
      className={`inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] bg-[var(--surface)] p-0.5 ${className}`}
    >
      {label && (
        <span className="pl-2 pr-1 font-mono text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
          {label}
        </span>
      )}
      <Segment
        active={mounted && mode === "guided"}
        padding={padding}
        dot={dot}
        onClick={() => pick("guided")}
        title={t("modeGuidedTitle")}
      >
        {t("modeGuided")}
      </Segment>
      <Segment
        active={mounted && mode === "expert"}
        padding={padding}
        dot={dot}
        onClick={() => pick("expert")}
        title={t("modeExpertTitle")}
      >
        {t("modeExpert")}
      </Segment>
    </div>
  );
}

function Segment({
  active,
  padding,
  dot,
  onClick,
  title,
  children,
}: {
  active: boolean;
  padding: string;
  dot: string;
  onClick: () => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      title={title}
      className={`inline-flex items-center gap-1.5 rounded-full font-medium transition-colors ${padding} ${
        active
          ? "bg-[var(--accent)] text-white shadow-sm"
          : "text-[var(--text-muted)] hover:text-[var(--text)]"
      }`}
    >
      <span
        aria-hidden
        className={`rounded-full ${dot} ${
          active ? "bg-white" : "bg-[var(--text-muted)] opacity-50"
        }`}
      />
      {children}
    </button>
  );
}
