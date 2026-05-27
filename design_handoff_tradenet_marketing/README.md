# Handoff: Tradenet marketing site

> **Implementation status (2026-05-28):** plan saved at
> [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md). Decisions on
> CMS, architecture (Route Groups in `app/frontend/`), and PR sequence
> are captured there. Execution paused before PR 0 — pick up by
> re-reading the plan, then branching off `main`.

## Overview

The public-facing marketing site for **Tradenet** — a Vietnamese trademark intelligence tool. This bundle ships a single static HTML prototype containing five routes (Landing, Pricing, Coverage, Docs, Login) wired together with hash-based routing and a small amount of vanilla JS.

The companion design bundle is `design_handoff_trademark_gazette/` (the in-app surfaces: Today / Search / Detail / Compare / Watchlists / Gazettes). The marketing site reuses the same design vocabulary — oxblood brand, Be Vietnam Pro + Source Serif 4 + JetBrains Mono, gazette-paper aesthetic — so both should be implemented against one shared design system.

## About the design files

The files in this bundle are **design references created as static HTML/CSS + vanilla JS** (with a small inline React+Babel block only for the Tweaks panel — that's prototype-only, do not ship). The task is to **recreate these designs in the target marketing-site codebase** — typically Next.js / Astro / Remix / a static site generator — using its conventions for routing, MDX content, image optimization, and form handling.

The HTML is intentionally direct-editable: long-form copy lives in the source, not in JS. That property should survive the rewrite: marketing copy + docs content should be MDX or CMS-backed, not buried inside React components.

## Fidelity

**High-fidelity.** Final colors, typography, spacing, copy, and interaction patterns. Use the values exactly. Tasteful tweaks to copy and stat values are expected; the typographic system, brand color, and layout structure are not.

---

## Routes

Five routes, hash-routed in the prototype (`#/`, `#/pricing`, `#/coverage`, `#/docs`, `#/login`). In the target codebase use proper URL routes (`/`, `/pricing`, `/coverage`, `/docs/:slug`, `/login`).

### 1. `/` — Landing

The product pitch. Optimized for a 60-second visit by an IP-firm partner.

**Section order (top to bottom):**

1. **Top nav** — sticky, paper background with blur. Logo + 4 tab links + Sign in (link) + Start free trial (primary). Logo shows `Tradenet` in Be Vietnam Pro + `.vn` in mute.
2. **Hero** — two columns (1.05fr / 1fr).
   - Left: eyebrow ("Vietnam Trademark Intelligence") + h1 with two-tone treatment ("Catch every **conflict** in the Vietnamese gazette — ~~before~~ the opposition window closes") + sub + two CTAs (primary "Start free 14-day trial" + ghost "Watch 2-min tour" with play icon) + microcopy under the CTAs with a small green status dot
   - Right: a "Conflict scorecard · live" card that simulates the in-app scorecard — two mark plates side by side ("NEUREX" vs "NEUROFAX") with similarity rings (Phonetic / Visual / Class) below, verdict pill, and an "Opposition closes in 19 days" footer. The card has a -0.5° tilt for visual interest.
   - Background: soft radial gradient pulling oxblood-tint from upper-right
3. **Stats strip** — full-width band with a 1px-hairline grid of 4 stats: marks indexed (46,758), weekly gazettes/quarter (8), opposition windows tracked (5,283), avg search time (1.4s)
4. **Features** — 4-up grid, each card: icon (oxblood-tinted square), serif h3, body copy, dashed-underlined eyebrow at the bottom showing the underlying tech ("pHash · OCR · Vienna 5.1")
5. **Deep-dive: Image similarity** — split section with the mark mosaic visualization on the left (3×2 grid of mark plates, matched ones tinted oxblood with their match-percent in the corner) and explanatory copy + checked bullets on the right. Paper-2 background, bordered top + bottom.
6. **Deep-dive: Opposition calendar** — reversed split. Calendar viz on the right shows 4 opposition rows with day-count + colored progress bars + "File / Open" buttons.
7. **Deep-dive: Conflict scorecard** — split with detailed scorecard viz on the left (composite ring, verdict pill, 4 score bars). Paper-2 background.
8. **Coverage grid** — 4×2 grid of recent gazette issues. Each cell: green dot + issue name (mono), big serif count, mute meta line ("Registrations · 2m ago"). Subtitle below the grid mentions Madrid + WIPO.
9. **CTA strip** — full-width oxblood-gradient banner with rounded corners, two-column. Headline + sub on left, two white-on-oxblood buttons on the right. Decorative circular highlight in the top-right corner.
10. **Footer** — 5-column grid: brand + tagline · Product · Company · Resources · Legal. Bottom bar with copyright + version. Hidden on the Login route.

### 2. `/pricing` — Pricing

3-tier pricing card row + comparison table + FAQ.

- **Header**: eyebrow + serif h1 ("Priced for the work, not the dashboard.") + sub. Below the head: two segmented controls — period (Annual · save 17% / Monthly) and currency (USD / VND).
- **3 tier cards** — Solo / Firm (featured) / Enterprise. Featured tier is translated up by 8px, has a 2px oxblood border, an oxblood→white gradient background, a "MOST POPULAR" badge poking above the top edge, and a primary CTA (the others use ghost CTAs).
  - Each card: name (serif h3) + tagline (mute), price block (`$` + amount + `/ mo` + bill-note), CTA, divider, "Includes" / "Everything in X, plus" label, bullet list (muted bullets for "not included" items).
  - Prices update live as the toggles change. USD/VND, Annual/Monthly. Enterprise is always "Custom".
- **Comparison table** — full-feature compare. Section rows (paper-3 background, mono uppercase label) divide groups: Search / Coverage / Workflow / Team & security / Support. The Firm column has a subtle oxblood-tinted background to mirror the featured tier card.
- **FAQ** — two-column: title + sub on the left, `<details>` accordion items on the right with + / − indicators. First item is open by default.

### 3. `/coverage` — Coverage (data corpus)

The "trust" page. Open about what's indexed, how fresh it is, and where we fall short.

- **Hero**: eyebrow + big serif h1 + sub. Below: 4-up stats grid (marks indexed / issues YTD / median ingest lag / OCR confidence) with subtitles giving the methodology.
- **Source cards** — 2-column grid. First 2 cards (Vietnam IP Section A and B) carry a "Primary source" pill and a 2px oxblood border with the tinted background gradient. The Madrid and WIPO mirror cards are standard. Each card has a 2×2 KV footer (frequency, lag, fields, availability) on a dashed top border.
- **Ingest timeline** — full-width visual showing 4 rows (2025 A, 2025 B, 2026 A, 2026 B) × 52 weeks of cells. Cells are colored by load (0 / <2k / 2–5k / 5–8k / >8k) using a 4-step oxblood ramp. Hover any cell for a tooltip. Legend at the top-right of the card.
- **Data quality grid** — 3×2 grid of metric cards: OCR confidence / Duplicate detection / Image extraction / Vienna code accuracy / Status currency / Historical archive. Each card: mono uppercase label + big serif percentage + thin progress bar + meta description. Numbers that look bad (87.6%, 94.1%) are kept that way — the page promises "openly measured" so don't sanitize them.
- **CTA strip** — links to /docs#api

### 4. `/docs` — Documentation

Two-column layout: sticky sidebar + main article column.

- **Sidebar** (240px wide on desktop, scrolls independently with `top: 88px`): 5 grouped sections — Getting started / Searching / Workflow / API / Reference. Each link is a button (not anchor) so it can switch articles via JS without route changes. Active link has oxblood-tint background. Some links carry a small mono badge ("5 min", "Ent", "↗").
- **Main column** (max-width 760px): renders one article at a time, switched via the sidebar.
  - **Eyebrow pill** at top (oxblood-tinted, mono, e.g. "Reference · Vienna 5.1")
  - **H1** (38px serif) + **lede** (17px ink-2)
  - **TOC card** (paper-2, mono uppercase label, ordered list)
  - **H2** sections numbered with a mono "01", "02"… prefix in oxblood
  - **Body paragraphs** (15px / 1.65)
  - **Callouts** — paper-2 background with 3px oxblood left-border and an uppercase mono label
  - **Code blocks** — dark surface (`oklch(0.18 0.015 255)`), JetBrains Mono, language hint top-right, basic syntax highlighting via `.k` `.s` `.c` `.p` spans
  - **Tables** — full-width with mono uppercase column heads
  - **Footer** — flex row with previous + next page navigators (each a card-like button)
- **8 articles fully written**: Introduction · Your first watchlist · Image similarity · REST API · Article 112 guide · Vienna codes · Nice classification · Vietnam IP glossary. 9 more sidebar entries fall through to a "Coming soon" placeholder.

### 5. `/login` — Login

Two-pane layout. The marketing top-nav is hidden on this route (set `body.login-mode` to hide; nav `display: none`). The footer is also hidden.

- **Left pane** — paper background with two effects: a subtle vertical pinstripe (repeating-linear-gradient at 28px) and an oxblood-tint radial in the bottom-right.
  - **Brand mark** at top
  - **Specimen mosaic**: 3×3 grid of mark plates rendered in mixed typography styles, two of them oxblood-tinted. Visual signal that this is a trademark product.
  - **Quote block** at the bottom with a big serif quotation mark in oxblood + 22px serif testimonial + author byline. Quote is positive but specific ("eleven days to spare").
- **Right pane** — white surface, form centered, max-width 380px.
  - Small "← Back" link top-right (mono uppercase)
  - H1 ("Welcome back.") + sub
  - 2 SSO buttons (Google Workspace · Microsoft 365) — each with the brand icon, label, and right-aligned "SSO" hint
  - "or" divider
  - Email input with magic-link CTA. Below the input: "We'll email you a one-time sign-in link. Use password instead" with the link in oxblood
  - Primary button: "Email me a sign-in link"
  - Footer link: "Don't have an account? Start your 14-day trial →"
  - Trust strip at the bottom: SOC 2 Type II · GDPR · VN Data Residency — mono uppercase, small lock icons

---

## Interactions

- **View routing** — hash-based in the prototype. In the target codebase use real URLs and prefetch where possible.
- **Pricing toggles** — period (Annual / Monthly) and currency (USD / VND). Updating either updates the visible amount and the bill-note line. Numbers are hard-coded in `marketing/marketing.js` and need to live in CMS / config in production.
- **Docs sidebar switching** — clicking a sidebar button hides all `[data-doc-content]` articles except the one whose `data-doc-content` matches the clicked `data-doc`. Articles that don't have content fall through to the `placeholder` article (controlled by the `PLACEHOLDER_DOCS` set in `marketing/marketing.js`).
- **Coverage timeline** — rendered on demand the first time the Coverage view becomes visible. Cells use a deterministic pseudo-random load function for the demo data; replace with real ingest stats.
- **Similarity rings** — small SVG primitives rendered by `marketing/marketing.js` on every `.simring` element, reading `data-score` and `data-size` attributes.
- **Hover transitions** — 120–150ms ease on background and border-color. Buttons translate Y by 1px on `:active`.
- **No scroll-driven animation** — by design. The page is dense and the eye does its own work.

## Design tokens

The marketing site **shares the same token set** as the in-app design. See `design_handoff_trademark_gazette/README.md` for the canonical token list. Quick reference:

- **Brand**: oxblood `oklch(0.45 0.135 28)`, with stamp-2 / stamp-line / stamp-deep variants. Two alt brands (Teal, Ink) available via `body[data-theme]`.
- **Paper / ink** ramp: `--paper`, `--paper-2`, `--paper-3`, `--surface` / `--line`, `--line-strong` / `--ink`, `--ink-2`, `--mute`, `--fade`.
- **Semantic**: `--ok` `--warn` and their tints.
- **Type**: Be Vietnam Pro (body), JetBrains Mono (codes / eyebrows / numbers), Source Serif 4 (display heads).
- **Radius**: 7px (buttons), 8px (controls), 14px (cards), 20px (CTA strip).
- **Container**: 1240px max-width. Use the same width on both marketing and app for visual consistency.

Marketing-specific values (only used here):

```
--radius-xl       20px               // CTA strip
--shadow-lg       0 1px 2px rgba(20,16,12,0.04), 0 24px 60px -20px rgba(20,16,12,0.18)
```

## Components inventory

In the target codebase, build these as proper components (most have direct in-app analogues):

- **Layout**: MarketingNav (sticky, blur), MarketingFooter, Container
- **Buttons**: Button (primary, ghost, link, sizes lg / md / sm), KbdHint
- **Hero primitives**: HeroEyebrow (lined), HeroH1 (with `.stamp` and `.strike` accent spans)
- **Cards**: FeatureCard, SourceCard (with KV footer), VizCard, ScorecardCard, OppCalRow, SpecMosaic + SpecMosaicCell, TierCard (with `featured` variant + badge)
- **Pricing**: PricingSeg (segmented control), PricingTierCard, ComparisonTable
- **FAQ**: FAQ item (`<details>` based)
- **Coverage**: StatTile, IngestTimeline, DqCard
- **Docs**: DocsSidebar, DocsArticle, DocsCallout, DocsCodeBlock, DocsTable, DocsNavButton
- **Login**: SsoButton, LoginField, LoginDivider, SpecimenMosaicWall, LoginQuote
- **Specimen primitives**: SpecimenPlate (uniform plated frame with corner ticks), MarkSpecimen renderer (SVG, scales)
- **Shared with app**: SimilarityRing, Pill, ClassChip

The Tweaks panel (`marketing/tweaks.jsx`) is **prototype-only**. Do not ship it. It exists so reviewers can swap brand color, default currency, and the annual-discount badge label without rebuilding.

## Content sources

The marketing-site copy should not be locked inside React components. Recommended pattern:

- **Landing copy** — small JSON / YAML / TS module per section. Easy to A/B test.
- **Pricing tiers + comparison rows** — config module. Currency / period prices live here.
- **Docs articles** — MDX. The 8 written articles in this bundle map 1:1 to MDX files.
- **FAQ** — MDX or a simple `{ q, a }[]` config module.
- **Stats** (46,758 marks, ingest lag, etc.) — read from the same data layer the app uses, with stale-while-revalidate caching. Don't hard-code in copy.

## SEO / performance

Not in scope of this design, but worth flagging for the implementer:

- The hero conflict scorecard should be SSR'd (it's the LCP candidate)
- Fonts should be self-hosted (currently fetched from fonts.googleapis.com) and preloaded with `font-display: swap`
- Page weight in production should be << the prototype — the React + Babel runtime is for Tweaks only and shouldn't ship
- Per-route `og:image` should match the hero of that route (Landing → scorecard demo, Pricing → tier cards, etc.)

