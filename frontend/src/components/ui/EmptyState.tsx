"use client";
import type { ReactNode } from "react";

export type EmptyStateProps = {
  icon?: ReactNode;
  title?: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  dir?: "rtl" | "ltr";
};

export function EmptyState({
  icon,
  title = "لا توجد بيانات بعد",
  description,
  action,
  className = "",
  dir = "rtl",
}: EmptyStateProps) {
  return (
    <div
      dir={dir}
      className={`flex flex-col items-center justify-center text-center gap-2 px-4 py-6 border border-dashed border-[var(--border)] rounded-xl bg-[var(--surface-alt)]/40 ${className}`}
    >
      {icon ? (
        <div
          className="inline-flex items-center justify-center h-10 w-10 rounded-full bg-[var(--accent)]/10 text-[var(--accent)]"
          aria-hidden="true"
        >
          {icon}
        </div>
      ) : null}
      <div className="text-sm font-semibold text-[var(--text)]">{title}</div>
      {description ? (
        <div className="text-xs text-[var(--text-muted)] leading-relaxed max-w-xs">
          {description}
        </div>
      ) : null}
      {action ? <div className="mt-1">{action}</div> : null}
    </div>
  );
}
