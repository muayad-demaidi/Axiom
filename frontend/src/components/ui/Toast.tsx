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
import { CheckCircle2, AlertTriangle, Info, X } from "lucide-react";

export type ToastVariant = "success" | "error" | "info";

type ToastItem = {
  id: number;
  message: string;
  variant: ToastVariant;
  duration: number;
};

type ToastContextValue = {
  show: (message: string, opts?: { variant?: ToastVariant; duration?: number }) => void;
  success: (message: string, duration?: number) => void;
  error: (message: string, duration?: number) => void;
  info: (message: string, duration?: number) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    // Graceful no-op so components remain usable in isolation/tests.
    return {
      show: () => {},
      success: () => {},
      error: () => {},
      info: () => {},
    };
  }
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const idRef = useRef(0);

  const dismiss = useCallback((id: number) => {
    setItems((cur) => cur.filter((t) => t.id !== id));
  }, []);

  const show = useCallback<ToastContextValue["show"]>((message, opts) => {
    const variant = opts?.variant ?? "success";
    const duration = opts?.duration ?? 3000;
    idRef.current += 1;
    const id = idRef.current;
    setItems((cur) => [...cur, { id, message, variant, duration }]);
    if (duration > 0) {
      window.setTimeout(() => dismiss(id), duration);
    }
  }, [dismiss]);

  const value = useMemo<ToastContextValue>(
    () => ({
      show,
      success: (message, duration) => show(message, { variant: "success", duration }),
      error: (message, duration) => show(message, { variant: "error", duration }),
      info: (message, duration) => show(message, { variant: "info", duration }),
    }),
    [show],
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <ToastViewport items={items} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}

function ToastViewport({
  items,
  onDismiss,
}: {
  items: ToastItem[];
  onDismiss: (id: number) => void;
}) {
  return (
    <div
      aria-live="polite"
      aria-atomic="true"
      className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[100] flex flex-col items-center gap-2 pointer-events-none w-full max-w-sm px-3"
      dir="rtl"
    >
      {items.map((t) => (
        <ToastBubble key={t.id} item={t} onDismiss={onDismiss} />
      ))}
    </div>
  );
}

function ToastBubble({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: (id: number) => void;
}) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const t = window.setTimeout(() => setVisible(true), 10);
    return () => window.clearTimeout(t);
  }, []);

  const palette =
    item.variant === "error"
      ? "border-red-500/40 bg-red-500/10 text-red-700"
      : item.variant === "info"
      ? "border-[var(--accent)]/40 bg-[var(--accent)]/10 text-[var(--accent)]"
      : "border-emerald-500/40 bg-emerald-500/10 text-emerald-700";

  const Icon =
    item.variant === "error"
      ? AlertTriangle
      : item.variant === "info"
      ? Info
      : CheckCircle2;

  return (
    <div
      role={item.variant === "error" ? "alert" : "status"}
      className={`pointer-events-auto inline-flex items-center gap-2 rounded-full border px-4 py-2 text-sm shadow-lg backdrop-blur transition-all duration-200 ${palette} ${
        visible ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
      }`}
      style={{ minHeight: 44 }}
    >
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="leading-snug">{item.message}</span>
      <button
        type="button"
        onClick={() => onDismiss(item.id)}
        className="ml-1 inline-flex items-center justify-center h-6 w-6 rounded-full hover:bg-black/10"
        aria-label="إغلاق"
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
      </button>
    </div>
  );
}
