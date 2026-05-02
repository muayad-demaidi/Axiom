import "../globals.css";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Inter, JetBrains_Mono } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getMessages, setRequestLocale } from "next-intl/server";
import { SITE, organizationJsonLd } from "@/lib/site";
import { LOCALES, asLocale, localeDir } from "@/i18n/config";

const inter = Inter({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  display: "swap",
  variable: "--font-inter",
});

const jetbrains = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-jetbrains",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: `${SITE.name} — ${SITE.tagline}`, template: `%s | ${SITE.name}` },
  description: SITE.description,
  openGraph: {
    title: SITE.name,
    description: SITE.description,
    url: SITE.url,
    siteName: SITE.name,
    images: [SITE.socialImage],
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: SITE.name,
    description: SITE.description,
    images: [SITE.socialImage],
  },
  icons: { icon: "/logo-mark.png" },
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

const themeBootScript = `(function(){try{var q=location.search.indexOf('theme=dark')>=0;var s=localStorage.getItem('axiom-theme');var m=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;var d=q||s==='dark'||(!s&&m);if(d)document.documentElement.classList.add('dark');}catch(e){}})();`;

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale: rawLocale } = await params;
  if (!(LOCALES as readonly string[]).includes(rawLocale)) {
    notFound();
  }
  const locale = asLocale(rawLocale);
  // Tell next-intl which locale this render is for so server-side
  // calls to `getTranslations()` resolve to the right catalogue.
  setRequestLocale(locale);
  const messages = await getMessages();
  const dir = localeDir(locale);

  return (
    <html
      lang={locale}
      dir={dir}
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrains.variable}`}
    >
      <body suppressHydrationWarning>
        <script
          dangerouslySetInnerHTML={{ __html: themeBootScript }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationJsonLd()) }}
        />
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
