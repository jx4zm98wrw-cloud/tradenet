/**
 * Typed content module for the marketing pricing page (`/pricing`).
 *
 * Source of truth: `design_handoff_tradenet_marketing/marketing/marketing.js`
 * (PRICES constant + `updatePrices`) and the `data-view="pricing"` section
 * of `design_handoff_tradenet_marketing/Tradenet - Marketing.html`. Copy is
 * verbatim — do not paraphrase without updating the prototype too.
 *
 * Per IMPLEMENTATION_PLAN.md Q1, marketing copy lives as typed in-repo
 * modules (MDX-in-repo + TS config) until a CMS proves necessary.
 */

export type Period = "annual" | "monthly";
export type Currency = "USD" | "VND";

/**
 * Canonical prices, lifted from `marketing.js` PRICES.
 *
 *   - USD values are raw numbers (formatted at render time with `$` prefix
 *     and `en-US` grouping).
 *   - VND values are pre-formatted strings with `.` thousands separators —
 *     that's the Vietnamese locale convention the prototype uses
 *     (`1.190.000` not `1,190,000`), so we preserve them as-is rather than
 *     re-deriving via `toLocaleString("vi-VN")`.
 *   - `soloYr` / `firmYr` are the yearly totals shown in the bill-note
 *     under each tier on annual; on monthly they're `null` and the page
 *     reconstructs a monthly billnote (`firm * 3 / mo · 3 seats min`).
 */
export const PRICES = {
  USD: {
    annual: { solo: 49, firm: 179, soloYr: 588, firmYr: 6444 },
    monthly: { solo: 59, firm: 219, soloYr: null, firmYr: null },
  },
  VND: {
    annual: { solo: "1.190.000", firm: "4.390.000", soloYr: "14.280.000", firmYr: "158.040.000" },
    monthly: { solo: "1.490.000", firm: "5.490.000", soloYr: null, firmYr: null },
  },
} as const;

export type PriceSet = {
  /** USD: number; VND: pre-grouped string. */
  solo: number | string;
  firm: number | string;
  soloYr: number | string | null;
  firmYr: number | string | null;
};

export type Bullet = { text: string; included: boolean };

export type Tier = {
  id: "solo" | "firm" | "enterprise";
  name: string;
  tagline: string;
  featured: boolean;
  badge?: string;
  /** When true, the price renders as the literal string "Custom" (no toggle effect). */
  customPrice?: boolean;
  /**
   * Per-seat marker shown after the price ("/ mo" vs "/ seat / mo"). Lifted
   * straight from the prototype HTML — the Firm tier uses per-seat pricing.
   */
  perPeriodLabel?: string;
  includesLabel: string;
  bullets: ReadonlyArray<Bullet>;
  cta: { label: string; href: string; variant: "primary" | "ghost" };
};

