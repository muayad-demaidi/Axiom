"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { ThemeToggle } from "./ThemeToggle";
import { LanguageToggle } from "./LanguageToggle";
import { LogoMark } from "./LogoMark";
import { UserMenu } from "./UserMenu";

const LINKS: { href: string; key: "features" | "pricing" | "glossary" | "guides" | "compare" | "about" }[] = [
  { href: "/features", key: "features" },
  { href: "/pricing", key: "pricing" },
  { href: "/glossary", key: "glossary" },
  { href: "/guides", key: "guides" },
  { href: "/compare", key: "compare" },
  { href: "/about", key: "about" },
];

export function Header({ current = "" }: { current?: string }) {
  const t = useTranslations("nav");
  return (
    <header className="sticky top-0 z-50 backdrop-blur bg-[var(--surface)]/80 border-b border-[var(--border)]">
      <div className="container-x flex items-center justify-between gap-6 py-3">
        <Link
          href="/"
          aria-label="AXIOM home"
          className="flex items-center gap-2.5 font-semibold text-base tracking-tight"
        >
          <LogoMark className="h-7 w-7" />
          <span>AXIOM</span>
        </Link>
        <nav aria-label="Primary" className="hidden md:flex gap-5 text-sm">
          {LINKS.map((l) => {
            const active = current === l.href;
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`hover:text-[var(--accent)] ${active ? "text-[var(--accent)] font-medium" : "text-[var(--text-muted)]"}`}
              >
                {t(l.key)}
              </Link>
            );
          })}
        </nav>
        <div className="flex items-center gap-2">
          <LanguageToggle />
          <ThemeToggle />
          <UserMenu variant="marketing" />
        </div>
      </div>
    </header>
  );
}
