/**
 * Typed copy module for the marketing landing page.
 *
 * Lives here (rather than inlined in `page.tsx`) so a future translation
 * pass or copy edit can happen in one file without touching JSX, and so
 * the marketing team has a single source of truth as soon as they start
 * editing without engineering (per `IMPLEMENTATION_PLAN.md` decision Q1:
 * MDX-in-repo + TS config until a CMS is needed).
 *
 * All copy mirrors `design_handoff_tradenet_marketing/Tradenet - Marketing.html`
 * verbatim — do not paraphrase without updating the design prototype too.
 */

export type FeatureCard = {
  /** Lucide-style icon identifier; mapped to JSX in `page.tsx`. */
  icon: "image" | "bell" | "calendar" | "grid";
  title: string;
  body: string;
  tech: string;
};

export type CoverageCell = {
  /** `Grant / Apr · 2026` shape — type (Filing=A, Grant=B) / month / year */
  label: string;
  /** Raw mark count for the gazette issue */
  count: string;
  /** Relative-time stamp, e.g. `2m ago` */
  meta: string;
};

export const landing = {
  hero: {
    eyebrow: "Vietnam Trademark Intelligence",
    /**
     * H1 with two inline accents:
     *   - `conflict` rendered with `<span class="stamp">` (oxblood ink)
     *   - `before` rendered with `<span class="strike">` (handwritten
     *     diagonal strike-through animation)
     * Page composes these spans directly; the data here just labels the
     * surrounding plain-text chunks for reference.
     */
    h1Plain: {
      lead: "Catch every ",
      stampWord: "conflict",
      middle: " in the Vietnamese gazette — ",
      strikeWord: "before",
      tail: " the opposition window closes.",
    },
    sub: "Tradenet ingests every IP VIETNAM issue the day it publishes, runs your watchlists against it, and surfaces the ten marks you actually need to look at this morning. No more reading 4,000-page PDFs.",
    ctaPrimary: "Start free 14-day trial",
    ctaGhost: "Watch 2-min tour",
    microcopy: "No credit card · 46,758 marks already indexed · Live coverage of T1–T4 weekly issues",
  },

  scorecard: {
    title: "Conflict scorecard · live",
    status: "Watching NEUREX",
    yours: { name: "NEUREX", meta: "Your mark · CR-2024-118" },
    other: { name: "NEUROFAX", meta: "Pharmasia SG · A_T2_2026" },
    /** 0..1 scores for the three rings under the mark plates */
    rings: [
      { score: 0.88, label: "Phonetic" },
      { score: 0.71, label: "Visual" },
      { score: 1.0, label: "Class 5,10" },
    ],
    verdict: "Likely conflict · 94% composite",
    oppositionClosesInDays: 19,
  },

  stats: [
    { value: "46,758", label: "Vietnamese marks indexed" },
    { value: "8", label: "Weekly gazettes / quarter" },
    { value: "5,283", label: "Opposition windows tracked" },
    /** `unit` rendered smaller + muted, e.g. "1.4s" → "1.4" + "s" */
    { value: "1.4", unit: "s", label: "Avg search time across corpus" },
  ] as const,

  featuresSection: {
    eyebrow: "What you get",
    h2: "Built for the way trademark work actually happens.",
    sub: "Not a generic search box on a PDF dump. Four core surfaces — each shaped around a job IP professionals do every week.",
  },

  features: [
    {
      icon: "image",
      title: "Image-similarity search",
      body: "Drop a specimen image. We compute perceptual hash + OCR + Vienna code inference, then surface every visually adjacent mark — even when the text reads differently.",
      tech: "pHash · OCR · Vienna 5.1",
    },
    {
      icon: "bell",
      title: "Watchlists that watch themselves",
      body: "Save a query — fuzzy name, image, class, applicant — once. It re-runs against every new gazette automatically. Monday morning you get a digest of what landed and what matters.",
      tech: "Auto re-run · Per-matter · Slack/email",
    },
    {
      icon: "calendar",
      title: "Opposition calendar",
      body: "Every published application opens a 5-month opposition window under Article 112. We surface yours sorted by days-remaining, with urgency colors and one-click filing handoff.",
      tech: "Vietnam Article 112 · Auto-track",
    },
    {
      icon: "grid",
      title: "Side-by-side conflict scorecard",
      body: "Pick two or three marks. Get a composite similarity score broken down across phonetic, visual, and class-overlap dimensions — with a recommendation you can defend in a client memo.",
      tech: "40% phonetic · 30% visual · 30% class",
    },
  ] as ReadonlyArray<FeatureCard>,

  imageSimilarity: {
    eyebrow: "Image similarity",
    h3: "Find lookalikes you'd never spell-check your way into.",
    bodyParas: [
      "Trademark conflict isn't a string match. A logo can be visually identical to yours and read “NEUROFAX” instead of “NEUREX” — and a typist-only search misses it entirely.",
      "Our pipeline extracts perceptual hashes from every specimen, runs OCR on the wordmarks, and infers Vienna codes — so one upload finds visual, typographic, and semantic neighbours in the same query.",
    ],
    bullets: [
      "Drop a PNG, JPG, or PDF — we handle the rest",
      "Tunable similarity threshold per query, saved per watchlist",
      "Vienna-code 5.1 inference for figurative-only marks",
    ],
    vizEyebrow: { left: "Image search · 0.87 threshold", right: "7 matches" },
    /** Score % shown in top-right of each cell; `matched` toggles oxblood tint */
    mosaic: [
      { word: "NEUREX", score: "100%", matched: true, font: "sans", weight: 800 as const, size: 34, fill: "var(--stamp)" },
      { word: "NEUROFAX", score: "94%", matched: true, font: "sans", weight: 800 as const, size: 30, fill: "var(--ink)" },
      { word: "NEURAXIS", score: "88%", matched: true, font: "serif", weight: 600 as const, size: 32, fill: "var(--ink)" },
      { word: "BIVAXIS", score: "81%", matched: false, font: "serif", weight: 600 as const, size: 30, fill: "var(--ink)" },
      { word: "VEXARIS", score: "79%", matched: false, font: "sans", weight: 700 as const, size: 28, fill: "var(--ink)", letterSpacing: 3 },
      { word: "ZENPHARM", score: "71%", matched: false, font: "sans", weight: 800 as const, size: 34, fill: "var(--ink)" },
    ],
  },

  opposition: {
    eyebrow: "Opposition windows",
    h3: "Five months is shorter than you remember at month four.",
    bodyParas: [
      "Vietnam gives you 150 days from publication to oppose. Miss it and your only option is invalidation proceedings — slower, more expensive, more uncertain.",
      "Every match against a watchlist creates a deadline. We sort by days-remaining, escalate the colour at 14 and 30 days, and hand off cleanly to your filing template.",
    ],
    bullets: [
      "Article 112 timer on every published application",
      "Madrid-protocol windows tracked separately",
      "Calendar export to Outlook, Google, ICS",
    ],
    vizEyebrow: { left: "Opposition · open windows", right: "5 closing in 30d" },
    rows: [
      {
        days: 8,
        urgency: "urgent" as const,
        mark: "NUROFEN PLUS · Class 5",
        meta: "Reckitt Benckiser · closes 28 May",
        barPct: 8,
        barColor: "var(--stamp)",
        cta: "File",
      },
      {
        days: 8,
        urgency: "urgent" as const,
        mark: "VEXIS · Class 5",
        meta: "Vexis Labs Pvt · closes 28 May",
        barPct: 8,
        barColor: "var(--stamp)",
        cta: "File",
      },
      {
        days: 19,
        urgency: "warn" as const,
        mark: "NEUROFAX · Class 5, 10",
        meta: "Pharmasia Holdings · closes 8 Jun",
        barPct: 18,
        barColor: "var(--warn)",
        cta: "Open",
      },
      {
        days: 19,
        urgency: "warn" as const,
        mark: "VEXARIS · Class 5, 10, 44",
        meta: "Bayer AG · closes 8 Jun",
        barPct: 18,
        barColor: "var(--warn)",
        cta: "Open",
      },
    ],
  },

  scorecardDeep: {
    eyebrow: "Conflict scorecard",
    h3: "A defensible answer, not a vibe check.",
    bodyParas: [
      "Every “is this a conflict?” question gets a composite score broken down across four dimensions — phonetic distance, visual hash, Nice-class overlap, and semantic similarity in the goods/services text.",
      "Weights are tunable per matter, and every score traces back to its evidence: the actual edit distance, the matched specimen, the overlapping class headings. Drop it straight into a memo.",
    ],
    bullets: [
      "Composite + per-channel scores you can defend in court",
      "Tunable weights per client matter",
      "One-click export to PDF memo or Word",
    ],
    vizEyebrow: { left: "Scorecard · NEUREX vs. NEUROFAX", right: "Composite 0.94" },
    otherName: "NEUROFAX",
    otherApplicant: "Pharmasia Holdings SG",
    composite: 0.94,
    verdict: "Likely conflict",
    bars: [
      { label: "Phonetic", pct: 88, color: "var(--stamp)" },
      { label: "Visual", pct: 71, color: "var(--warn)" },
      { label: "Class overlap", pct: 100, color: "var(--stamp)" },
    ],
  },

  coverageSection: {
    eyebrow: "Coverage",
    h2: "Every IP VIETNAM issue, the day it publishes.",
    sub: "Vietnam's Cục Sở hữu trí tuệ publishes weekly applications (Section A) and registrations (Section B). We OCR, deduplicate, and index all of it within hours of release.",
    /** Free-form footnote under the grid */
    footnote: "Madrid Protocol coverage included on Firm and Enterprise plans · WIPO Global Brand Database mirrored daily",
  },

  coverage: [
    { label: "Grant / Apr · 2026", count: "9,499", meta: "2m ago" },
    { label: "Grant / Mar · 2026", count: "5,326", meta: "8m ago" },
    { label: "Grant / Feb · 2026", count: "5,913", meta: "11m ago" },
    { label: "Grant / Jan · 2026", count: "6,608", meta: "17m ago" },
    { label: "Filing / Apr · 2026", count: "8,331", meta: "21m ago" },
    { label: "Filing / Mar · 2026", count: "3,273", meta: "28m ago" },
    { label: "Filing / Feb · 2026", count: "3,159", meta: "1h ago" },
    { label: "Filing / Jan · 2026", count: "4,649", meta: "1h ago" },
  ] as ReadonlyArray<CoverageCell>,

  cta: {
    h2: "See what landed in the gazette this week.",
    sub: "Free 14-day trial. No credit card. Upload one mark, get your first watchlist running in five minutes.",
    primary: "Start free trial",
    ghost: "View pricing",
  },
} as const;
