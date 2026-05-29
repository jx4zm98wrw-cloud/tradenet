/**
 * Typed content module for the marketing coverage page (`/coverage`).
 *
 * Source of truth: `data-view="coverage"` section of
 * `design_handoff_tradenet_marketing/Tradenet - Marketing.html`
 * (~lines 676-881) and the timeline rendering logic in
 * `design_handoff_tradenet_marketing/marketing/marketing.js`
 * (~lines 137-193). Copy is verbatim — do not paraphrase without updating
 * the prototype too.
 *
 * Per IMPLEMENTATION_PLAN.md Q1, marketing copy lives as typed in-repo
 * modules (MDX-in-repo + TS config) until a CMS proves necessary.
 */

/** Hero block at the top of the page. */
export const coverageHero = {
  eyebrow: "Data Coverage",
  h1: "Every Vietnam IP issue, every Madrid designation, every week.",
  sub:
    "We ingest the Vietnamese trademark gazette directly from Vietnam IP — the agency formerly known as NOIP, officially Cục Sở hữu trí tuệ — the day each issue publishes — plus Madrid Protocol designations from WIPO. Here's exactly what's in the corpus, how fresh it is, and how we measure quality.",
};

export type CoverageStat = {
  label: string;
  /** The big serif numeral / phrase. */
  value: string;
  /** Optional muted suffix rendered inside the value at 0.5em. */
  valueSuffix?: string;
  meta: string;
};

/** Four-up stats row directly below the hero copy. */
export const coverageStats: ReadonlyArray<CoverageStat> = [
  {
    label: "Marks indexed",
    value: "46,758",
    meta: "Vietnam · all classes · 2018→",
  },
  {
    label: "Issues this year",
    value: "20",
    valueSuffix: " / 52",
    meta: "8 sections A · 12 sections B",
  },
  {
    label: "Ingest lag · median",
    value: "3.8",
    valueSuffix: "h",
    meta: "From Vietnam IP publication to searchable",
  },
  {
    label: "OCR confidence · avg",
    value: "99.4",
    valueSuffix: "%",
    meta: "Rows below 0.85 flagged for review",
  },
];

export type SourceCardKv = { dt: string; dd: string };

export type SourceCard = {
  name: string;
  sub: string;
  primary: boolean;
  pillLabel: string;
  body: string;
  /** Exactly 4 dt/dd pairs per the prototype. */
  kvs: ReadonlyArray<SourceCardKv>;
};

/** Four source cards (2 primary + 2 non-primary) in a 2-col grid. */
export const sourceCards: ReadonlyArray<SourceCard> = [
  {
    name: "Vietnam IP · Section A — Applications published",
    sub: "Cục Sở hữu trí tuệ · A_T*_YYYY.pdf",
    primary: true,
    pillLabel: "Primary source",
    body:
      "Every application that passes formal examination and gets published to open its opposition window. T1–T4 weekly issues, ~3,000–8,000 marks per issue, including all 45 Nice classes and Vietnam-designated Madrid filings.",
    kvs: [
      { dt: "Frequency", dd: "Weekly · T1, T2, T3, T4" },
      { dt: "Lag", dd: "2–6 hours from PDF release" },
      { dt: "Fields", dd: "26 WIPO INID codes" },
      { dt: "Available on", dd: "All plans" },
    ],
  },
  {
    name: "Vietnam IP · Section B — Registered marks",
    sub: "Cục Sở hữu trí tuệ · B_T*_YYYY.pdf",
    primary: true,
    pillLabel: "Primary source",
    body:
      "Granted registrations, post-opposition. Includes certificate number, 10-year term, renewals, and partial cancellations. The authoritative record of who owns what mark, in what class, in Vietnam.",
    kvs: [
      { dt: "Frequency", dd: "Weekly · T1, T2, T3, T4" },
      { dt: "Lag", dd: "2–6 hours from PDF release" },
      { dt: "Renewals", dd: "Tracked automatically" },
      { dt: "Available on", dd: "All plans" },
    ],
  },
  {
    name: "Madrid Protocol designations",
    sub: "WIPO ROMARIN · daily delta feed",
    primary: false,
    pillLabel: "Firm + Enterprise",
    body:
      "International Registrations designating Vietnam — straight from WIPO before they appear in the local gazette. Catches conflicts 4–12 weeks earlier than waiting for Vietnam IP publication.",
    kvs: [
      { dt: "Frequency", dd: "Daily delta sync" },
      { dt: "Lag", dd: "~24 hours from WIPO" },
      { dt: "Coverage", dd: "All 130 Madrid members" },
      { dt: "Available on", dd: "Firm, Enterprise" },
    ],
  },
  {
    name: "WIPO Global Brand Database mirror",
    sub: "WIPO GBD · weekly snapshot",
    primary: false,
    pillLabel: "Firm + Enterprise",
    body:
      "Full mirror of WIPO's GBD covering 70M+ marks across 89 jurisdictions, for global prior-art searches. Updated weekly, with image specimens and full Vienna codes.",
    kvs: [
      { dt: "Records", dd: "~70M global marks" },
      { dt: "Lag", dd: "7 days" },
      { dt: "Jurisdictions", dd: "89 IP offices" },
      { dt: "Available on", dd: "Firm, Enterprise" },
    ],
  },
];

