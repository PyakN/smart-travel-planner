import type { NextConfig } from "next";

// The browser calls /api/* on the same origin and Next.js proxies it to FastAPI,
// so the backend needs no CORS setup.
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The end-to-end tests build into a directory of their own (playwright.config.ts).
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // A self-contained server (server.js with only the modules it needs) for the Docker image.
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // POST /plan may run up to the backend's 90 s limit; the default proxy timeout is 30 s.
    proxyTimeout: 120_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
