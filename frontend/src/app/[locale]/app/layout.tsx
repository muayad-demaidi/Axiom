import Link from "next/link";
import { Suspense } from "react";
import { getTranslations } from "next-intl/server";
import { ProductSidebar } from "@/components/product/ProductSidebar";
import { UserMenu } from "@/components/UserMenu";
import { LanguageToggle } from "@/components/LanguageToggle";
import { LogoMark } from "@/components/LogoMark";
import { AppChrome, HeaderToggle } from "@/components/product/AppChrome";

export const metadata = { title: "AXIOM — Workspace" };

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const t = await getTranslations("appShell");
  return (
    <AppChrome>
      <div className="min-h-screen flex flex-col bg-[var(--surface)]">
        <header className="border-b border-[var(--border)] bg-[var(--surface)] sticky top-0 z-40">
          <div className="px-5 h-14 flex items-center justify-between">
            <Link
              href="/"
              aria-label="AXIOM home"
              className="flex items-center gap-2.5 font-semibold tracking-tight"
            >
              <LogoMark className="h-[26px] w-[26px]" />
              <span>AXIOM</span>
              <span className="ml-2 text-xs font-mono text-[var(--text-muted)] font-normal">{t("workspaceLabel")}</span>
            </Link>
            <div className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
              <LanguageToggle />
              <HeaderToggle />
              <span className="hidden sm:inline">{t("trialBanner")}</span>
              <UserMenu variant="app" />
            </div>
          </div>
        </header>
        <div className="flex-1 grid grid-cols-[240px_1fr]">
          <Suspense fallback={<aside className="border-r border-[var(--border)] bg-[var(--surface)]" />}>
            <ProductSidebar />
          </Suspense>
          <main className="p-6 overflow-auto">{children}</main>
        </div>
      </div>
    </AppChrome>
  );
}