export type DqCard = {
  heading: string;
  value: string;
  valueSuffix?: string;
  /** Width % for the inline bar fill (0–100). */
  fillPct: number;
  /**
   * Optional CSS var token *name* ("ok" / "warn") — rendered as
   * `var(--<name>)`. Omit to fall back to the default `.dq-bar-fill`
   * oxblood color baked into the CSS.
   */
  fillColorVar?: "ok" | "warn";
  meta: string;
};

/** Six DQ cards in a 3-col grid. */
export const dqCards: ReadonlyArray<DqCard> = [
  {
    heading: "OCR confidence",
    value: "99.4",
    valueSuffix: "%",
    fillPct: 99.4,
    meta:
      "14 rows below threshold this month. Flagged for human review before search.",
  },
  {
    heading: "Duplicate detection",
    value: "99.92",
    valueSuffix: "%",
    fillPct: 99.92,
    fillColorVar: "ok",
    meta:
      "Same mark appearing in multiple issues collapsed to one record, with full history.",
  },
  {
    heading: "Image extraction",
    value: "94.1",
    valueSuffix: "%",
    fillPct: 94.1,
    fillColorVar: "warn",
    meta:
      "Specimens extracted from PDF and indexed for visual search. Fallback wordmark rendered when extraction fails.",
  },
  {
    heading: "Vienna code accuracy",
    value: "87.6",
    valueSuffix: "%",
    fillPct: 87.6,
    fillColorVar: "warn",
    meta:
      "Inferred via classifier when not provided. Verified manually on Enterprise.",
  },
  {
    heading: "Status currency",
    value: "< 24",
    valueSuffix: "h",
    fillPct: 100,
    fillColorVar: "ok",
    meta:
      "Mark status (pending → registered → opposed → abandoned) updates within 24 hours of Vietnam IP change.",
  },
  {
    heading: "Historical archive",
    value: "2018",
    valueSuffix: "→",
    fillPct: 100,
    meta:
      "Complete back-archive to 2018. Pre-2018 data available on Enterprise via dedicated import.",
  },
];

/** Bottom oxblood CTA strip. */
export const coverageCta = {
  h2: "Need the raw data? We have an API.",
  sub:
    "Every mark, every status change, every match against your watchlist — available as JSON over HTTPS or as a webhook. Enterprise customers only.",
  primaryLabel: "View API docs",
  primaryHref: "/docs",
  secondaryLabel: "Talk to sales",
  secondaryHref: "/login",
};
