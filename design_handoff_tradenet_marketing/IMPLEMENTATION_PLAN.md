# Marketing site — implementation plan

Companion to [`README.md`](./README.md). The README describes **what to build**;
this doc describes **where it lives in our codebase**, **the PR sequence**, and
the decisions that pin those choices down. A future session should be able to
read just this file (plus the README) and start executing PR 0.

Status: **plan saved, not yet implemented**. Pause point — execution begins
with the token reconciliation PR.

---

## Where it ships

**Same Next.js app, two Route Groups.** Do not spin up a second frontend
repo — design tokens, build pipeline, CI, deployment, and Playwright suite
already live in `app/frontend/` and would all need duplicating.

Next.js 15 Route Groups (parentheses-named directories) carry their own
`layout.tsx` without affecting URLs, so the marketing layout (no auth) and
the app layout (with `AuthProvider`) coexist cleanly in one codebase.

```
app/frontend/app/
├── (marketing)/                    ← public, no AuthProvider
│   ├── layout.tsx                  ← MarketingNav + MarketingFooter
│   ├── page.tsx                    ← Landing  (/)
│   ├── pricing/page.tsx
│   ├── coverage/page.tsx
│   ├── docs/
│   │   ├── layout.tsx              ← sidebar
│   │   └── [[...slug]]/page.tsx    ← MDX-backed
│   └── _content/                   ← TS + MDX content modules
│       ├── landing.ts
│       ├── pricing.ts
│       └── faq.mdx
├── (app)/                          ← authenticated; AuthProvider here
│   ├── layout.tsx                  ← AuthProvider + TopNav
│   ├── today/page.tsx              ← moved from current root `app/page.tsx`
│   ├── search/page.tsx             ← moved
│   ├── compare/page.tsx            ← moved
│   ├── watchlists/page.tsx         ← moved
│   ├── admin/gazettes/page.tsx     ← moved
│   ├── marks/[id]/page.tsx         ← moved
│   └── trademarks/[id]/page.tsx    ← moved
└── login/                          ← public (no group); replaces current
    └── page.tsx                    ← two-pane design from handoff
```

URLs visible to users are unchanged. The current root `app/page.tsx` (Today
digest, requires auth) moves into `(app)/today/page.tsx`; the new
`(marketing)/page.tsx` becomes `/`. An authenticated visitor hitting `/`
will see the marketing landing — same as a logged-out visitor. **There is
no auto-redirect to the app for logged-in users.** A "Sign in" link in the
TopNav takes them to `/today`. (Open for discussion: we could add a
client-side redirect for logged-in users hitting `/`, but it's not in the
handoff. Default is no.)

---

## Decisions confirmed

These resolve the README's "Open questions" enough to start building.

| README Q | Decision |
|---|---|
| 1 — CMS | **MDX-in-repo + TS config modules.** No external CMS. Docs as `.mdx` files under `(marketing)/docs/_articles/`; landing copy, pricing, FAQ as typed TS / MDX modules. Migrate to Sanity/Contentful only when the marketing team starts editing without engineering. |
| 2 — Auth provider | **Defer to PR 3 review.** Magic-link backend (`POST /api/v1/auth/magic-link/request`, `/verify`) is new work — currently we only have password login. SSO buttons in PR 3 ship as visual stubs (`onClick={() => alert("SSO coming soon")}`) until the auth provider is chosen (Auth0 / WorkOS / Clerk / custom). Magic-link form falls back to a "please use password" hint until backend is wired. |
| 3 — i18n | **Defer.** English-only as designed. Revisit after launch; the Vietnamese audience can read the site in English (and the in-product UI uses Vietnamese-aware fonts already). |
| 4 — Pricing localization | **No geo-detect.** Currency toggle prominent in the UI; defaults to USD. Annual default. |
| 5 — Annual discount | **17% (= 2 months free) as designed.** Hard-coded in `pricing.ts` config; can be changed in one place. |
| 6 — Pricing values | **$49 / $179 / Custom as placeholders.** Ship to staging with these; confirm with finance before public launch. |
| 7 — Customer logos | **Skip for now.** No social proof beyond the one testimonial in the login pane + aggregate stats. Adds cleanly later. |
| 8 — API docs URL | **Stub as `api.tradenet.vn`** in the Docs MDX. Replace with real values in a follow-up PR. |
| 9 — Vietnam IP brand language | **Keep as designed pending legal review.** Footer reads "operating under license from Vietnam IP" — flag to legal before launch but ship to staging as-is. |
| 10 — Trust badges | **Keep SOC 2 / GDPR / VN Data Residency as designed.** Confirm with security before public launch. |

---

## Token reconciliation (PR 0)

Three small token deltas between `app/frontend/app/globals.css` (app) and
`design_handoff_tradenet_marketing/marketing/marketing.css` (handoff).
All colors, font stacks, and alt-theme variables already match.

