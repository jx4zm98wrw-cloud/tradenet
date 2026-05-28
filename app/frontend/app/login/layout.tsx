/**
 * Login route layout — minimal: just AuthProvider.
 *
 * Login is a public route (no `(app)` group) but it consumes the auth
 * context to call `login()` and detect already-logged-in users. The
 * root layout dropped AuthProvider when we split into (marketing) /
 * (app) Route Groups; login needs its own provider since neither
 * group's layout wraps this route.
 *
 * No TopNav / no MarketingNav — the login form is full-bleed by design.
 * The redesigned two-pane login (per the marketing handoff) lands in
 * PR 3 of the marketing site work; this layout file stays the same.
 */
import { AuthProvider } from "@/components/auth-context";

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
