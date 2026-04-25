"use client";
import Link from "next/link";
import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ArrowUp, Loader2, Paperclip, Plug } from "lucide-react";

export type FloatingComposerHandle = {
  focus: () => void;
};

type FloatingComposerProps = {
  value: string;
  onValueChange: (v: string) => void;
  onSubmit: (text: string) => void;
  placeholder?: string;
  busy?: boolean;
  disabled?: boolean;
  /** When set, the attach button opens a native file picker that calls
   * `onAttachFile`. Otherwise it links to `attachHref`. */
  onAttachFile?: (file: File) => void;
  attachAccept?: string;
  attachBusy?: boolean;
  attachHref?: string;
  connectorsHref?: string;
  /** Optional small error string rendered under the composer (e.g. for
   * inline upload failures in the chat surface). */
  errorText?: string | null;
  /** Shared layoutId for the send button so it can morph between
   * surfaces (landing → chat) when Framer Motion is enabled. */
  sendLayoutId?: string;
};

export const FloatingComposer = forwardRef<FloatingComposerHandle, FloatingComposerProps>(
  function FloatingComposer(
    {
      value,
      onValueChange,
      onSubmit,
      placeholder = "Ask anything about your data…",
      busy = false,
      disabled = false,
      onAttachFile,
      attachAccept = ".csv,.tsv,.xlsx,.xls,.json",
      attachBusy = false,
      attachHref,
      connectorsHref,
      errorText = null,
      sendLayoutId,
    },
    ref
  ) {
    const taRef = useRef<HTMLTextAreaElement | null>(null);
    const fileRef = useRef<HTMLInputElement | null>(null);
    const reduceMotion = useReducedMotion();

    useImperativeHandle(ref, () => ({
      focus: () => taRef.current?.focus(),
    }));

    // Autosize the textarea with content, capped at ~10 lines.
    useEffect(() => {
      const el = taRef.current;
      if (!el) return;
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, 240) + "px";
    }, [value]);

    function send() {
      const text = value.trim();
      if (!text || busy || disabled) return;
      onSubmit(text);
    }

    function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    }

    const showFilePicker = !!onAttachFile;

    const motionProps = reduceMotion
      ? {}
      : {
          layoutId: sendLayoutId,
          transition: { duration: 0.18, ease: [0.4, 0, 0.2, 1] as const },
        };

    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          send();
        }}
        className="w-full"
      >
        {showFilePicker && (
          <input
            ref={fileRef}
            type="file"
            accept={attachAccept}
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f && onAttachFile) onAttachFile(f);
              if (fileRef.current) fileRef.current.value = "";
            }}
          />
        )}
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--surface)] shadow-sm p-3 text-left">
          <textarea
            ref={taRef}
            value={value}
            onChange={(e) => onValueChange(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={placeholder}
            rows={1}
            // The autosize effect mutates `style.height` on mount, which
            // would otherwise produce a hydration mismatch warning.
            suppressHydrationWarning
            className="w-full resize-none bg-transparent outline-none text-sm leading-6 text-[var(--text)] placeholder:text-[var(--text-muted)] px-1 py-2"
            disabled={disabled}
            aria-label="Message composer"
          />
          <div className="mt-2 flex items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              {showFilePicker ? (
                <button
                  type="button"
                  onClick={() => fileRef.current?.click()}
                  disabled={attachBusy || busy}
                  className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1.5 rounded-md hover:bg-[var(--surface-alt)] disabled:opacity-50"
                  title="Upload a CSV or Excel file"
                >
                  {attachBusy ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Paperclip className="h-3.5 w-3.5" />
                  )}
                  <span>Attach data</span>
                </button>
              ) : attachHref ? (
                <Link
                  href={attachHref}
                  className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1.5 rounded-md hover:bg-[var(--surface-alt)]"
                  title="Upload a CSV or Excel file"
                >
                  <Paperclip className="h-3.5 w-3.5" />
                  <span>Attach data</span>
                </Link>
              ) : null}
              {connectorsHref && (
                <Link
                  href={connectorsHref}
                  className="inline-flex items-center gap-1.5 text-xs text-[var(--text-muted)] hover:text-[var(--text)] px-2 py-1.5 rounded-md hover:bg-[var(--surface-alt)]"
                  title="Connect to a data source"
                >
                  <Plug className="h-3.5 w-3.5" />
                  <span>Connectors</span>
                </Link>
              )}
            </div>
            <motion.button
              {...motionProps}
              type="submit"
              disabled={busy || disabled || !value.trim()}
              className="inline-flex items-center justify-center h-8 w-8 rounded-full bg-[var(--accent)] text-white disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90"
              aria-label={busy ? "Sending…" : "Send"}
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
              )}
            </motion.button>
          </div>
        </div>
        {errorText && (
          <div className="text-[11px] text-red-500 mt-2 px-1">{errorText}</div>
        )}
      </form>
    );
  }
);