| Token | App today | Handoff value | Decision |
|---|---|---|---|
| `--container` | `1320px` | `1240px` | **Unify on 1240px.** The slimmer column reads better on widescreens; in-app pages tolerate the change. |
| `--radius-lg` | `12px` | `14px` | **Unify on 14px.** Card corners get a touch softer. |
| `--radius-xl` | — | `20px` | **Add.** Used by the marketing CTA strip; harmless elsewhere. |
| `--shadow-lg` | — | layered drop | **Add.** Used by the hero scorecard tilt + pricing featured tier. |

PR 0 also runs the existing Playwright visual baselines to confirm the in-app
look isn't disrupted. The 1320 → 1240 change is small enough that the
existing `max-w-container` Tailwind class still works (it reads from CSS
variable) — pages just become 80px narrower. Visual diffs may show as a
shift; we re-bake baselines if the new look is correct.

---

## PR sequence

Each PR is independent, atomic, and shippable. **All five run after PR 0.**

### PR 0 — Token reconciliation (5–10 min)
Updates `globals.css`. Touches no components. Re-bakes Playwright visual
baselines if the in-app look shifts.

### PR 1 — Landing (~3–4 hr)
**Scope:**
- Create `(marketing)/` and `(app)/` route groups
- Move `app/page.tsx` → `(app)/today/page.tsx`; same for search, compare,
  watchlists, admin/gazettes, marks/[id], trademarks/[id]
- `(marketing)/layout.tsx` with `MarketingNav` + `MarketingFooter`
- `(app)/layout.tsx` with `AuthProvider` + existing `TopNav`
- `(marketing)/page.tsx` — full Landing implementation
- `_content/landing.ts` — typed copy module (h1 stanzas, feature card text,
  CTA microcopy, stats labels)
- New components: `MarketingNav`, `MarketingFooter`, `Container`,
  `HeroEyebrow`, `HeroH1` (with `.stamp` + `.strike` accent spans),
  `FeatureCard`, `VizCard`, `OppCalRow`, `SpecMosaic`, `SpecMosaicCell`,
  `ConflictScorecardCard`, `StatStrip`
- Reused from existing app: `Button`, `SimilarityRing`, `Pill`, `Icon`
- Stats fetched from `GET /api/v1/stats/overview` (already exists) with
  ISR re-validate 1h
- Playwright visual baselines for `/` (landing) added

**Acceptance:**
- `/` renders the full landing exactly per handoff
- `(app)/today` still works for authenticated users
- `pnpm build` clean, `pnpm test:e2e` all green
- Visual baseline committed

### PR 2 — Pricing (~2–3 hr)
**Scope:**
- `(marketing)/pricing/page.tsx`
- `_content/pricing.ts` — tiers × currencies × periods × bullets +
  comparison table rows + FAQ entries
- New components: `PricingSeg` (segmented control), `PricingTierCard` +
  `featured` variant + badge, `ComparisonTable`, `FAQItem`
  (`<details>`-based)
- Live toggle state via `useState`; no URL params
- Visual baseline for `/pricing`

**Acceptance:**
- All four toggle combinations (USD/VND × Annual/Monthly) render correct
  amounts + bill notes
- Firm tier featured with `MOST POPULAR` badge + oxblood border
- Comparison table renders 5 section rows (Search / Coverage / Workflow /
  Team & security / Support)
- First FAQ item open by default

### PR 3 — Login (two-pane) (~3 hr)
**Scope:**
- Replace `app/login/page.tsx` (currently the simple one-pane form) with
  the two-pane design
- New components: `SpecimenMosaicWall` (3×3 with 2 oxblood-tinted cells),
  `LoginQuote` (big serif quotation + author byline), `SsoButton` (stub),
  `LoginField`, `LoginDivider`
- `body.login-mode` class hides any header/footer present (defensive; the
  `/login` route is outside `(marketing)` and `(app)` groups so doesn't
  inherit either chrome by default)
- Email + password form remains functional (calls existing
  `AuthProvider.login(email, password)`)
- SSO buttons stub: `alert("SSO coming soon — use email + password below")`
- Magic-link button stubbed similarly until backend lands
- Visual baseline for `/login`

**Acceptance:**
- Two-pane layout per handoff (paper-bg left with specimens + quote,
  white right with form)
- Existing password login still works
- `?next=/today` redirect preserved
- Trust strip at bottom (SOC 2 / GDPR / VN Data Residency)

### PR 4 — Coverage (~3 hr)
**Scope:**
- `(marketing)/coverage/page.tsx`
- New components: `StatTile`, `IngestTimeline` (4 rows × 52 weeks heat
  grid, oxblood ramp), `SourceCard` + `primary` variant with 2×2 KV
  footer, `DqCard`
- Stats from `GET /api/v1/stats/overview` for the headline tiles
- New backend endpoint (may need to ship separately): `GET
  /api/v1/stats/ingest-load` returning a 4×52 matrix of row counts —
  cellular for the timeline. Stub with deterministic pseudo-random data
  in PR 4; real endpoint can land before/after
- Timeline tooltips on hover (client component)
- Visual baseline for `/coverage`

**Acceptance:**
- 4-up stats row renders live numbers
- 4 source cards (2 Primary + 2 mirror) with KV footers
- Timeline renders 4×52 cells with the oxblood color ramp; legend at
  top-right; hover tooltip shows week + count
