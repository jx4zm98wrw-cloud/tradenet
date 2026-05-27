import "./globals.css";
import { Be_Vietnam_Pro, JetBrains_Mono, Source_Serif_4 } from "next/font/google";
import type { Metadata } from "next";
import { TopNav } from "@/components/top-nav";
import { CmdKProvider } from "@/components/cmdk";
import { TweaksPanel } from "@/components/tweaks-panel";
import { AuthProvider } from "@/components/auth-context";

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
  title: "Tradenet — Trademark Gazette",
  description: "Vietnam NOIP trademark gazette workbench",
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
        <AuthProvider>
          <CmdKProvider>
            <TopNav />
            <main>{children}</main>
            <TweaksPanel />
          </CmdKProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
