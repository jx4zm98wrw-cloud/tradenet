/**
 * Login route layout — AuthProvider + marketing chrome styles.
 *
 * `/login` is intentionally OUTSIDE both the `(marketing)` and `(app)`
 * Route Groups so it can render its own full-bleed two-pane layout
 * (no MarketingNav, no TopNav). But the form pane reuses several
 * marketing classes from the handoff:
 *
 *   .login / .login-left / .login-right / .login-form / .login-h1 /
 *   .login-stamp-mosaic / .login-quote / .login-trust / .sso-btn /
 *   .login-divider / .login-field / .login-back / .login-magic /
 *   .login-cta / .login-foot
 *
 * Plus a handful of generic helpers (`.btn` family, `.mk-brand-*`).
 *
 * Importing `../(marketing)/marketing.css` is the simplest path to get
 * those rules without duplicating them.  The unused .hero / .features /
 * .cta-strip rules add a few hundred bytes — negligible for a route that
 * lives behind the auth boundary.
 *
 * AuthProvider is required here because the root layout dropped it when
 * we split into Route Groups; `/login` calls `useAuth().login()` so it
 * needs its own provider.  The provider doesn't try to hit `/auth/me` on
 * mount when there's no token, so unauthenticated visits to `/login` are
 * free.
 */
import "../(marketing)/marketing.css";
import { AuthProvider } from "@/components/auth-context";

export default function LoginLayout({ children }: { children: React.ReactNode }) {
  return <AuthProvider>{children}</AuthProvider>;
}
