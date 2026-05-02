import Link from "next/link";
import { MarketingShell } from "@/components/MarketingShell";
import { SITE } from "@/lib/site";

export const metadata = { title: "Page not found" };

export default function NotFound() {
  return (
    <MarketingShell>
      <section className="container-x py-24 text-center">
        <span className="eyebrow">404</span>
        <h1 className="text-3xl md:text-5xl font-bold mt-3">We can&rsquo;t find that page.</h1>
        <p className="mt-4 text-[var(--text-muted)] max-w-xl mx-auto">
          The link may be outdated. Try the homepage, the glossary, or launch the app.
        </p>
        <div className="mt-8 flex justify-center gap-3">
          <Link className="btn btn-primary" href="/">Go home</Link>
          <Link className="btn btn-ghost" href={SITE.appUrl}>Launch the app</Link>
        </div>
      </section>
    </MarketingShell>
  );
}
