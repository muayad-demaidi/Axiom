import Link from "next/link";
import Image from "next/image";
import { ProductSidebar } from "@/components/product/ProductSidebar";

export const metadata = { title: "AXIOM — Workspace" };

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
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
            <span className="hidden sm:inline">60-day trial active</span>
            <Link href="/" className="btn btn-ghost text-xs">Marketing site</Link>
          </div>
        </div>
      </header>
      <div className="flex-1 grid grid-cols-[240px_1fr]">
        <ProductSidebar />
        <main className="p-6 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
