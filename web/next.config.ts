import type { NextConfig } from "next";

// The catalogue (SPEC-R2-CATALOGUE): the R2 bucket's public base URL, normalised once (no trailing slash) for the
// browser bundle. Its posters and videos are plain <img> and <video> elements pointing at that host: no next/image (so
// no optimisation or remotePatterns entry), and no Content-Security-Policy here that would need the host listed. A new
// policy must allow it in img-src, media-src and connect-src.
const CATALOGUE_URL = (process.env.NEXT_PUBLIC_CATALOGUE_URL || "").trim().replace(/\/+$/, "");
if (CATALOGUE_URL && !/^https?:\/\/[^/]+/.test(CATALOGUE_URL)) {
  throw new Error(`NEXT_PUBLIC_CATALOGUE_URL must be an http(s) base URL, got "${CATALOGUE_URL}"`);
}

const nextConfig: NextConfig = {
  // This folder is the workspace root (the repo above holds a Python project).
  turbopack: { root: __dirname },
  env: { NEXT_PUBLIC_CATALOGUE_URL: CATALOGUE_URL },
  // browsers ask for /favicon.ico on their own; the icon is app/icon.svg
  async rewrites() {
    return [{ source: "/favicon.ico", destination: "/icon.svg" }];
  },
};

export default nextConfig;
