/**
 * Typed sidebar config for the docs route group.
 *
 * Single source of truth for: sidebar order, slugs, "written vs stub"
 * status, per-article eyebrow text, and prev/next navigation. The
 * `[slug]/page.tsx` route lazy-imports MDX based on `written: true` here;
 * `DocsSidebar` reads `DOCS_GROUPS` to render the rail; `getNeighbors`
 * powers the prev/next buttons in `DocsArticleShell`.
 *
 * Source of truth: docs section of
 * `design_handoff_tradenet_marketing/Tradenet - Marketing.html` lines
 * 887-1645.
 */

export type DocsNavEntry = {
  /** URL slug — also the basename of the MDX file under `_articles/`. */
  slug: string;
  /** Sidebar label + page heading (when stub). */
  title: string;
  /** Trailing sidebar badge — reading time, "Ent", or "↗". */
  num?: string;
  /** True → MDX article exists; false → render `<DocsComingSoon>`. */
  written: boolean;
  /** Sidebar group heading. */
  group: string;
  /** Eyebrow pill rendered by `DocsArticleShell`. */
  eyebrow?: string;
};

export const DOCS_GROUPS: ReadonlyArray<{
  heading: string;
  entries: ReadonlyArray<DocsNavEntry>;
}> = [
  {
    heading: "Getting started",
    entries: [
      {
        slug: "getting-started",
        title: "Introduction",
        num: "5 min",
        written: true,
        group: "Getting started",
        eyebrow: "Getting started · 5 min read",
      },
      {
        slug: "first-watchlist",
        title: "Your first watchlist",
        num: "3 min",
        written: true,
        group: "Getting started",
        eyebrow: "Getting started · 3 min read",
      },
      {
        slug: "team-invite",
        title: "Inviting your team",
        num: "2 min",
        written: false,
        group: "Getting started",
      },
    ],
  },
  {
    heading: "Searching",
    entries: [
      {
        slug: "text-search",
        title: "Text & operators",
        written: false,
        group: "Searching",
      },
      {
        slug: "phonetic-search",
        title: "Phonetic / fuzzy",
        written: false,
        group: "Searching",
      },
      {
        slug: "image-search",
        title: "Image similarity",
        written: true,
        group: "Searching",
        eyebrow: "Searching · 4 min read",
      },
      {
        slug: "vienna-search",
        title: "Vienna codes",
        written: false,
        group: "Searching",
      },
    ],
  },
  {
    heading: "Workflow",
    entries: [
      {
        slug: "watchlists",
        title: "Watchlists",
        written: false,
        group: "Workflow",
      },
      {
        slug: "opposition",
        title: "Opposition workflow",
        written: false,
        group: "Workflow",
      },
      {
        slug: "reports",
        title: "Client reports",
        written: false,
        group: "Workflow",
      },
      {
        slug: "article-112",
        title: "Article 112 guide",
        num: "↗",
        written: true,
        group: "Workflow",
        eyebrow: "Reference · 6 min read",
      },
    ],
  },
  {
    heading: "API",
    entries: [
      {
        slug: "api",
        title: "REST reference",
        num: "Ent",
        written: true,
        group: "API",
        eyebrow: "API · Enterprise only",
      },
      {
        slug: "webhooks",
        title: "Webhooks",
        num: "Ent",
        written: false,
        group: "API",
      },
      {
        slug: "sso",
        title: "SSO setup",
        num: "Ent",
        written: false,
        group: "API",
      },
    ],
  },
  {
    heading: "Reference",
    entries: [
      {
        slug: "vienna-ref",
        title: "Vienna 5.1 codes",
        written: true,
        group: "Reference",
        eyebrow: "Reference · Vienna 5.1",
      },
      {
        slug: "nice-ref",
        title: "Nice classification",
        written: true,
        group: "Reference",
        eyebrow: "Reference · Nice 12-2026",
      },
      {
        slug: "glossary",
        title: "Vietnam IP glossary",
        written: true,
        group: "Reference",
        eyebrow: "Reference · Glossary",
      },
    ],
  },
];

/** Flat list of every slug for `generateStaticParams`. */
export const ALL_SLUGS: ReadonlyArray<string> = DOCS_GROUPS.flatMap((g) =>
  g.entries.map((e) => e.slug),
);

/** Slugs that map to a real MDX article (not a stub). */
export const WRITTEN_SLUGS: ReadonlyArray<string> = DOCS_GROUPS.flatMap((g) =>
  g.entries.filter((e) => e.written).map((e) => e.slug),
);

/** Flat list of every entry (preserves DOCS_GROUPS order). */
const FLAT_ENTRIES: ReadonlyArray<DocsNavEntry> = DOCS_GROUPS.flatMap(
  (g) => g.entries,
);

export function findEntry(slug: string): DocsNavEntry | undefined {
  return FLAT_ENTRIES.find((e) => e.slug === slug);
}

/**
 * Linear prev/next navigation across the entire flat docs sequence —
 * groups are concatenated in `DOCS_GROUPS` order. Returns `undefined`
 * for the ends.
 */
export function getNeighbors(slug: string): {
  prev?: DocsNavEntry;
  next?: DocsNavEntry;
} {
  const idx = FLAT_ENTRIES.findIndex((e) => e.slug === slug);
  if (idx === -1) return {};
  return {
    prev: idx > 0 ? FLAT_ENTRIES[idx - 1] : undefined,
    next: idx < FLAT_ENTRIES.length - 1 ? FLAT_ENTRIES[idx + 1] : undefined,
  };
}
