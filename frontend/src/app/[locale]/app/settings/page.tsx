"use client";
/**
 * User settings page.
 *
 * Lets the user pick a UI language (EN / AR). Saving:
 *  1. Persists `locale` to the user profile via PATCH /api/auth/me.
 *  2. Writes the `NEXT_LOCALE` cookie so middleware honours the
 *     choice on every subsequent request.
 *  3. Navigates to the locale-prefixed (or unprefixed-default) URL so
 *     the document `dir` / `lang` flip immediately.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter, useParams, usePathname } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { api, getToken } from "@/lib/api";
import { errMessage } from "@/lib/types";
import { useToast } from "@/components/ui/Toast";
import { LOCALES, DEFAULT_LOCALE, LOCALE_COOKIE, type Locale } from "@/i18n/config";

const LOCALE_LABEL_KEY: Record<Locale, "english" | "arabic"> = {
  en: "english",
  ar: "arabic",
};

function setLocaleCookie(locale: Locale) {
  if (typeof document === "undefined") return;
  // 1-year persistence is plenty; the cookie is reset on every save.
  const oneYear = 60 * 60 * 24 * 365;
  document.cookie = `${LOCALE_COOKIE}=${locale}; Path=/; Max-Age=${oneYear}; SameSite=Lax`;
}

function pathWithoutLocale(pathname: string, currentLocale: string): string {
  const prefix = `/${currentLocale}`;
  if (pathname === prefix) return "/";
  if (pathname.startsWith(`${prefix}/`)) return pathname.slice(prefix.length);
  return pathname;
}

function pathWithLocale(pathname: string, locale: Locale): string {
  const stripped = pathname.startsWith("/") ? pathname : `/${pathname}`;
  if (locale === DEFAULT_LOCALE) return stripped;
  return `/${locale}${stripped === "/" ? "" : stripped}`;
}

export default function SettingsPage() {
  const tCommon = useTranslations("common");
  const t = useTranslations("settings");
  const router = useRouter();
  const params = useParams();
  const pathname = usePathname() || "/";
  const activeLocale = useLocale();
  const toast = useToast();

  const [selected, setSelected] = useState<Locale>(activeLocale as Locale);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [authed, setAuthed] = useState(true);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      setAuthed(false);
      return;
    }
    api<{ locale?: string }>("/api/auth/me")
      .then((u) => {
        if (u?.locale && (LOCALES as readonly string[]).includes(u.locale)) {
          setSelected(u.locale as Locale);
        }
      })
      .catch(() => { /* harmless — keep current */ });
  }, []);

  const save = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      if (authed) {
        await api("/api/auth/me", {
          method: "PATCH",
          json: { locale: selected },
        });
      }
      setLocaleCookie(selected);
      toast.success(t("savedToast"));
      // Navigate to the same page under the new locale prefix so the
      // tree re-renders with the new dir/lang and catalogues.
      const currentPathLocale = (params?.locale as string) || activeLocale;
      const bare = pathWithoutLocale(pathname, currentPathLocale);
      const next = pathWithLocale(bare, selected);
      router.replace(next);
      router.refresh();
    } catch (e) {
      setError(errMessage(e));
      toast.error(t("saveFailed"));
    } finally {
      setSaving(false);
    }
  }, [selected, authed, toast, t, router, params, pathname, activeLocale]);

  return (
    <div className="max-w-2xl">
      <div>
        <div className="text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
          {t("title")}
        </div>
        <h1 className="text-2xl font-semibold mt-1">{t("title")}</h1>
        <p className="text-sm text-[var(--text-muted)] mt-1">{t("subtitle")}</p>
      </div>

      <section className="mt-6 card">
        <h2 className="font-semibold text-sm">{t("languageSection")}</h2>
        <p className="text-xs text-[var(--text-muted)] mt-1">{t("languageHelp")}</p>
        <div className="mt-4 space-y-2">
          {LOCALES.map((loc) => {
            const id = `locale-${loc}`;
            const checked = selected === loc;
            return (
              <label
                key={loc}
                htmlFor={id}
                className={`flex items-center gap-3 rounded-md border p-3 cursor-pointer text-sm ${
                  checked
                    ? "border-[var(--accent)] bg-[var(--accent)]/10"
                    : "border-[var(--border)] hover:border-[var(--accent)]/50"
                }`}
              >
                <input
                  id={id}
                  type="radio"
                  name="locale"
                  value={loc}
                  checked={checked}
                  onChange={() => setSelected(loc)}
                  className="accent-[var(--accent)]"
                />
                <span className="font-medium">{tCommon(LOCALE_LABEL_KEY[loc])}</span>
                <span className="ms-auto text-[10px] uppercase tracking-widest text-[var(--text-muted)]">
                  {loc}
                </span>
              </label>
            );
          })}
        </div>
        {error && (
          <div className="mt-3 text-xs text-red-500" role="alert">{error}</div>
        )}
        <div className="mt-5 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void save()}
            disabled={saving || selected === activeLocale}
            className="btn btn-primary text-sm disabled:opacity-50"
            style={{ minHeight: 44 }}
          >
            {saving ? tCommon("saving") : tCommon("save")}
          </button>
        </div>
      </section>
    </div>
  );
}
