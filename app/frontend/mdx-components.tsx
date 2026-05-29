/**
 * Global MDX component map — Next.js 15 looks for this file at the project
 * root and applies the returned map to every compiled MDX module.
 *
 * Tradenet docs articles are written as pure body MDX (no eyebrow/h1/lede
 * — those come from `DocsArticleShell` in `[slug]/page.tsx`). The body
 * uses raw HTML/MDX paragraphs and bullet lists; we map those plain
 * elements to the prototype's docs-specific classes here so individual
 * MDX files don't need to repeat the className everywhere.
 *
 * Anything richer (callouts, tables, code blocks, TOC) is imported from
 * `components/marketing/docs/*` directly inside each .mdx file.
 */
import type { MDXComponents } from "mdx/types";

export function useMDXComponents(components: MDXComponents): MDXComponents {
  return {
    p: ({ children }) => <p className="docs-p">{children}</p>,
    ul: ({ children }) => <ul className="docs-list">{children}</ul>,
    ...components,
  };
}