export const TIERS: ReadonlyArray<Tier> = [
  {
    id: "solo",
    name: "Solo",
    tagline: "Independent IP counsel, single-matter watching",
    featured: false,
    perPeriodLabel: "/ mo",
    includesLabel: "Includes",
    bullets: [
      { text: "<strong>5</strong> active watchlists", included: true },
      { text: "<strong>500</strong> searches / month", included: true },
      { text: "Phonetic + image search", included: true },
      { text: "Opposition calendar", included: true },
      { text: "Email digest, weekly", included: true },
      { text: "Madrid Protocol coverage", included: false },
      { text: "Side-by-side scorecard", included: false },
      { text: "Client-facing PDF reports", included: false },
    ],
    cta: { label: "Start free trial", href: "/login", variant: "ghost" },
  },
  {
    id: "firm",
    name: "Firm",
    tagline: "IP boutiques and in-house teams · 3–25 seats",
    featured: true,
    badge: "Most popular",
    perPeriodLabel: "/ seat / mo",
    includesLabel: "Everything in Solo, plus",
    bullets: [
      { text: "<strong>Unlimited</strong> watchlists &amp; searches", included: true },
      { text: "Side-by-side conflict scorecard", included: true },
      { text: "Madrid Protocol &amp; WIPO mirror", included: true },
      { text: "Per-matter weight tuning", included: true },
      { text: "Client-facing PDF reports", included: true },
      { text: "Slack &amp; Microsoft Teams alerts", included: true },
      { text: "Shared watchlists across firm", included: true },
      { text: "Calendar sync (Google, Outlook, ICS)", included: true },
    ],
    cta: { label: "Start free trial", href: "/login", variant: "primary" },
  },
  {
    id: "enterprise",
    name: "Enterprise",
    tagline: "Large firms, IP departments, alliances",
    featured: false,
    customPrice: true,
    includesLabel: "Everything in Firm, plus",
    bullets: [
      { text: "<strong>API access</strong> &amp; webhooks", included: true },
      { text: "SSO (SAML 2.0, OIDC)", included: true },
      { text: "Audit log + data residency in VN", included: true },
      { text: "99.9% uptime SLA", included: true },
      { text: "Dedicated onboarding &amp; training", included: true },
      { text: "Custom Vienna code training", included: true },
      { text: "White-label client reports", included: true },
      { text: "Priority support · 1-hr response", included: true },
    ],
    cta: { label: "Contact sales", href: "/login", variant: "ghost" },
  },
] as const;

export type ComparisonRow = {
  feature: string;
  solo: string;
  firm: string;
  enterprise: string;
};

export type ComparisonSection = {
  label: string;
  rows: ReadonlyArray<ComparisonRow>;
};

/**
 * Comparison rows mirror the `<table class="compare-table">` markup in the
 * prototype. Cell values are either plain text or one of the sentinel
 * strings "check" / "dash" — rendered as the ✓ / — glyphs from the
 * prototype CSS (`.check` / `.dash`).
 */
export const COMPARISON_SECTIONS: ReadonlyArray<ComparisonSection> = [
  {
    label: "Search",
    rows: [
      { feature: "Active watchlists", solo: "5", firm: "Unlimited", enterprise: "Unlimited" },
      { feature: "Searches per month", solo: "500", firm: "Unlimited", enterprise: "Unlimited" },
      { feature: "Phonetic / fuzzy search", solo: "check", firm: "check", enterprise: "check" },
      { feature: "Image-similarity search", solo: "check", firm: "check", enterprise: "check" },
      { feature: "Vienna code search", solo: "check", firm: "check", enterprise: "check" },
      { feature: "Side-by-side scorecard", solo: "dash", firm: "check", enterprise: "check" },
    ],
  },
  {
    label: "Coverage",
    rows: [
      { feature: "Vietnamese gazette (Vietnam IP)", solo: "check", firm: "check", enterprise: "check" },
      { feature: "Madrid Protocol marks", solo: "dash", firm: "check", enterprise: "check" },
      { feature: "WIPO Global Brand DB mirror", solo: "dash", firm: "check", enterprise: "check" },
      { feature: "Historical archive", solo: "2 years", firm: "10 years", enterprise: "Full" },
    ],
  },
  {
    label: "Workflow",
    rows: [
      { feature: "Opposition calendar", solo: "check", firm: "check", enterprise: "check" },
      { feature: "Email digest", solo: "Weekly", firm: "Daily + weekly", enterprise: "Configurable" },
      { feature: "Slack / Teams alerts", solo: "dash", firm: "check", enterprise: "check" },
      { feature: "Client-facing PDF reports", solo: "dash", firm: "check", enterprise: "check" },
      { feature: "White-label reports", solo: "dash", firm: "dash", enterprise: "check" },
    ],
  },
  {
    label: "Team & security",
    rows: [
      { feature: "Seats included", solo: "1", firm: "From 3", enterprise: "Unlimited" },
      { feature: "Shared watchlists", solo: "dash", firm: "check", enterprise: "check" },
      { feature: "SSO (SAML, OIDC)", solo: "dash", firm: "dash", enterprise: "check" },
      { feature: "Audit log", solo: "dash", firm: "dash", enterprise: "check" },
      { feature: "API access", solo: "dash", firm: "dash", enterprise: "check" },
      { feature: "Uptime SLA", solo: "dash", firm: "99.5%", enterprise: "99.9%" },
    ],
  },
  {
    label: "Support",
    rows: [
      { feature: "Onboarding", solo: "Self-serve", firm: "Live, 1 hour", enterprise: "Dedicated CSM" },
      { feature: "Support", solo: "Email", firm: "Email + chat", enterprise: "Priority · 1-hr" },
    ],
  },
];

