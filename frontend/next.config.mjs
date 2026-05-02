import createNextIntlPlugin from "next-intl/plugin";

// Wire the request-config file so next-intl can hand it to the React
// tree on every render. Path is relative to the project root.
const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Allow Next/Image to run its optimizer on locally hosted assets
  // (logo, OG images, marketing thumbnails). The frontend runs behind
  // the same Next server on :5000 in dev and via `next start` in
  // production, so we don't need any remotePatterns yet.
  images: {
    formats: ["image/avif", "image/webp"],
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
