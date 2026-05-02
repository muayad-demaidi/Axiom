"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { api, getToken, setToken, ApiError } from "@/lib/api";
import { clearAllCached } from "@/lib/workspaceCache";

type Me = {
  id: number;
  email: string;
  username: string;
  subscription_type?: string | null;
  trial_end?: string | null;
};

type Variant = "marketing" | "app";

export function UserMenu({ variant = "marketing" }: { variant?: Variant }) {
  const router = useRouter();
  const tNav = useTranslations("nav");
  const [me, setMe] = useState<Me | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setLoaded(true);
      return;
    }
    let cancelled = false;
    api<Me>("/api/auth/me")
      .then((u) => {
        if (cancelled) return;
        setMe(u);
        setLoaded(true);
      })
      .catch((e: ApiError) => {
        if (cancelled) return;
        if (e.status === 401) setToken(null);
        setMe(null);
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    function onDoc(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  function logout() {
    setToken(null);
    clearAllCached();
    setMe(null);
    setOpen(false);
    router.push("/");
  }

  if (!loaded) {
    return (
      <div
        aria-hidden
        className="h-8 w-24 rounded-md bg-[var(--surface-2,rgba(255,255,255,0.04))] animate-pulse"
      />
    );
  }

  if (!me) {
    if (variant === "app") {
      return (
        <Link href="/login" className="btn btn-ghost text-xs">
          {tNav("login")}
        </Link>
      );
    }
    return (
      <>
        <Link href="/login" className="btn btn-ghost hidden sm:inline-flex">
          {tNav("login")}
        </Link>
        <Link href="/signup" className="btn btn-primary">
          {tNav("signup")} →
        </Link>
      </>
    );
  }

  const display = me.username || me.email.split("@")[0];
  const initials = display.slice(0, 2).toUpperCase();

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        className="flex items-center gap-2 rounded-full pl-1 pr-3 py-1 border border-[var(--border)] hover:border-[var(--accent)] transition-colors"
      >
        <span
          aria-hidden
          className="h-7 w-7 rounded-full grid place-items-center text-xs font-semibold bg-[var(--accent)]/15 text-[var(--accent)]"
        >
          {initials}
        </span>
        <span className="text-sm font-medium max-w-[140px] truncate">{display}</span>
        <svg
          aria-hidden
          width="12"
          height="12"
          viewBox="0 0 12 12"
          className={`transition-transform ${open ? "rotate-180" : ""}`}
        >
          <path d="M2 4l4 4 4-4" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 mt-2 w-64 rounded-xl border border-[var(--border)] bg-[var(--surface)] shadow-xl overflow-hidden z-50"
        >
          <div className="px-4 py-3 border-b border-[var(--border)]">
            <div className="text-sm font-semibold truncate">{display}</div>
            <div className="text-xs text-[var(--text-muted)] truncate">{me.email}</div>
            {me.subscription_type && (
              <div className="mt-1 inline-block text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded bg-[var(--accent)]/15 text-[var(--accent)]">
                {me.subscription_type}
              </div>
            )}
          </div>
          <nav className="py-1 text-sm">
            {variant === "marketing" && (
              <Link
                href="/app"
                onClick={() => setOpen(false)}
                className="block px-4 py-2 hover:bg-[var(--accent)]/10"
                role="menuitem"
              >
                {tNav("dashboard")}
              </Link>
            )}
            <Link
              href="/app/projects"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 hover:bg-[var(--accent)]/10"
              role="menuitem"
            >
              {tNav("projects")}
            </Link>
            <Link
              href="/app/connectors"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 hover:bg-[var(--accent)]/10"
              role="menuitem"
            >
              {tNav("connectors")}
            </Link>
            <Link
              href="/app/settings"
              onClick={() => setOpen(false)}
              className="block px-4 py-2 hover:bg-[var(--accent)]/10"
              role="menuitem"
            >
              {tNav("settings")}
            </Link>
          </nav>
          <div className="border-t border-[var(--border)]">
            <button
              type="button"
              onClick={logout}
              role="menuitem"
              className="w-full text-start px-4 py-2 text-sm text-red-400 hover:bg-red-500/10"
            >
              {tNav("logout")}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
