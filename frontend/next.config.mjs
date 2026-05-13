import createNextIntlPlugin from "next-intl/plugin";

// Wire the request-config file so next-intl can hand it to the React
// tree on every render. Path is relative to the project root.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  // Allow Next/Image to run its optimizer on locally hosted assets
  // (logo, OG images, marketing thumbnails). The frontend runs behind
  // the same Next server on :5000 in dev and via `next start` in
  // production, so we don't need any remotePatterns yet.
  images: {
    formats: ["image/avif", "image/webp"],
  },
  // Baseline security headers — applied to every response. Picked to
  // satisfy Lighthouse "Best Practices" without breaking the existing
  // app (no CSP yet because the dev experience would need nonces for
  // the boot scripts; tracked as a recommendation in the v2 audit).
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), interest-cohort=()" },
          { key: "X-DNS-Prefetch-Control", value: "on" },
          { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: (process.env.BACKEND_URL || "http://localhost:8000") + "/api/:path*",
      },
    ];
  },
};

export default withNextIntl(nextConfig);
