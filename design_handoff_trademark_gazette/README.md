# Handoff: Trademark Gazette redesign

## Overview

A redesign of an internal tool used by IP/trademark professionals to search, watch, and analyze entries in the Vietnamese Trademark Gazette (NOIP — Cục Sở hữu trí tuệ). The original tool worked but was framed as a generic SaaS admin around a database; this redesign re-anchors the UX on the user's actual jobs:

- **Watch** — what new filings this week resemble marks my clients own?
- **Clear** — is this proposed name conflict-free?
- **Oppose** — what's in the opposition window, and when does it close?
- **Report** — produce client-facing watch reports

The bundle ships four redesigned core screens plus two auxiliary screens.

---

## About the design files

The files in this bundle are **design references created as a static HTML/React-via-Babel prototype** — they show intended look and behavior, not production code to copy directly. The task is to **recreate these designs in the target codebase's existing environment** (likely the existing React + Tailwind app, judging by `reference/original_ui_demo.html`) using its established patterns, component primitives, and conventions. The Babel-in-browser setup, vanilla CSS, and `<script src="…">` glue used in the prototype are scaffolding for fast iteration only — they should not be ported.

If the existing codebase already has a Button, Card, Pill, Modal, etc., use those rather than recreating from this prototype's markup.

## Fidelity

**High-fidelity.** Final colors, typography, spacing, and interactions are specified below. Use these values exactly. Where the prototype uses placeholder copy or fake data, the README calls it out.

---

## What changed vs. the original (important context)

Reading the original `reference/original_ui_demo.html` then this redesign side-by-side will be the fastest way to understand intent. Key shifts:

| Area | Original | Redesigned |
|---|---|---|
| **Home screen** | Dashboard showing ingest pipeline stats (rows processed, file sizes, jobs completed) | "Today" screen anchored on the user's watchlist findings + open opposition windows. Pipeline stats collapse into a single admin strip at the bottom. |
| **Mark image** | Wordmark rendered as styled HTML text (e.g. SAMSUNG in `font-serif`) | Treated as a real specimen — SVG-rendered with distinct typography per mark, framed with corner registration ticks, captioned with WIPO INID code 540 + pHash |
| **Search modes** | Text substring only | Four modes: Text, Phonetic/fuzzy (Metaphone + Levenshtein), Image (pHash + OCR + Vienna inference), Vienna code |
| **Results** | Table only, no images | Grid (default) + Table view toggle. Grid shows mark specimen prominently. Multi-select with sticky toolbar → Compare N marks |
| **Detail view** | Card stack, all equal weight | Hero specimen card with claims (color, transliteration, disclaimer), procedural timeline (filed → exam → published → opposition → registration), live opposition countdown bar, full goods/services rendered |
| **New: Compare** | — | Side-by-side 2–3-up conflict review with a composite scorecard (phonetic 40% / visual 30% / class overlap 30%) |
| **Watchlists** | Implicit | First-class — saved queries that auto-re-run each issue, surfacing new findings on Today |
| **Cmd-K** | Hint shown but non-functional | Real command palette: actions + trademark search + watchlists + recent searches |
| **Localization** | English-only despite Vietnamese audience | Font (Be Vietnam Pro) renders diacritics correctly. Bilingual labels not implemented in this round — see "Open questions" below. |
| **Brand** | Generic Tailwind indigo `#6366f1` | Oxblood `oklch(0.45 0.135 28)` as default brand, with Teal and Ink alternates. Reads as "official record". |

---

## Screens / Views

There are 6 routes. The first 4 are the focus of the redesign; the last 2 are supporting.

The prototype uses internal state for routing (no real URLs). In the target codebase use proper URL routing.

### 1. `/` — Today (Dashboard)

**Purpose:** First screen on Monday morning. Tells the user what changed in the gazette since they last checked, what needs action this week, and lets them jump into work.

**Layout (desktop, ≥1000px):**

- Hero strip (full-width, bottom-border): left 1.4fr column with eyebrow + h1 + sub + two CTAs; right 1fr column with 3-up KPI tiles
- Two-column grid (1.4fr / 1fr, gap 20px): "New findings" on the left, "Opposition windows" on the right
- Two-column grid (1fr / 1fr): "Watchlists" and "Your recent activity"
- Collapsible pipeline strip at the bottom (closed by default)

