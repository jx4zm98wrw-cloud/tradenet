/** @type {import('next').NextConfig} */
module.exports = {
  reactStrictMode: true,
  async rewrites() {
    // Proxy /api/* to the FastAPI backend during local dev.
    return [
      {
        source: "/api/:path*",
        destination: (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/api/:path*",
      },
    ];
  },
};
