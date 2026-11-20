import type { NextConfig } from "next";

// NEXT_PUBLIC_STATIC_DEMO=1 builds the read-only static demo for GitHub Pages.
const staticDemo = process.env.NEXT_PUBLIC_STATIC_DEMO === "1";

const nextConfig: NextConfig = {
  ...(staticDemo
    ? { output: "export", distDir: ".next-static", basePath: process.env.NEXT_PUBLIC_BASE_PATH ?? "", trailingSlash: true, images: { unoptimized: true } }
    : { cacheComponents: true, partialPrefetching: true }),
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
