import Link from "next/link";
import Image from "next/image";
import { SITE } from "@/lib/site";

export function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="border-t border-[var(--border)] mt-20 bg-[var(--surface-alt)]">
      <div className="container-x grid gap-10 py-12 md:grid-cols-[2fr_1fr_1fr_1fr]">
        <div>
          <Link href="/" aria-label="AXIOM home" className="inline-flex items-center gap-3">
            <Image
              src="/logo-mark.png"
              alt=""
              aria-hidden="true"
              width={40}
              height={40}
              className="h-10 w-10 object-contain"
            />
            <span className="text-lg font-semibold tracking-tight">AXIOM</span>
          </Link>
          <p className="text-sm text-[var(--text-muted)] mt-3 max-w-[320px]">
            An intelligent data analytics platform that turns raw datasets into clear, actionable
            insights — in seconds, no code required.
          </p>
        </div>
        <FooterCol title="Product" links={[
          { href: "/features", label: "Features" },
          { href: "/pricing", label: "Pricing & Plans" },
          { href: SITE.appUrl, label: "Launch App" },
          { href: SITE.appUrl, label: "60-Day Free Trial" },
        ]} />
        <FooterCol title="Learn" links={[
          { href: "/glossary", label: "Glossary" },
          { href: "/guides", label: "Guides" },
          { href: "/compare", label: "Compare" },
          { href: "/about", label: "About" },
        ]} />
        <FooterCol title="Support" links={[
          { href: "/contact", label: "Contact" },
          { href: `mailto:${SITE.supportEmail}`, label: "Email Support" },
          { href: "/sitemap.xml", label: "Sitemap" },
          { href: "/robots.txt", label: "Robots" },
        ]} />
      </div>
      <div className="container-x flex items-center justify-between py-5 text-xs font-mono text-[var(--text-muted)] border-t border-[var(--border)]">
        <span>© {year} {SITE.name}. All rights reserved.</span>
        <span><span className="text-[var(--accent)]">●</span> All systems operational</span>
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
