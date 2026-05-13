"use client";
/**
 * User settings page. The locale picker has been removed — the app
 * is English-only. The page is kept as a stub so the sidebar link
 * and `/app/settings` route still resolve, and we have a place to
 * add future preferences without re-introducing the route.
 */
import { useTranslations } from "next-intl";

export default function SettingsPage() {
  const t = useTranslations("settings");
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
        <h2 className="font-semibold text-sm">Account</h2>
        <p className="text-xs text-[var(--text-muted)] mt-1">
          More preferences are coming soon. AXIOM is currently
          English-only — the assistant will reply in whichever language
          you write to it in.
        </p>
      </section>
    </div>
  );
}
