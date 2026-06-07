import "../globals.css";
import type { Metadata, Viewport } from "next";
import { notFound } from "next/navigation";
import { Inter, JetBrains_Mono, Noto_Sans_Arabic } from "next/font/google";
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

// Arabic-optimised typeface. Inter has no Arabic glyphs, so without
// this the RTL UI falls back to inconsistent system fonts. Exposed as
// a CSS variable and chained after Inter in the body stack so Latin
// glyphs stay on Inter and Arabic glyphs render with Noto Sans Arabic.
const notoArabic = Noto_Sans_Arabic({
  subsets: ["arabic"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-arabic",
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
  manifest: "/manifest.webmanifest",
};

// Mobile + PWA basics surfaced as part of the world-class audit
// (Task #270). `width=device-width, initial-scale=1` is required for
// any responsive layout to render correctly on phones; `themeColor`
// matches the dark chrome the app actually paints so the address bar
// (mobile Safari, Android Chrome) blends in instead of flashing white.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0b1220" },
  ],
};

export function generateStaticParams() {
  return LOCALES.map((locale) => ({ locale }));
}

const themeBootScript = `(function(){try{var q=location.search.indexOf('theme=dark')>=0;var s=localStorage.getItem('axiom-theme');var m=window.matchMedia&&window.matchMedia('(prefers-color-scheme: dark)').matches;var d=q||s==='dark'||(!s&&m);if(d)document.documentElement.classList.add('dark');}catch(e){}})();`;

// Global ChunkLoadError recovery: when a redeploy invalidates the
// hashed JS chunks referenced by an already-open tab, dynamic imports
// (Charts.tsx, PredictionCard.tsx, etc.) start throwing
// ChunkLoadError. We do a one-time silent reload per session so users
// auto-pick up the new bundle instead of seeing the Next.js red
// runtime overlay. The sessionStorage flag prevents reload loops if
// the chunk is genuinely broken.
const chunkReloadScript = `(function(){try{var FLAG='axiom-chunk-reloaded';function isChunkErr(err){if(!err)return false;var n=String(err.name||'');var m=String(err.message||'');return n==='ChunkLoadError'||/ChunkLoadError/i.test(m)||/Loading chunk [^ ]+ failed/i.test(m)||/Loading CSS chunk/i.test(m);}function maybeReload(err){if(!isChunkErr(err))return;try{if(sessionStorage.getItem(FLAG))return;sessionStorage.setItem(FLAG,'1');}catch(_e){}window.location.reload();}window.addEventListener('error',function(e){maybeReload(e&&e.error);});window.addEventListener('unhandledrejection',function(e){maybeReload(e&&e.reason);});}catch(_e){}})();`;

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
      className={`${inter.variable} ${jetbrains.variable} ${notoArabic.variable}`}
    >
      <body suppressHydrationWarning>
        <script
          dangerouslySetInnerHTML={{ __html: themeBootScript }}
        />
        <script
          dangerouslySetInnerHTML={{ __html: chunkReloadScript }}
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
