"use client";
import { Loader2 } from "lucide-react";

export type SpinnerProps = {
  size?: "xs" | "sm" | "md" | "lg";
  label?: string;
  className?: string;
};

const SIZE_CLASS: Record<NonNullable<SpinnerProps["size"]>, string> = {
  xs: "h-3 w-3",
  sm: "h-3.5 w-3.5",
  md: "h-4 w-4",
  lg: "h-5 w-5",
};

export function Spinner({ size = "sm", label, className = "" }: SpinnerProps) {
  return (
    <span
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-1.5 ${className}`}
    >
      <Loader2
        aria-hidden="true"
        className={`${SIZE_CLASS[size]} animate-spin`}
      />
      {label ? (
        <span className="text-xs">{label}</span>
      ) : (
        <span className="sr-only">جاري التحميل…</span>
      )}
    </span>
  );
}
