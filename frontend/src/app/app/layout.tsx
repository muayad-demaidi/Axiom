import Link from "next/link";
import Image from "next/image";
import { Suspense } from "react";
import { ProductSidebar } from "@/components/product/ProductSidebar";
import { UserMenu } from "@/components/UserMenu";
import { AppChrome, HeaderToggle } from "@/components/product/AppChrome";

export const metadata = { title: "AXIOM — Workspace" };

export default function AppLayout({ children }: { children: React.ReactNode }) {
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
              <Image
                src="/logo-mark.png"
                alt=""
                aria-hidden="true"
                width={26}
                height={26}
                priority
                className="h-[26px] w-[26px] object-contain"
              />
              <span>AXIOM</span>
              <span className="ml-2 text-xs font-mono text-[var(--text-muted)] font-normal">Workspace</span>
            </Link>
            <div className="flex items-center gap-3 text-sm text-[var(--text-muted)]">
              <HeaderToggle />
              <span className="hidden sm:inline">60-day trial active</span>
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
