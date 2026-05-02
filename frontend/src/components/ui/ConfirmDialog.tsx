"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslations } from "next-intl";
import { AlertTriangle } from "lucide-react";

type ConfirmKind = "danger" | "default";

type ConfirmOptions = {
  title?: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  kind?: ConfirmKind;
};

type ConfirmContextValue = {
  confirm: (opts?: ConfirmOptions) => Promise<boolean>;
};

const ConfirmContext = createContext<ConfirmContextValue | null>(null);

export function useConfirm(): ConfirmContextValue["confirm"] {
  const ctx = useContext(ConfirmContext);
  if (!ctx) {
    // Fallback to native confirm so calls don't blow up in isolation.
    return async (opts) => {
      if (typeof window === "undefined") return false;
      const text = [opts?.title, opts?.description].filter(Boolean).join("\n\n");
      return window.confirm(text || "Are you sure?");
    };
  }
  return ctx.confirm;
}

type DialogState = ConfirmOptions & {
  open: boolean;
  resolve?: (value: boolean) => void;
};

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const t = useTranslations("confirm");
  const [state, setState] = useState<DialogState>({ open: false });
  const confirmBtnRef = useRef<HTMLButtonElement | null>(null);

  const confirm = useCallback<ConfirmContextValue["confirm"]>((opts = {}) => {
    return new Promise<boolean>((resolve) => {
      setState({
        open: true,
        title: opts.title ?? t("defaultTitle"),
        description: opts.description,
        confirmLabel: opts.confirmLabel ?? t("confirmCta"),
        cancelLabel: opts.cancelLabel ?? t("cancelCta"),
        kind: opts.kind ?? "danger",
        resolve,
      });
    });
  }, [t]);

  const close = useCallback(
    (value: boolean) => {
      setState((cur) => {
        cur.resolve?.(value);
        return { open: false };
      });
    },
    [],
  );

  useEffect(() => {
    if (!state.open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") close(false);
      else if (e.key === "Enter") close(true);
    }
    document.addEventListener("keydown", onKey);
    const timer = window.setTimeout(() => confirmBtnRef.current?.focus(), 30);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.clearTimeout(timer);
    };
  }, [state.open, close]);

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      {state.open && (
        <div
          className="fixed inset-0 z-[110] flex items-center justify-center px-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-title"
        >
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => close(false)}
            aria-hidden="true"
          />
          <div
            className="relative w-full max-w-sm rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-xl p-5 text-start"
          >
            <div className="flex items-start gap-3">
              {state.kind === "danger" && (
                <span
                  className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-red-500/10 text-red-600 shrink-0"
                  aria-hidden="true"
                >
                  <AlertTriangle className="h-5 w-5" />
                </span>
              )}
              <div className="flex-1 min-w-0">
                <h2
                  id="confirm-title"
                  className="text-base font-semibold text-[var(--text)]"
                >
                  {state.title}
                </h2>
                {state.description && (
                  <p className="text-sm text-[var(--text-muted)] mt-1.5 leading-relaxed">
                    {state.description}
                  </p>
                )}
              </div>
            </div>
            <div className="mt-5 flex items-center gap-2 justify-end">
              <button
                type="button"
                onClick={() => close(false)}
                className="inline-flex items-center justify-center rounded-md border border-[var(--border)] bg-[var(--surface)] px-4 text-sm font-semibold text-[var(--text)] hover:bg-[var(--surface-alt)]"
                style={{ minHeight: 44, minWidth: 44 }}
              >
                {state.cancelLabel}
              </button>
              <button
                ref={confirmBtnRef}
                type="button"
                onClick={() => close(true)}
                className={`inline-flex items-center justify-center rounded-md px-4 text-sm font-semibold text-white ${
                  state.kind === "danger"
                    ? "bg-red-600 hover:bg-red-700"
                    : "bg-[var(--accent)] hover:opacity-90"
                }`}
                style={{ minHeight: 44, minWidth: 44 }}
              >
                {state.confirmLabel}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}
