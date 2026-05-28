/**
 * Root layout — slim shell only.
 *
 * Carries the things every URL needs (html / body / font CSS variables /
 * global styles) and nothing else. Per-section chrome lives in the route
 * group layouts:
 *
 *   app/(marketing)/layout.tsx   → MarketingNav + MarketingFooter (public)
 *   app/(app)/layout.tsx         → AuthProvider + CmdKProvider + TopNav
 *                                  + TweaksPanel (authenticated)
 *   app/login/page.tsx           → no group; uses its own minimal shell
 *
 * This split lets the marketing pages render without paying the
 * AuthProvider boot cost (refresh-token round-trip on mount) and
 * without rendering the in-app TopNav.
 */
import "./globals.css";
import { Be_Vietnam_Pro, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import type { Metadata } from "next";

const sans = Be_Vietnam_Pro({
  subsets: ["latin", "vietnamese"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-sans",
  display: "swap",
});
const mono = JetBrains_Mono({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-mono",
  display: "swap",
});
const serif = Source_Serif_4({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
  variable: "--font-serif",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Tradenet — Vietnam Trademark Intelligence",
  description:
    "Catch every conflict in the Vietnamese gazette before the opposition window closes.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${sans.variable} ${mono.variable} ${serif.variable}`}
    >
      <body
        data-theme="oxblood"
        data-density="cozy"
        data-serifheads="1"
        className="min-h-screen font-sans"
      >
        {children}
      </body>
    </html>
  );
}
