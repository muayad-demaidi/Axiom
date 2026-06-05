"use client";
import { useRouter, usePathname } from "next/navigation";
import { useTransition } from "react";

/**
 * Marketing/app language switch between English (prefix-free) and Arabic
 * (`/ar` prefix), matching the `localePrefix: "as-needed"` routing.
 *
 * We compute the current locale from the first path segment, swap to the
 * other locale, persist the choice in the `NEXT_LOCALE` cookie (so
 * next-intl honours it on subsequent visits), and navigate to the
 * equivalent path. Styled to mirror `ThemeToggle` so the header chrome
 * stays consistent.
 */
const LOCALE_COOKIE = "NEXT_LOCALE";

function setLocaleCookie(locale: string) {
  try {
    // 1-year persistent cookie, site-wide.
    document.cookie = `${LOCALE_COOKIE}=${locale}; path=/; max-age=31536000; samesite=lax`;
  } catch {
    /* cookies disabled — navigation still works for this session */
  }
}

export function LanguageToggle() {
  const router = useRouter();
  const pathname = usePathname() || "/";
  const [pending, startTransition] = useTransition();

  const isArabic = pathname === "/ar" || pathname.startsWith("/ar/");
  const nextLocale = isArabic ? "en" : "ar";

  function switchLocale() {
    // Strip an existing `/ar` prefix to get the locale-neutral path.
    let basePath = pathname;
    if (pathname === "/ar") basePath = "/";
    else if (pathname.startsWith("/ar/")) basePath = pathname.slice(3);

    const target =
      nextLocale === "ar"
        ? basePath === "/"
          ? "/ar"
          : `/ar${basePath}`
        : basePath || "/";

    setLocaleCookie(nextLocale);
    startTransition(() => {
      router.push(target);
      router.refresh();
    });
  }

  // Label shows the language you'll switch TO.
  const label = isArabic ? "Switch to English" : "التبديل إلى العربية";
  const glyph = isArabic ? "EN" : "ع";

  return (
    <button
      type="button"
      onClick={switchLocale}
      className="theme-toggle"
      aria-label={label}
      title={label}
      disabled={pending}
      style={{ fontWeight: 600, fontSize: "0.85rem", minWidth: "2.25rem" }}
    >
      {glyph}
    </button>
  );
}
