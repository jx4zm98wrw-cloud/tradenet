"use client";

/**
 * SSO button stub — visual fidelity to the handoff, but the click handler
 * just toasts a "coming soon" message.
 *
 * Per `design_handoff_tradenet_marketing/IMPLEMENTATION_PLAN.md` open-question 2:
 *
 *   > SSO buttons in PR 3 ship as visual stubs … until the auth provider
 *   > is chosen (Auth0 / WorkOS / Clerk / custom). Magic-link form falls
 *   > back to a "please use password" hint until backend is wired.
 *
 * We use `alert()` here on purpose (not a toast library) — it's exactly
 * what the prototype HTML does, it requires no dep, and it makes "this
 * is intentionally non-functional" obvious to anyone clicking. When the
 * auth provider lands, this component swaps to a real OAuth redirect
 * without touching any caller.
 *
 * Client component because of the click handler; renders an icon + label
 * + "SSO" hint on the right (in monospace), matching `.sso-btn` styles
 * in `marketing.css`.
 */
import * as React from "react";

type SsoButtonProps = {
  provider: "google" | "microsoft";
  label: string;
};

export function SsoButton({ provider, label }: SsoButtonProps) {
  return (
    <button
      type="button"
      className="sso-btn"
      onClick={() => {
        alert("SSO coming soon — please use email + password below.");
      }}
    >
      <SsoIcon provider={provider} />
      {label}
      <span className="sso-hint">SSO</span>
    </button>
  );
}

/**
 * Provider-specific inline SVG — colors match the brand marks from the
 * handoff so the buttons are visually identifiable without needing image
 * assets in /public.
 *
 * Google: 4-color "G" lifted from the prototype HTML (a simplified
 *   approximation of Google's actual logo — sufficient for a marketing
 *   surface; the real OAuth flow will hand off to Google's own page).
 * Microsoft: the 4-quadrant Windows tile (FluentDesign palette).
 */
function SsoIcon({ provider }: { provider: "google" | "microsoft" }) {
  if (provider === "google") {
    return (
      <svg className="sso-icon" viewBox="0 0 24 24" aria-hidden="true">
        <path
          fill="#4285F4"
          d="M22.5 12.27c0-.79-.07-1.54-.2-2.27H12v4.51h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.32z"
        />
        <path
          fill="#34A853"
          d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
        />
        <path
          fill="#FBBC05"
          d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"
        />
        <path
          fill="#EA4335"
          d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
        />
      </svg>
    );
  }
  // microsoft
  return (
    <svg className="sso-icon" viewBox="0 0 24 24" aria-hidden="true">
      <rect width="10" height="10" x="1" y="1" fill="#F25022" />
      <rect width="10" height="10" x="13" y="1" fill="#7FBA00" />
      <rect width="10" height="10" x="1" y="13" fill="#00A4EF" />
      <rect width="10" height="10" x="13" y="13" fill="#FFB900" />
    </svg>
  );
}