Below 1000px the hero stacks; below 1080px the two-up grids stack.

**Hero strip:**
- Eyebrow: `"Tuesday 19 May · This week's digest"` — JetBrains Mono, 11px, weight 600, letter-spacing 0.12em, uppercase, mute color
- H1: e.g. `"9 new findings"` (oxblood) `"across 3 watchlists."` (mute) — Source Serif 4, 30px, weight 600, line-height 1.25, letter-spacing -0.015em. Two-tone via inline `<span>`s.
- Sub: count of opposition windows closing in 14 days + last sync timestamp, 14px mute
- CTAs: primary "Review findings →" + ghost "New search"
- 3 KPI tiles in a 1px-gap grid (visually hairlines): Findings (oxblood number) · Opposition · 7d (warn-amber if >0) · Watchlists. Number is 32px tabular-nums.

**New findings card:**
- Card title + sub describing scoring methodology
- List of rows; each row is a grid: `[100px specimen] [meta] [right block]`
- Specimen thumbnail with corner registration ticks
- Meta: name + type pill (A/B) + class chips; applicant; flag + country + appno + published date
- Right block: similarity ring (40px) + watchlist attribution (name + reason)
- Card foot: "Showing N of N" + tiny actions ("Dismiss all", "Generate client report")

**Opposition windows card:**
- List of rows for currently-open windows, sorted by days-remaining ASC
- Row layout: `[64px days-block] [meta] [actions]` with a 2px progress bar pinned to the bottom edge of the row
- Days block: big number (28px, tabular-nums, oxblood if urgent) + "DAYS" label in monospace
- If days-left ≤ 14, the row gets a horizontal gradient wash from oxblood-tint to transparent
- Progress bar: green ≥ 30 days, amber 15–30, oxblood ≤ 14
- Each row links to the mark's detail view

**Watchlists card** — list rows: 4px-wide marker (oxblood if newCount > 0 else light) + name + matter + query description; right: "+N" big number for new findings + "X total" small.

