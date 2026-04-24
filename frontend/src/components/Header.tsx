import Link from "next/link";
import Image from "next/image";
import { NAV_LINKS, SITE } from "@/lib/site";
import { ThemeToggle } from "./ThemeToggle";

export function Header({ current = "" }: { current?: string }) {
  return (
    <header className="sticky top-0 z-50 backdrop-blur bg-[var(--surface)]/80 border-b border-[var(--border)]">
      <div className="container-x flex items-center justify-between gap-6 py-3">
        <Link
          href="/"
          aria-label="AXIOM home"
          className="flex items-center gap-2.5 font-semibold text-base tracking-tight"
        >
          <Image
            src="/logo-mark.png"
            alt=""
            aria-hidden="true"
            width={28}
            height={28}
            priority
            className="h-7 w-7 object-contain"
          />
          <span>AXIOM</span>
        </Link>
        <nav aria-label="Primary" className="hidden md:flex gap-5 text-sm">
          {NAV_LINKS.map((l) => {
            const active = current === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`hover:text-[var(--accent)] ${active ? "text-[var(--accent)] font-medium" : "text-[var(--text-muted)]"}`}
              >
                {l.label}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link href="/login" className="btn btn-ghost hidden sm:inline-flex">Sign In</Link>
          <Link href="/signup" className="btn btn-primary">Launch App →</Link>
        </div>
      </div>
    </header>
  );
}