## Files in this bundle

```
design_handoff_tradenet_marketing/
├── README.md                          ← this file
├── Tradenet - Marketing.html          ← single-file prototype, all 5 routes
├── screenshots/                       ← reference renders
│   ├── landing.png                    ← Landing hero + features region
│   ├── pricing.png                    ← Pricing tier cards + toggles
│   ├── coverage.png                   ← Coverage hero + stats grid
│   ├── docs.png                       ← Docs sidebar + Introduction article
│   └── login.png                      ← Two-pane login
├── marketing/
│   ├── marketing.css                  ← all marketing-site styles + tokens
│   ├── marketing.js                   ← view switcher, pricing toggles, similarity rings, timeline, docs sidebar
│   └── tweaks.jsx                     ← prototype-only Tweaks panel
└── app/
    └── tweaks-panel.jsx               ← shared Tweaks helper (also prototype-only)
```

Open `Tradenet - Marketing.html` in a browser. Try the Tweaks panel (toggle in top toolbar) for brand color, currency default, and the "Jump to" shortcuts that route between views.

## Open questions

These were intentionally not designed-around. Confirm with the team before implementation:

1. **CMS choice.** Marketing copy + docs content should be CMS-backed (Sanity, Contentful, MDX-in-repo, etc.). Pick one before writing components.
2. **Authentication backend.** Login currently goes nowhere. Need to decide on auth provider (Auth0, WorkOS, Clerk, custom) — affects the SSO button list and the magic-link flow.
3. **i18n.** Site is English-only. The audience (Vietnamese IP firms) probably wants at least a Vietnamese version of the marketing pages. Critical Vietnamese terminology (Cục Sở hữu trí tuệ, Vietnam IP, T1–T4) is preserved in English copy.
4. **Pricing localization.** USD + VND are toggled; do we localize amounts by IP geolocation? Show currency toggle prominently or default-by-region?
5. **Annual discount.** Currently hard-coded at 17% (= 2 months free). Confirm before launch.
6. **Pricing values.** $49 / $179 are placeholders. Confirm with finance.
7. **Customer logos / case studies.** No social proof beyond one testimonial in the login pane and aggregate stats. If you have early customers willing to be named, a "Trusted by" logo strip slots cleanly below the hero stats.
8. **API access docs.** Need real API base URL + actual endpoint shapes before launch. The docs page assumes `api.tradenet.vn` and stub schemas.
9. **Vietnam IP brand permission.** Footer says "operating under license from Vietnam IP" — confirm this language is accurate with legal.
10. **Trust badges.** SOC 2 Type II + GDPR + VN Data Residency are claimed on the login footer. Confirm with security before launch.