- 3×2 DQ grid renders numbers as designed (don't sanitize 87.6%, 94.1%)

### PR 5 — Docs (~4–5 hr — biggest)
**Scope:**
- Install `@next/mdx` + `remark-gfm`
- Wire `next.config.js` with the MDX plugin
- `(marketing)/docs/layout.tsx` with `DocsSidebar` (sticky 240px, 5 groups,
  17 entries — 8 written + 9 stubs)
- `[[...slug]]/page.tsx` — catch-all route loads MDX by slug; unmatched
  slugs render the "Coming soon" placeholder
- New components: `DocsSidebar`, `DocsArticle` (with eyebrow pill + numbered
  h2 prefixes), `DocsCallout` (3 variants: tip / warn / api), `DocsCodeBlock`
  with language hint top-right + basic syntax highlighting, `DocsTable`
  (mono uppercase column heads), `DocsNavButton` (prev/next), `DocsTOC`
- 8 MDX articles migrated from the prototype HTML: introduction · first
  watchlist · image similarity · REST API · Article 112 guide · Vienna
  codes · Nice classification · Vietnam IP glossary
- 9 stub MDX files for the placeholder entries
- Visual baselines for `/docs` (root) + 1 representative article page

**Acceptance:**
- Sidebar navigates between articles without route changes (or via slug;
  decide during impl — slug-based is cleaner for SEO)
- All 8 written articles render correctly with eyebrow pill, h1, lede,
  TOC, numbered h2 sections, body, callouts, code blocks
- 9 stubs show "Coming soon" placeholder
- Prev/Next nav at article bottom

---

## Static vs dynamic per route

| Route | Strategy | Data |
|---|---|---|
| `/` | SSG + ISR 1h | Stats from `/api/v1/stats/overview` |
| `/pricing` | SSG | None |
| `/coverage` | SSG + ISR 1h | Stats + ingest-load matrix |
| `/docs/<slug>` | SSG per slug | MDX at build time |
| `/login` | SSR / client | URL search params + form submit |
| `(app)/*` | Existing client-rendered with auth | Unchanged |

---

## What we already have that the handoff lists

| Handoff component | Lives in app today |
|---|---|
| `SimilarityRing` | `app/frontend/components/specimen/SimilarityRing.tsx` |
| `Pill`, `ClassChip` | `app/frontend/components/badges.tsx` |
| `Button` (primary/ghost/link, sizes) | `app/frontend/components/ui/button.tsx` |
| `Icon` set | `app/frontend/components/icons.tsx` |
| `Card` | `app/frontend/components/ui/card.tsx` |
| `MarkSpecimen` renderer | `app/frontend/components/specimen/` |
| `SpecimenPlate` | `app/frontend/components/specimen/` |

The marketing-specific Tweaks panel (`design_handoff_tradenet_marketing/marketing/tweaks.jsx`)
is **prototype-only — do not ship**, per the handoff README.

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Token reconciliation (1320→1240) shifts in-app visual baselines | PR 0 re-bakes baselines if the new look is correct; visual diffs are auditable in the PR |
| Existing `/login` users see different UI mid-session | Hard cutover at PR 3 merge. Session cookies survive — only the form layout changes. No client breakage. |
| `(app)/today` becomes the new home for authenticated users | Update any hard-coded `router.push("/")` calls in the app to `router.push("/today")` instead, OR add a redirect from `/` for logged-in users (TBD in PR 1) |
| MDX build time grows | `next-mdx` is incremental; only changed `.mdx` files recompile. 17 articles is well within tolerance. |
| SSO buttons stubbed until auth provider decision | Stub clearly says "coming soon"; password login still works the whole time |
| Magic-link backend not yet built | Stub the button until separate backend PR lands |
| Marketing stats API endpoint for `/coverage` | Land with deterministic pseudo-random demo data in PR 4; replace with real endpoint in a follow-up |

---

## Estimated effort

| PR | Hours | Cumulative |
|---|---|---|
| PR 0 — Token reconciliation | 0.5 | 0.5 |
| PR 1 — Landing | 4 | 4.5 |
| PR 2 — Pricing | 3 | 7.5 |
| PR 3 — Login (two-pane) | 3 | 10.5 |
| PR 4 — Coverage | 3 | 13.5 |
| PR 5 — Docs | 5 | 18.5 |

Plus ~2 hr for visual baseline bakes across the 5 PRs (using the
Docker→artifact-swap workflow we proved out on PR #41).

Total: **~20 hours**, spread across 5 PRs each independently mergeable.

---

## How to resume

1. Read this doc + `README.md` end-to-end
2. Verify the static prototype still works: `python3 -m http.server 8765`
   in `design_handoff_tradenet_marketing/` then open
   `http://localhost:8765/Tradenet%20-%20Marketing.html`
3. Confirm decisions in the "Decisions confirmed" table above still hold
4. Branch off `main` and start PR 0 (token reconciliation)
5. After PR 0 lands, PRs 1–5 can be done in any order, but the listed
   sequence (Landing → Pricing → Login → Coverage → Docs) gives the
   fastest visible-value-per-PR ramp
