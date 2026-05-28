/**
 * (app) route group layout — wraps every authenticated in-product surface
 * (Today / Search / Detail / Compare / Watchlists / Admin / Gazettes /
 * Marks / Trademarks / Dev showcase).
 *
 * What lives here:
 *  - AuthProvider: bounces unauthenticated visits to /login. Pages outside
 *    this group (the marketing site, /login itself) don't pay this cost.
 *  - CmdKProvider: enables the ⌘-K command palette across all in-app
 *    surfaces. The palette is meaningless on marketing pages.
 *  - TopNav: the in-app navigation chrome (Today / Search / Watchlists /
 *    Gazettes tabs, search box, user menu). Marketing pages render the
 *    public MarketingNav instead.
 *  - TweaksPanel: dev-only design-token tweaker. Same scope rationale —
 *    only shown to authenticated app users.
 *
 * Route Groups (parens-named directories) don't affect URLs — `(app)/today`
 * still serves at `/today`. The grouping is purely for layout composition.
 */
import { TopNav } from "@/components/top-nav";
import { CmdKProvider } from "@/components/cmdk";
import { TweaksPanel } from "@/components/tweaks-panel";
import { AuthProvider } from "@/components/auth-context";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <CmdKProvider>
        <TopNav />
        <main>{children}</main>
        <TweaksPanel />
      </CmdKProvider>
    </AuthProvider>
  );
}