export type FaqEntry = { q: string; a: string };

export const FAQ: ReadonlyArray<FaqEntry> = [
  {
    q: 'What does a "seat" mean on the Firm plan?',
    a: "One named user with their own login, watchlists, and saved searches. Watchlists can be shared across seats inside the same firm — assignment and ownership stay clear in the audit log.",
  },
  {
    q: "Do you cover Madrid Protocol designations?",
    a: "Yes, on Firm and Enterprise. We ingest WIPO's Romarin output and surface Vietnam designations the moment they hit the gazette — so a US or DE applicant's mark shows up alongside domestic filings.",
  },
  {
    q: "How quickly do new gazette issues appear?",
    a: "Vietnam IP publishes weekly issues T1–T4. We typically have a new issue OCR'd, deduplicated, and searchable within 4 hours of release. Watchlists re-run automatically once the issue lands.",
  },
  {
    q: "Can we file oppositions through Tradenet?",
    a: "Not directly — opposition filing happens through Vietnam IP or your IP agent. We export a pre-filled brief (mark, grounds, prior rights, evidence pack) that drops into your filing template. Direct e-filing is on the roadmap for late 2026.",
  },
  {
    q: "Is the data hosted in Vietnam?",
    a: "Enterprise customers get data residency in Vietnam (Viettel IDC, Hanoi). Solo and Firm are hosted in Singapore on AWS ap-southeast-1.",
  },
  {
    q: "What's your refund policy?",
    a: "14-day money-back guarantee on annual plans, no questions asked. Cancel monthly plans at any point with no cancellation fee.",
  },
  {
    q: "Do you offer discounts for solo practitioners or NGOs?",
    a: "Yes — 50% off Solo for early-career attorneys (first 3 years post-qualification) and 100% off for registered legal aid organisations. Email us with proof of status.",
  },
];

/** Currency-symbol prefix (`$` / `₫`). Mirrors `symbol()` in marketing.js. */
export function currencySymbol(c: Currency): string {
  return c === "USD" ? "$" : "₫";
}

/**
 * Format a price amount for display.
 *   - USD numbers go through `toLocaleString("en-US")`, matching the
 *     prototype's `fmtAmount` (49 stays "49"; 6444 becomes "6,444").
 *   - VND strings (already locale-formatted with `.` separators) pass
 *     through untouched.
 */
export function formatAmount(v: number | string): string {
  if (typeof v === "number") return v.toLocaleString("en-US");
  return v;
}

/**
 * The hero copy block — kept out of the JSX so the `(marketing)/_content/`
 * directory stays the single touch-point for translation / copy edits.
 */
export const pricingHero = {
  eyebrow: "Pricing",
  h1: "Priced for the work, not the dashboard.",
  sub: "Pick the plan that matches your matter volume. Upgrade or cancel any time. Annual saves you 17%.",
};

export const periodOptions = [
  { value: "annual" as const, label: "Annual · save 17%" },
  { value: "monthly" as const, label: "Monthly" },
];

export const currencyOptions = [
  { value: "USD" as const, label: "USD" },
  { value: "VND" as const, label: "VND" },
];

export const compareSection = {
  h2: "Compare in detail",
};

export const faqSection = {
  h2: "Questions, answered.",
  sub: {
    lead: "Anything else? ",
    talkToSales: "Talk to sales",
    middle: " or email ",
    email: "hello@tradenet.vn",
  },
};
