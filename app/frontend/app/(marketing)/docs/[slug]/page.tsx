/**
 * Per-slug docs page (`/docs/<slug>`).
 *
 * Server component. Strategy:
 *   1. `generateStaticParams` emits all 17 known slugs so each is
 *      pre-rendered at build time (SSG).
 *   2. The slug is looked up in `docsNav.ts`. Unknown slug → `notFound()`.
 *   3. `written: true` → render the matching MDX article body inside
 *      `DocsArticleShell` (which adds eyebrow + h1 + lede + prev/next).
 *      The h1/lede are hard-coded in the article body via per-slug
 *      tuples below so the shell can render them above the MDX.
 *   4. `written: false` → render `<DocsComingSoon>` with the entry title.
 *
 * MDX imports are explicit (not dynamic-string) so the bundler can
 * tree-shake unused articles per route and so TypeScript can verify
 * each path at build time.
 */
import type { MDXProps } from "mdx/types";
import { notFound } from "next/navigation";
import {
  ALL_SLUGS,
  WRITTEN_SLUGS,
  findEntry,
} from "../../_content/docsNav";
import { DocsArticleShell } from "@/components/marketing/docs/DocsArticleShell";
import { DocsComingSoon } from "@/components/marketing/docs/DocsComingSoon";

// Static MDX imports for every written article. Keeping these as
// top-level imports (vs. dynamic) lets Next pre-render each slug at
// build time without an async tree-walk per request.
import GettingStarted from "../_articles/getting-started.mdx";
import FirstWatchlist from "../_articles/first-watchlist.mdx";
import ImageSearch from "../_articles/image-search.mdx";
import Api from "../_articles/api.mdx";
import Article112 from "../_articles/article-112.mdx";
import ViennaRef from "../_articles/vienna-ref.mdx";
import NiceRef from "../_articles/nice-ref.mdx";
import Glossary from "../_articles/glossary.mdx";

/** The shape of every default-exported MDX component. */
type MDXComponent = (props: MDXProps) => React.JSX.Element;

/**
 * Per-slug header copy. The MDX file owns the body; the shell owns the
 * h1 + lede. These are mirrored verbatim from the prototype.
 */
const HEADERS: Record<
  string,
  { h1: string; lede: string; Component: MDXComponent }
> = {
  "getting-started": {
    h1: "Introduction to Tradenet",
    lede:
      "Tradenet is a search-and-watch tool for the Vietnamese trademark gazette. This guide walks through what the product does, how the four main surfaces fit together, and how to set up your first watchlist in under five minutes.",
    Component: GettingStarted,
  },
  "first-watchlist": {
    h1: "Your first watchlist",
    lede:
      "Watchlists are saved queries that re-run automatically against every new gazette issue. Setting one up is the single highest-value action in Tradenet.",
    Component: FirstWatchlist,
  },
  "image-search": {
    h1: "Image similarity search",
    lede:
      "Image search is the fastest way to find visual lookalikes — including marks that read differently but look the same. It works on uploaded PNGs, JPGs, or PDFs.",
    Component: ImageSearch,
  },
  api: {
    h1: "REST API reference",
    lede:
      "Tradenet exposes every action in the UI as a REST endpoint. JSON in, JSON out, HTTP Bearer auth. Webhooks available for async events (watchlist hits, status changes).",
    Component: Api,
  },
  "article-112": {
    h1: "Article 112 — Opposition rules in Vietnam",
    lede:
      "A practical guide to opposition windows under Vietnamese IP law. Not legal advice — always confirm with qualified counsel, especially for Madrid-protocol designations and edge cases.",
    Component: Article112,
  },
  "vienna-ref": {
    h1: "Vienna classification — figurative codes",
    lede:
      "The Vienna Classification is the international standard for classifying the figurative elements of trademarks. Tradenet supports search by Vienna code and auto-classifies uploaded images against the current 5.1 edition.",
    Component: ViennaRef,
  },
  "nice-ref": {
    h1: "Nice classification — goods & services",
    lede:
      "The Nice Classification is a 45-class system describing the goods and services a trademark covers. A mark registered for “Class 5” (pharmaceuticals) gives you no protection in “Class 30” (foodstuffs) — even for the same wordmark. Getting the class right is the single most common conflict pivot.",
    Component: NiceRef,
  },
  glossary: {
    h1: "IP VIETNAM glossary & INID codes",
    lede:
      "The vocabulary of the Vietnamese trademark system — Vietnamese terminology, IP VIETNAM's specific conventions, and the WIPO INID numerical field codes that appear in every gazette entry. Bookmark this page.",
    Component: Glossary,
  },
};

/**
 * SSG: pre-render every slug we know about (17 total — 8 written + 9
 * stubs). Unknown slugs fall through to `notFound()` and Next renders
 * the standard 404.
 */
export function generateStaticParams() {
  return ALL_SLUGS.map((slug) => ({ slug }));
}

type Params = { slug: string };

export default async function DocsSlugPage({
  params,
}: {
  params: Promise<Params>;
}) {
  const { slug } = await params;
  const entry = findEntry(slug);
  if (!entry) {
    notFound();
  }

  // Stub: render the friendly placeholder.
  if (!entry.written) {
    return <DocsComingSoon title={entry.title} />;
  }

  // Written: hand the MDX body to the shell.
  const header = HEADERS[slug];
  if (!header) {
    // `written: true` in docsNav but no header tuple → developer error.
    // Surfaces as 404 in prod rather than crashing the build.
    notFound();
  }
  const { Component } = header;
  return (
    <DocsArticleShell
      slug={slug}
      eyebrow={entry.eyebrow ?? "Documentation"}
      h1={header.h1}
      lede={header.lede}
    >
      <Component />
    </DocsArticleShell>
  );
}

// Sanity check at build time: every `written: true` slug must have a
// header tuple. If this ever fails, TypeScript surfaces it before
// runtime.
const _written: ReadonlyArray<string> = WRITTEN_SLUGS;
void _written;
