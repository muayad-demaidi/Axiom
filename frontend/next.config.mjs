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
export default nextConfig;
