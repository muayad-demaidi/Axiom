export const SITE = {
  name: "AXIOM",
  tagline: "AI-powered data analysis, no code required",
  description:
    "AXIOM turns raw CSVs and Excel files into clean, analyzed, AI-explained insights in seconds. Auto cleaning, statistics, ML, predictions, and a built-in chat assistant.",
  url: process.env.NEXT_PUBLIC_SITE_URL || "https://AXIOM.app",
  appUrl: process.env.NEXT_PUBLIC_APP_URL || "/app",
  supportEmail: "muayad.demaidi.work@gmail.com",
  organization: {
    name: "AXIOM",
    legalName: "AXIOM",
    foundingDate: "2026-01-01",
    sameAs: [] as string[],
  },
  socialImage: "/og-default.png",
  twitter: "@AXIOM",
  defaultUpdated: "2026-04-01",
};

export const NAV_LINKS = [
  { href: "/features", label: "Features" },
  { href: "/pricing", label: "Pricing" },
  { href: "/glossary", label: "Glossary" },
  { href: "/guides", label: "Guides" },
  { href: "/compare", label: "Compare" },
  { href: "/about", label: "About" },
];

export function organizationJsonLd() {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: SITE.organization.name,
    legalName: SITE.organization.legalName,
    url: SITE.url,
    logo: SITE.url + "/logo.png",
    foundingDate: SITE.organization.foundingDate,
    email: SITE.supportEmail,
    sameAs: SITE.organization.sameAs,
  };
}
