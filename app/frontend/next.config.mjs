// ESM Next config — switched from `.js` (CommonJS) in PR 5 so we can
// `import` `remark-gfm`, which is ESM-only and breaks `require()`.
// All previous behavior (CSP, headers, /api + /static rewrites) is
// preserved verbatim; the only new wiring is `withMDX`.

import createMDX from "@next/mdx";
import remarkGfm from "remark-gfm";

const withMDX = createMDX({
  extension: /\.mdx?$/,
  options: {
    remarkPlugins: [remarkGfm],
    rehypePlugins: [],
  },
});

// Content Security Policy — only the API origin + Google Fonts allowed.
// The `'unsafe-inline'` on style-src is required for Next's Tailwind injection.
// Tighten further once we move to CSS-modules-only / nonce-based inline styles.
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline' 'unsafe-eval'", // Next.js needs unsafe-eval in dev; tighten with nonces in prod build
  "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
  // Same-origin images only (`/static/image/...` from the backend mount),
  // plus `data:` (inline SVGs / canvas exports) and `blob:` (file uploads).
  // No external image hosts are referenced today; if that changes, list
  // them explicitly rather than re-opening `https:`.
  "img-src 'self' data: blob:",
  "font-src 'self' https://fonts.gstatic.com",
  "connect-src 'self' " + (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"),
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const SECURITY_HEADERS = [
  { key: "Content-Security-Policy", value: CSP },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  // Only enable HSTS in prod — it's irreversible-ish for the browser.
  ...(process.env.NODE_ENV === "production"
    ? [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains; preload" }]
    : []),
];

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  pageExtensions: ["ts", "tsx", "mdx"],
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/api/:path*",
      },
      {
        // Trademark logo PNGs served by the backend's StaticFiles mount.
        source: "/static/:path*",
        destination: (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/static/:path*",
      },
    ];
  },
};

export default withMDX(nextConfig);
