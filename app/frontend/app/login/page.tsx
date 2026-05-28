"use client";

/**
 * Login page — two-pane redesign per the marketing handoff (PR 3).
 *
 * Left pane (`<aside class="login-left">`): paper-tinted brand panel with
 * the Tradenet wordmark, a 3×3 specimen mosaic wall, and a customer
 * pull-quote.  Hidden under 900px wide.
 *
 * Right pane (`<div class="login-right">`): the form itself —
 *   "Welcome back." h1
 *   → Two stubbed SSO buttons (alert "coming soon")
 *   → OR divider
 *   → Email + Password fields wired into the existing AuthProvider
 *   → Trial CTA at the bottom (links to nothing yet)
 *   → Trust strip (SOC 2 / GDPR / VN Data Residency)
 *
 * Architecture notes:
 *   - The functional auth path is unchanged from the simple form we used
 *     to render: `useAuth().login(email, password)` POSTs to
 *     `/api/v1/auth/login`, stores the JWT in the cookie store, and
 *     resolves with the user object. SSO + magic-link are visual stubs
 *     per IMPLEMENTATION_PLAN.md open-question 2 (defer until auth
 *     provider is chosen).
 *   - The `?next=…` redirect behavior is preserved verbatim from the
 *     pre-redesign page: after login (or if already authed) we
 *     `router.replace(sp.get("next") ?? "/today")`. The "/today" fallback
 *     bounces authed users to the in-app home, not the public marketing
 *     landing at `/`.
 *   - The `useEffect` redirect (instead of a render-time `router.replace`)
 *     is the fix from PR #45 — calling router methods during render
 *     trips React 19's "Cannot update a component while rendering a
 *     different component" error.
 *   - Wrapped in `<Suspense>` because `useSearchParams()` suspends on
 *     SSR.  The fallback is `null` (a blank pane) because the form
 *     itself paints in the next frame.
 */
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/auth-context";
import { LoginDivider } from "@/components/marketing/LoginDivider";
import { LoginField } from "@/components/marketing/LoginField";
import { LoginQuote } from "@/components/marketing/LoginQuote";
import { SpecimenMosaicWall } from "@/components/marketing/SpecimenMosaicWall";
import { SsoButton } from "@/components/marketing/SsoButton";
import {
  loginHero,
  loginQuote,
  loginTrust,
  ssoButtons,
} from "./_content/login";

export default function LoginPageShell() {
  // Wrap the real page in Suspense because useSearchParams suspends.
  return (
    <Suspense fallback={null}>
      <LoginPage />
    </Suspense>
  );
}

function LoginPage() {
  const router = useRouter();
  const sp = useSearchParams();
  const { login, user } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // If we're already authenticated (e.g., came via /login while logged in),
  // skip the form and bounce to the requested destination. Done in an effect
  // because router.replace() is a setState — calling it during render
  // triggers React 19's "Cannot update a component while rendering a
  // different component" error. The effect runs after commit, which is
  // when navigation is safe.
  useEffect(() => {
    if (user) {
      // `/` is the public marketing landing post-PR 1 (Route Group split).
      // Authed users with no `?next=` should land on the in-app home, not
      // bounce back to the marketing page.
      const next = sp.get("next") ?? "/today";
      router.replace(next);
    }
  }, [user, sp, router]);

  // Hide the form during the redirect frame to avoid flashing it.
  if (user) {
    return null;
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      // Same fallback as the already-authed redirect above: /today is the
      // in-app home; marketing's / would dump the user back onto the public
      // landing they just signed in from.
      const next = sp.get("next") ?? "/today";
      router.replace(next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      {/* Left brand pane — hidden under 900px via CSS */}
      <aside className="login-left">
        <div className="login-left-bg" aria-hidden="true" />
        <div className="login-left-content">
          <Link href="/" className="login-brand mk-brand">
            <BrandMark />
            <span className="mk-brand-name">
              Tradenet<span className="mk-brand-tld">.vn</span>
            </span>
          </Link>
          <SpecimenMosaicWall />
        </div>
        <LoginQuote text={loginQuote.text} attribution={loginQuote.attribution} />
      </aside>

      {/* Right form pane */}
      <div className="login-right">
        <Link href="/" className="login-back">
          <svg
            width="12"
            height="12"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            aria-hidden="true"
          >
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
          Back
        </Link>

        <div className="login-form">
          {/* Mobile-only brand — shown when left pane is hidden */}
          <Link href="/" className="login-mobile-brand mk-brand">
            <BrandMark />
            <span className="mk-brand-name">
              Tradenet<span className="mk-brand-tld">.vn</span>
            </span>
          </Link>

          <h1 className="login-h1">{loginHero.h1}</h1>
          <p className="login-sub">{loginHero.sub}</p>

          {ssoButtons.map((sso) => (
            <SsoButton key={sso.provider} provider={sso.provider} label={sso.label} />
          ))}

          <LoginDivider />

          <form onSubmit={onSubmit} noValidate>
            <LoginField
              id="login-email"
              name="email"
              label="Work email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@firm.vn"
              autoComplete="email"
              required
              autoFocus
            />
            <LoginField
              id="login-password"
              name="password"
              label="Password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
              minLength={8}
            />

            {error && (
              <div
                className="text-[12.5px] text-rose-600 bg-rose-50 border border-rose-200 rounded px-3 py-2"
                style={{ marginBottom: 12 }}
                role="alert"
              >
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={busy}
              className="btn btn-primary btn-lg login-cta"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          <p className="login-foot">
            No self-registration — accounts are created by an admin via the{" "}
            <code style={{ fontFamily: "var(--font-mono), monospace" }}>create_user</code> CLI.
          </p>

          <div className="login-trust" aria-label="Compliance and security">
            {loginTrust.map((label) => (
              <span key={label} className="login-trust-item">
                {label === "SOC 2 Type II" && <ShieldLockIcon />}
                {label === "GDPR" && <ShieldIcon />}
                {label}
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * The tiny inline brand mark used in the prototype HTML. Repeated in both
 * the left pane and the mobile-only brand at the top of the form, so it's
 * factored to a single component.
 */
function BrandMark() {
  return (
    <span className="mk-brand-mark">
      <svg width={18} height={18} viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M5 4 H19 V8 L12 9.5 L5 8 Z" fill="white" opacity={0.95} />
        <path d="M11 9 H13 V20 H11 Z" fill="white" opacity={0.95} />
      </svg>
    </span>
  );
}

function ShieldLockIcon() {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      aria-hidden="true"
    >
      <rect x={3} y={11} width={18} height={11} rx={2} />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg
      width={12}
      height={12}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2.5}
      aria-hidden="true"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}
