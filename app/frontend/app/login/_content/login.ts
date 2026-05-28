/**
 * Typed copy module for `/login`.
 *
 * Centralizes every user-visible string the login page renders, so the
 * page component stays focused on layout + state. Mirrors the pattern
 * we used for `/_content/landing.ts` and `/_content/pricing.ts`.
 *
 * If marketing wants to A/B-test the headline or swap the testimonial,
 * they edit this file and nothing else.
 *
 * The testimonial is the exact quote from the prototype HTML — keep
 * pending real customer testimonials.
 */

export const loginHero = {
  h1: "Welcome back.",
  sub: "Sign in to your firm's Tradenet workspace.",
} as const;

export const loginQuote = {
  text:
    "We used to read the gazette PDF cover to cover every Friday. Tradenet caught a NEUROFAX filing we would have missed entirely — we filed opposition with eleven days to spare.",
  attribution: {
    name: "Nguyễn Thị Lan",
    role: "Senior Associate, Trần & Partners IP",
  },
} as const;

export const ssoButtons = [
  { provider: "google" as const, label: "Continue with Google Workspace" },
  { provider: "microsoft" as const, label: "Continue with Microsoft 365" },
] as const;

export const loginTrust = ["SOC 2 Type II", "GDPR", "VN Data Residency"] as const;