**Your recent activity card** — list of searches the user ran (NOT the system's ingest jobs).

**Pipeline strip** — `<details>` element, closed by default. Inside: 4 KPIs (Total trademarks, This quarter, Pages OCR'd, Manual review queue with `warn` color if > 0). This is the only place the ingest stats appear on Today.

---

### 2. `/search` — Search

**Purpose:** Find conflicting or interesting marks across the entire gazette corpus.

**Layout:**
- Query band, full-width white surface with bottom border:
  - Mode tabs row: Text / Phonetic+fuzzy / Image / Vienna code (segmented control feel; active = oxblood-tint background, oxblood text)
  - Input row (depends on mode): big text input with `⌘K`-style hint chips on the right for `applicant:`, `class:`, `agent:` operators; OR in image mode, a tile showing uploaded specimen + filename + pHash + OCR'd text + matching weights
  - Extras row: Similarity threshold slider (40–99%) + active filter chips + "Save as watchlist" link
- Body grid (240px / 1fr, gap 24px; collapses below 760px):
  - **Left rail** (filter groups): Record type, Country, Nice classes (with ANY/ALL toggle), Applicant, Publication date (date range + presets)
  - **Main** (results)

**Filter rail:**
- Each group has a sticky-feeling caps eyebrow (10.5px JetBrains Mono, mute) and a body of `<label>` rows
- Active filters get an oxblood-tint background + oxblood-colored count
- Class chips use mono numerals (`05`, `10`) plus the class label
- "Show all N classes →" / "Show all 67 countries" reveals the full picker (modal — not implemented in the prototype, build it in the app)

**Results toolbar:** Count headline ("**N trademarks** match …") + descriptive sub line ("Personal & company applicants · Classes 5, 10 · Vietnam + 4 others · last 90 days") + view-mode segmented (Grid/Table) + Sort select + Export.

**Results grid:**
- `repeat(auto-fill, minmax(280px, 1fr))`
- Each card: select checkbox top-left, similarity ring top-right, big specimen plate (paper-2 background, bordered bottom), meta block (name + type pill, applicant line, flag + appno + published, class chips)
- Selected state: oxblood border + 2px oxblood-tint glow

**Results table** — used when user wants density. Same columns but row-based: select / similarity ring / 90px specimen / name+applicant stacked / type pill / class chips / country / published / agent.

**Selection bar** (appears when ≥1 selected) — dark inverted (`var(--ink)` background, white text), sticky just under top nav: "Clear / N selected" left; "Add to watchlist / Tag / Export / Compare N marks →" right (Compare is oxblood primary).

**Pagination** at the bottom: "Showing 1–50 of N" + page numbers.

**Cmd-K palette** — accessible from anywhere via ⌘K or by clicking the top-nav search box:
- Overlay with backdrop blur, modal centered 14vh from top, 640px wide
- Groups: Actions, Trademarks, Watchlists, Recent (each filtered by query)
- Each item: small icon block + label + sub + hint kbd
- Hover state: oxblood-tint background + oxblood text

---

### 3. `/marks/:id` — Detail view

**Purpose:** Everything about one trademark, with workflow surfaces (file opposition, copy link, add to watchlist).

**Layout:**
- Breadcrumb strip: "← Back to results" + path crumb + action buttons (Watch, Copy link, Tag, primary "File opposition")
- Main grid (1fr / 320px sidebar; stacks below 1080px)

**Main column (top to bottom):**

1. **Specimen card** — two-column inside the card (1.05fr / 1fr; stacks below 900px). Left: large specimen plate in `--paper` background, gazette-style corner ticks, caption "WIPO INID code 540 · Reproduction of the mark" + pHash on right. Below: claim rows (Type of mark / Color claim / Transliteration / Disclaimer) — dashed underlines, mono uppercase labels.
   Right: H1 (Source Serif 4 if serif-heads on, 26px), pills (type A/B + status with pulse-dot), applicant block (name + flag/country/type/city), 2-column KV grid (appno, certno, filed, published, registered, expires, exam, agent), and the **Opposition box** at the bottom if the window is open.

2. **Opposition box** (only if window is open) — oxblood-tint background if days ≤ 14, paper otherwise. Big day-count + "days remaining" + primary "File opposition" button. Visualization underneath: horizontal progress bar marked with "Published [date]" on left and "Window closes [date]" on right. Foot text explains the legal frame ("Under Vietnam Article 112: opposition window = 5 months from publication. After this date, only invalidation proceedings remain.")

3. **Procedural timeline card** — vertical ol of events with circle-dot + connecting line. Done events: filled green dot with check. Current event: oxblood-filled dot with "!". Each row: label (oxblood if current) + mono date on the right, body description below.
   Events: filed → formal exam → substantive exam → published (anchor) → opposition closes (if A) → registration expected (if A) → registered (if B) → first renewal due (if B).

4. **Goods & services card** — for every Nice class on the mark, render a row of `[class chip] [full text]`. Matched classes use the oxblood-stamp variant. Don't collapse this behind a "Show full →" — show it all.

5. **Similar marks landing this period card** — grid of small tiles: `[80px specimen] [meta] [similarity ring]`. Clickable to navigate. CTA in card head: "Compare in side-by-side →" (links to Compare with this mark + the top 2 similar pre-selected).

**Sidebar:**

- **Source** card — gazette filename, page, issue, section, "Open in gazette →" button
- **Applicant's portfolio** card — name + 3 stat tiles (active marks / pending / oppositions filed) + "View all N marks →"
- **Co-marks** card — list of related marks from same applicant, with year + class chips
- **Raw INID markers** card — collapsed by default; "Expand" shows all 26 WIPO INID fields with OCR confidence

---

### 4. `/compare?ids=…` — Compare

**Purpose:** Side-by-side conflict review of 2–3 marks. Reached via Search multi-select → "Compare N marks" or via the Detail similar-marks card.

**Layout:**

- Same breadcrumb strip as Detail with primary "Export PDF report"
- **Conflict scorecard band** — white card, 22px padding:
  - Eyebrow + h2 ("MARK A vs. MARK B, MARK C") + sub explaining composite formula
  - Grid of scorecards for each non-anchor mark: name + applicant + composite similarity ring (52px); verdict pill ("Likely conflict" / "Possible conflict" / "Low risk"); three score bars (Phonetic / Visual / Class overlap) each as a label + thin track + percentage
- **Mark plates row** — grid: 1.2fr label column + repeat(N, 1fr) plate columns. First plate is the anchor — oxblood-tint background + tiny "YOUR MARK" label top-right. Each plate: big specimen + name+type pill below + applicant.
- **Comparative rows** — same grid structure. Each row: label cell on left (paper) + N cells of comparative values. Rows are grouped by sections (`Identity & status`, `Similarity to ANCHOR`, `Classes & overlap`, `Procedural state`, `Action`).
  - Class chips: when an "other" mark's class matches one of anchor's, it gets the oxblood-stamp variant.
  - Opposition windows row uses a pill: oxblood if ≤ 14 days, amber if open, mute if closed.
  - Action row recommends per-mark: "Consider opposition" (oxblood), "Watch closely" (amber), "Monitor only" (mute), based on a simple class-overlap + phonetic similarity check.

The first mark is always the anchor ("your mark"). Backend should let the user designate which mark is the anchor.

---

### 5. `/watchlists` — Watchlists (supporting)

Grid of watchlist cards, each showing: name + matter, "+N new this period" count, query description in a dashed monospace block, the actual recent findings (with mini specimens + similarity rings), and footer with total count + last run time.

The last tile is a "+ New watchlist" dashed-border placeholder.

### 6. `/admin/gazettes` — Gazettes (admin)

Closer to the original demo's Gazettes table. Should be gated to admin users — daily users live on Today. Key change: status column shows real failure modes — `Needs review` with warning tone when OCR confidence is low — not just "Completed" everywhere.

---

## Interactions & behavior

- **Top nav** — sticky at top, blur background. Logo + 4 tabs (Today / Search / Watchlists / Gazettes) + central search box (clicking opens Cmd-K) + alerts bell (with notification dot) + help + avatar.
- **Cmd-K shortcut** — `⌘K` / `Ctrl+K` from anywhere. `Esc` closes. The hint in the top-nav search box is real.
- **Tab navigation** — active tab gets a `paper-3` background and a 2px oxblood underline (inset box-shadow).
- **Navigation** — most clicks navigate within the SPA; `data-tab-link` and on-row clicks in the prototype model this. In the target codebase, use real URLs.
- **Hover** on rows: paper-2 background. On result cards: shadow-md elevation + line-strong border.
- **Selection** in search results: clicking the checkbox toggles select. The row click itself navigates to detail. Selection persists across pagination (this is the intent; the prototype only shows one page).
- **Compare CTA** — gated on `selected.size >= 2`. Max 3 marks (the layout breaks beyond that — design a "swap mark" interaction for swapping in/out).
- **Opposition countdown** — visualized two ways: the dashboard "Opposition windows" card uses a horizontal day count + bar; the detail view uses a progress bar with date markers. The bar fill color is determined by days remaining (oxblood ≤ 14, amber ≤ 30, green > 30).
- **Pulse dot** — small animated dot indicating live state (e.g. "Examination pending", "Active registration"). 1.6s ease-in-out infinite, scale 1→0.7→1 with opacity.
- **No real animations** beyond hover transitions (120–150ms) and the pulse dot.

## State management

Per screen (this is illustrative — adapt to the target codebase's data layer):

- **Today** — Read-only digest. Inputs: current user, last_sync_at. Queries: watchlist_findings (with similarity score, scoped to last gazette run), opposition_windows (open, sorted by closes_at asc), watchlists (with newCount derived from findings), recent_searches (last 7d for current user).
- **Search** — Local state: mode, query, similarityThreshold, filters {country[], classes[], applicantType, period, typeRecord}, view (grid/table), sortBy, selection (Set of mark ids). Server query reruns on filter change with debounce. Selected set must survive pagination.
- **Detail** — Param: markId. Loads mark, opposition_window (if any), timeline_events (derived from mark dates server-side), goods_services (full text per class), applicant_portfolio_stats, co_marks (same applicant), similar_marks (same period, similar via the engine).
- **Compare** — Params: markIds (comma-separated, 2–3). Loads each mark. Composite + per-channel scores should be computed server-side via the same similarity engine that powers search — don't re-implement the formula in the client. The weights (40/30/30) should be tunable per matter.

## Design tokens

All colors are in `oklch()`. Convert to your codebase's preferred format if needed.

### Surfaces & ink
```
--paper        oklch(0.992 0.004 85)   // warm off-white background
--paper-2      oklch(0.975 0.005 85)   // alt surface (kpi tile chrome, list-row hover)
--paper-3      oklch(0.955 0.006 85)   // pressed/selected nav background
--surface      #ffffff                  // card surface
--line         oklch(0.91 0.005 85)    // hairline borders
--line-strong  oklch(0.85 0.006 85)    // emphasized borders / dashed accents

--ink          oklch(0.22 0.018 255)   // primary text, near-black with a hint of blue
--ink-2        oklch(0.38 0.015 255)   // secondary text
--mute         oklch(0.55 0.012 255)   // meta / labels
--fade         oklch(0.72 0.010 255)   // tertiary / disabled
```

### Brand — Oxblood (default)
```
--stamp        oklch(0.45 0.135 28)    // brand / accent / primary buttons
--stamp-2      oklch(0.962 0.025 28)   // tint background for active filters, matched chips
--stamp-line   oklch(0.85 0.05 28)     // tint border
--stamp-deep   oklch(0.32 0.12 28)     // pressed / hover-darker for primary buttons
```

Two alternate brand swaps are also supported in the prototype's Tweaks panel:
- **Teal** — `--stamp: oklch(0.42 0.085 195)`, `--stamp-2: oklch(0.962 0.020 195)`, `--stamp-line: oklch(0.85 0.04 195)`, `--stamp-deep: oklch(0.30 0.08 195)`
- **Ink** — `--stamp: oklch(0.32 0.04 260)`, `--stamp-2: oklch(0.955 0.012 260)`, `--stamp-line: oklch(0.85 0.02 260)`, `--stamp-deep: oklch(0.22 0.03 260)`

### Semantic
```
--ok           oklch(0.46 0.10 165)    // success / "active registration"
--ok-2         oklch(0.952 0.030 165)
--warn         oklch(0.58 0.13 75)     // attention / amber for "examination pending" / soon-closing
--warn-2       oklch(0.955 0.04 75)
```

### Typography

Three fonts. Load via Google Fonts: `Be Vietnam Pro` (weights 400/500/600/700/800), `JetBrains Mono` (400/500/600/700), `Source Serif 4` (opsz, weights 400/500/600/700).

| Use | Font | Notes |
|---|---|---|
| Body, UI labels, buttons | Be Vietnam Pro | Renders Vietnamese diacritics well — this matters for the audience |
| Codes, numbers, eyebrows, labels | JetBrains Mono | Application numbers, certificate numbers, pHash, dates in tabular contexts, all-caps eyebrows |
| Section heads (optional toggle) | Source Serif 4 | `body[data-serifheads="1"]` opts in. Used for hero h1, card titles, page h1, band title, spec name |
| Mark specimens (synthesized) | Mix per-mark | See "Mark specimens" below |

Body base: 14px / 1.5. Tabular-nums on all numeric stats (`font-variant-numeric: tabular-nums`).

### Spacing & radius
```
--container       1320px
--row-pad-y       12px (cozy) | 8px (compact) | 18px (roomy)
--gap-card        20px (cozy) | 14px (compact) | 28px (roomy)
--radius          8px      // most controls/cards
--radius-lg       12px     // big cards
--shadow-sm       0 1px 0 rgba(20,16,12,0.04)
--shadow-md       0 1px 2px rgba(20,16,12,0.04), 0 6px 24px -8px rgba(20,16,12,0.10)
```

Density tokens are driven by `body[data-density]` — implement as a theming hook in the target codebase.

## Mark specimens

The prototype invents stylized wordmarks because we don't have real specimen images. **In production, mark specimens come from the gazette PDF as raster images** — render those as `<img>` inside the same plated frame.

Until real specimens are available, this prototype's specimen styles can act as fallback for marks whose image extraction failed (a typographic last-resort). They're SVG-rendered in `app/marks.jsx`:

- `wordmark-sans-bold` — Be Vietnam Pro 800, uppercase
- `wordmark-serif` — Source Serif 4 600, uppercase
- `wordmark-italic-serif` — Source Serif 4 500 italic
- `wordmark-rounded` — Be Vietnam Pro 800, tight tracking
- `wordmark-condensed` — Be Vietnam Pro 700, wide tracking
- `monogram-V` — V-stroke svg + small wordmark below
- `monogram-circle` — circle outline + 2-letter monogram inside

The plate frame is uniform: `var(--paper)` background, `var(--line)` 1px border, 6px radius, 4 corner registration ticks (8px L-shapes at 0.35 opacity) — these reads as "official record".

## Components inventory

The prototype's `app/` folder is organized for fast iteration, not production. In the target codebase, build these as proper components:

- **Layout**: AppShell, TopNav, ContentContainer
- **Cards**: Card, CardHead (title + sub + action slot), CardFoot
- **Buttons**: Button (primary, ghost, tiny), LinkButton, IconButton, SegmentedControl
- **Inputs**: TextInput (with hint slot), Checkbox, RadioToggle, RangeSlider, DateRangePicker, Select
- **Specimen primitives**: SpecimenPlate (uniform plated frame), MarkSpecimen (renderer)
- **Chips**: Pill (variants: ink, stamp, ok, warn, mute, A, B), ClassChip (compact mono), ClassChipFull (label + mono), FilterChip (removable)
- **Indicators**: SimilarityRing (svg ring + center percentage), PulseDot, ProgressBar
- **List rows**: FindingRow, OppositionRow, WatchlistRow, RecentSearchRow, CoMarkRow (these all share a `[icon/specimen] [meta] [right block]` skeleton)
- **Overlays**: CmdK (overlay + grouped results + keyboard nav), Modal, Drawer (used in original detail view; redesign uses a full page)
- **Compare-specific**: ScorecardBand, CompareGrid, CmpRow, CmpHeader, ScoreBar

Density is global — drive via theme tokens, not per-component props.

## Data shape

(See `app/data.js` for the full mock data, but here's the schema for the actual API.)

```ts
type Mark = {
  id: string;
  name: string;
  applicant: string;
  applicantType: "company" | "personal" | "government";
  country: ISO2;
  countryName: string;
  appNo: string;          // e.g. "4-2025-71204"
  certNo?: string;        // e.g. "4-0289741", present if registered
  type: "A" | "B";        // application vs. registration
  typeLabel: string;      // human-readable, e.g. "Application", "Registration (Madrid)"
  classes: number[];      // Nice classes (1..45)
  publishedAt: ISODate;
  filedAt: ISODate;
  examinedAt?: ISODate;
  registeredAt?: ISODate;
  expiresAt?: ISODate;
  oppositionEnds?: ISODate;
  city: string;
  agent: string;          // "—" if none
  specimen: {
    style: SpecimenStyle;  // see "Mark specimens" above; or replace with imageUrl
    color: "ink" | "stamp" | "ok";
    text: string;
    imageUrl?: string;     // preferred when available
  };
  gazette: string;         // source filename
  page: number;
  similarToWatch?: {       // populated when this mark hits one of the user's watchlists
    score: number;         // 0..1
    watchId: string;
    reason: string;        // explanation, e.g. "Phonetic + class overlap"
  };
};

type Watchlist = {
  id: string;
  name: string;
  client: string;
  matter: string;          // matter ID, e.g. "CR-2024-118"
  queryDesc: string;       // human-readable summary of the saved query
  query: WatchQuery;       // the actual saved query (text/phonetic/image-ref/class/country/etc.)
  newCount: number;        // findings since last_seen_at
  totalCount: number;      // lifetime total
  lastUpdated: ISODate;
};

type OppositionWindow = {
  markId: string;
  closesAt: ISODate;
  daysLeft: number;        // negative if closed
  status: "open" | "closed";
  relevant: boolean;       // true if linked to one of the user's watchlists
  watchId?: string;
};

type SearchQuery = {
  mode: "text" | "phonetic" | "image" | "vienna";
  q?: string;
  imageRef?: { phash: string; ocr: string; viennaCodes: string[] };
  viennaCodes?: string[];
  threshold: number;       // 0..1
  filters: {
    country: ISO2[];
    classes: number[];
    classesMode: "any" | "all";
    applicantType?: "company" | "personal" | "government";
    typeRecord?: "A" | "B-domestic" | "B-madrid";
    period: { from: ISODate; to: ISODate };
  };
  sort: "similarity" | "publication-desc" | "applicant-asc" | "class-count";
};
```

## Assets

No bitmap assets. All visuals are CSS + SVG. The favicon "T" logo block is in `app/shell.jsx` (the `Logo` component) — a 28×28 oxblood rounded square with a white "gazette-stack" SVG mark.

Flag emoji are inline (`🇻🇳`, `🇨🇳`, etc.) — fine for desktop; consider Twemoji shim if you need cross-platform parity.

## Files in this bundle

```
design_handoff_trademark_gazette/
├── README.md                              ← this file
├── Trademark Gazette - Redesign.html      ← main entry point of the prototype
├── screenshots/                           ← reference renders of each screen
│   ├── dashboard.png                      ← Today, top of page
│   ├── dash-findings.png                  ← Today, findings + opposition windows
│   ├── dash-watchlists.png                ← Today, watchlists + recent activity
│   ├── search.png                         ← Search, grid view with rail
│   ├── search-selection.png               ← Search with multi-select + sticky compare bar
│   ├── detail.png                         ← Detail, specimen + facts + opposition box
│   ├── detail-timeline.png                ← Detail, procedural timeline + goods/services
│   ├── compare.png                        ← Compare, conflict scorecard band
│   ├── compare-rows.png                   ← Compare, comparative rows
│   ├── watchlists.png                     ← Watchlists overview
│   └── cmd-k.png                          ← Command palette (filtered by "neur")
├── app/
│   ├── app.css                            ← all design tokens + screen styles
│   ├── data.js                            ← mock data (marks, watchlists, oppositions, gazettes)
│   ├── marks.jsx                          ← MarkSpecimen renderer + Pill / SimilarityRing / ClassChip / Flag
│   ├── shell.jsx                          ← TopNav + Cmd-K palette + Logo
│   ├── screen-dashboard.jsx               ← Today
│   ├── screen-search.jsx                  ← Search + filter rail + results grid/table
│   ├── screen-detail.jsx                  ← Detail + Timeline + OppositionBox + SimilarMarks
│   ├── screen-compare.jsx                 ← Compare + ScorecardBand + CmpRow
│   ├── screen-aux.jsx                     ← Watchlists + Gazettes
│   ├── tweaks-panel.jsx                   ← prototype-only theme switcher; ignore in production
│   └── index.jsx                          ← root + routing state
└── reference/
    └── original_ui_demo.html              ← the pre-redesign demo, for comparison
```

Open `Trademark Gazette - Redesign.html` in a browser to see the full prototype. Try the Tweaks panel (toggle in top toolbar) for brand color, density, serif-heads, and quick-jump shortcuts to specific routes.

## Open questions for the team

These were intentionally not designed-around. Flag them in your implementation plan:

1. **Localization.** The audience is Vietnamese but the UI is English. Implement a real i18n layer? Bilingual labels? Vietnamese-primary? At minimum, the field labels in the gazette (already Vietnamese in source data, e.g. "10 năm") should be translated or transliterated consistently.
2. **Permissions.** The Gazettes / pipeline view should be gated to admin roles. Who else has admin? Is there a separate "matters & clients" admin?
3. **Mark images.** The specimens in this redesign are synthesized SVG wordmarks. Production needs real raster extraction from the gazette PDFs, with a fallback specimen style when extraction confidence is low.
4. **Similarity engine.** Visual (pHash), phonetic (Metaphone + Levenshtein), semantic (NLP on goods/services) are referenced in the UI but the actual engine is a black box. The 40/30/30 weights should be per-matter-tunable.
5. **Reports.** "Generate client report" and "Export PDF report" CTAs are in the UI but no report template is designed. Worth a dedicated design round if reports are a real workflow.
6. **Notifications.** The alerts bell shows a dot but there's no notification surface yet. Email digests + in-app bell drop-down are obvious next pieces.
7. **Vietnam-specific procedural rules.** The opposition window is hardcoded to 5 months in the prototype. Confirm against Article 112 and whether the rule differs for Madrid-originated marks.
