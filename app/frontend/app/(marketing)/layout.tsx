/**
 * (marketing) route group layout — wraps every public marketing surface
 * (Landing today; Pricing / Coverage / Docs in later PRs).
 *
 * Deliberately does NOT include AuthProvider — these pages are public, so
 * paying the refresh-token round-trip on mount would be wasted work and
 * would gate the marketing site on the backend being reachable.
 *
 * The marketing chrome (MarketingNav + MarketingFooter) lives here and
 * applies to every (marketing)/ page. The login route lives outside this
 * group so it can render its own full-bleed two-pane layout (PR 3).
 *
 * `./marketing.css` carries the prototype's section/component styles
 * (`.hero`, `.section`, `.split`, `.cta-strip`, `.mk-nav`, `.mk-footer`,
 * etc.) — the design tokens themselves are already in `app/globals.css`.
 */
import "./marketing.css";
import { MarketingNav } from "@/components/marketing/MarketingNav";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <MarketingNav />
      <main>{children}</main>
      <MarketingFooter />
    </>
  );
}
