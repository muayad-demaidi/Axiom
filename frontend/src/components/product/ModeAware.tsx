"use client";
/**
 * Reusable building blocks for Guided/Expert mode-aware tool screens.
 *
 * The five screens (Clean, Transform, Visualize, Predict, Statistics,
 * Model) share the same shape:
 *
 *   GuidedMode
 *     - Outcome cards (one-click "Do the right thing")
 *     - "Advanced" expander that swaps in the Expert controls
 *
 *   ExpertMode
 *     - Full controls + JSON / metrics surfaced
 *
 *   Result cards in Guided also expose a "View technical details"
 *   disclosure that mirrors what Expert would have shown, plus an
 *   "Open in Expert Mode" handoff button.
 *
 * Putting these in one place keeps each tool page short.
 */
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMode } from "@/lib/modeContext";

/** Render `guided` content in Guided Mode and `expert` in Expert Mode. */
export function ModeAwareSection({
  projectId,
  guided,
  expert,
}: {
  projectId?: number | null;
  guided: React.ReactNode;
  expert: React.ReactNode;
}) {
  const { mode } = useMode(projectId ?? null);
  return <>{mode === "expert" ? expert : guided}</>;
}

/**
 * Always-visible "Advanced" expander that reveals Expert-style controls
 * inside a Guided screen. Includes a built-in "Switch this project to
 * Expert Mode" CTA so users who keep opening it can flip permanently.
 */
export function AdvancedExpander({
  projectId,
  title = "Advanced",
  hint,
  children,
}: {
  projectId?: number | null;
  title?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const { setMode } = useMode(projectId ?? null);
  return (
    <div className="mt-4 border-t border-[var(--border)] pt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text)]"
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        {title}
        {hint && (
          <span className="text-[10px] text-[var(--text-muted)] font-normal">
            — {hint}
          </span>
        )}
      </button>
      {open && (
        <div className="mt-3">
          <div className="rounded-md border border-dashed border-[var(--border)] p-3 bg-[var(--surface-alt)]/50">
            {children}
          </div>
          <button
            type="button"
            onClick={() => void setMode("expert")}
            className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-[var(--accent)] hover:underline"
          >
            <span aria-hidden>↗</span> Switch this project to Expert Mode
          </button>
        </div>
      )}
    </div>
  );
}

/**
 * "View technical details" disclosure for Guided result cards. Hides
 * the technical payload behind a click so casual users aren't bombarded
 * with JSON, but still surfaces an "Open in Expert Mode" handoff that
 * flips the project mode.
 */
export function TechnicalDetails({
  projectId,
  label = "View technical details",
  expertHandoffLabel = "Open in Expert Mode",
  showHandoff = true,
  /** Where to take the user after flipping to Expert. Defaults to the
   *  current route so the same screen re-renders in Expert form, but
   *  callers can pass a more specific path (e.g. /app/clean#duplicates)
   *  to land them on the right control directly. */
  expertHref,
  children,
}: {
  projectId?: number | null;
  label?: string;
  expertHandoffLabel?: string;
  showHandoff?: boolean;
  expertHref?: string;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const { mode, setMode } = useMode(projectId ?? null);
  // Flip the mode AND, if a target route was supplied, navigate to it
  // so the "Open in Expert Mode" CTA is a true handoff (not just a
  // silent toggle). Stays on the current page when no href is passed.
  const handoff = async () => {
    await setMode("expert");
    if (expertHref) router.push(expertHref);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };
  // In Expert Mode the disclosure is redundant — the parent screen
  // already shows technicals — so we render the body always-open.
  if (mode === "expert") {
    return (
      <div className="mt-3 text-xs">
        <div className="font-mono uppercase tracking-widest text-[10px] text-[var(--text-muted)] mb-1">
          Technical
        </div>
        <div>{children}</div>
      </div>
    );
  }
  return (
    <div className="mt-3 text-xs">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="inline-flex items-center gap-1.5 text-[11px] text-[var(--text-muted)] hover:text-[var(--text)]"
      >
        <span aria-hidden>{open ? "▾" : "▸"}</span>
        {label}
      </button>
      {open && (
        <div className="mt-2 rounded-md border border-[var(--border)] bg-[var(--surface-alt)]/50 p-3">
          {children}
          {showHandoff && (
            <button
              type="button"
              onClick={() => void handoff()}
              className="mt-2 inline-flex items-center gap-1.5 text-[11px] text-[var(--accent)] hover:underline"
            >
              <span aria-hidden>↗</span> {expertHandoffLabel}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Outcome-first action card used on Guided tool screens. One headline,
 * one short description, and one primary action button.
 */
export function GuidedActionCard({
  icon,
  title,
  description,
  cta,
  onAction,
  busy = false,
  disabled = false,
}: {
  icon?: React.ReactNode;
  title: string;
  description: string;
  cta: string;
  onAction: () => void;
  busy?: boolean;
  disabled?: boolean;
}) {
  return (
    <div className="card p-4 flex flex-col h-full">
      <div className="flex items-start gap-3">
        {icon && (
          <div
            aria-hidden
            className="h-9 w-9 rounded-md bg-[var(--accent)]/10 text-[var(--accent)] flex items-center justify-center shrink-0"
          >
            {icon}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <div className="font-semibold text-sm">{title}</div>
          <div className="text-xs text-[var(--text-muted)] mt-1">
            {description}
          </div>
        </div>
      </div>
      <div className="flex-1" />
      <button
        type="button"
        onClick={onAction}
        disabled={disabled || busy}
        className="mt-3 btn btn-primary text-xs disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {busy ? "Working…" : cta}
      </button>
    </div>
  );
}

/**
 * Eyebrow + heading pair for a tool screen, mode-aware. Guided uses
 * a friendly headline, Expert uses a precise one.
 */
export function ModeAwareHeading({
  projectId,
  eyebrow,
  guidedTitle,
  expertTitle,
  guidedSubtitle,
  expertSubtitle,
}: {
  projectId?: number | null;
  eyebrow: string;
  guidedTitle: string;
  expertTitle: string;
  guidedSubtitle?: string;
  expertSubtitle?: string;
}) {
  const { mode } = useMode(projectId ?? null);
  return (
    <div>
      <div className="eyebrow">{eyebrow}</div>
      <h1 className="text-2xl font-semibold tracking-tight mt-1">
        {mode === "expert" ? expertTitle : guidedTitle}
      </h1>
      {(mode === "expert" ? expertSubtitle : guidedSubtitle) && (
        <p className="text-[var(--text-muted)] text-sm mt-2 max-w-2xl">
          {mode === "expert" ? expertSubtitle : guidedSubtitle}
        </p>
      )}
    </div>
  );
}
