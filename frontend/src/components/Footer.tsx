"use client";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { LogoMark } from "./LogoMark";
import { SITE } from "@/lib/site";

export function Footer() {
  const tNav = useTranslations("nav");
  const tF = useTranslations("footer");
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-[var(--border)] mt-20 bg-[var(--surface-alt)]">
      <div className="container-x grid gap-10 py-12 md:grid-cols-[2fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" aria-label="AXIOM home" className="inline-flex items-center gap-3">
            <LogoMark className="h-10 w-10" />
            <span className="text-lg font-semibold tracking-tight">AXIOM</span>
          </Link>
          <p className="text-sm text-[var(--text-muted)] mt-3 max-w-[320px]">
            {tF("tagline")}
          </p>
        </div>
        <FooterCol title={tF("productTitle")} links={[
          { href: "/features", label: tNav("features") },
          { href: "/pricing", label: tF("pricingPlans") },
          { href: SITE.appUrl, label: tF("launchApp") },
          { href: SITE.appUrl, label: tF("freeTrial") },
        ]} />
        <FooterCol title={tF("learnTitle")} links={[
          { href: "/glossary", label: tNav("glossary") },
          { href: "/guides", label: tNav("guides") },
          { href: "/compare", label: tNav("compare") },
          { href: "/about", label: tNav("about") },
        ]} />
        <FooterCol title={tF("supportTitle")} links={[
          { href: "/contact", label: tNav("contact") },
          { href: `mailto:${SITE.supportEmail}`, label: tF("emailSupport") },
          { href: "/sitemap.xml", label: tF("sitemap") },
          { href: "/robots.txt", label: tF("robots") },
        ]} />
      </div>
      <div className="container-x flex items-center justify-between py-5 text-xs font-mono text-[var(--text-muted)] border-t border-[var(--border)]">
        <span>© {year} {SITE.name}. {tF("rights")}</span>
        <span><span className="text-[var(--accent)]">●</span> {tF("systemsOperational")}</span>
      </div>
    </footer>
  );
}

function FooterCol({ title, links }: { title: string; links: { href: string; label: string }[] }) {
  return (
    <div>
      <div className="font-mono text-xs uppercase tracking-wider text-[var(--text-muted)] mb-3">{title}</div>
      <ul className="space-y-2 text-sm">
        {links.map((l) => (
          <li key={l.href + l.label}>
            <Link href={l.href} className="text-[var(--text-muted)] hover:text-[var(--accent)]">{l.label}</Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
