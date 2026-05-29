/**
 * Wraps an MDX article body with the eyebrow pill, h1, lede, and
 * prev/next footer. Used by `[slug]/page.tsx` for every written article.
 *
 * Server component. The MDX body itself is passed as `children`; the
 * shell decides the chrome around it so individual .mdx files stay
 * pure body content.
 *
 * Prev/next are looked up from `docsNav.ts` so adding a new article only
 * touches that config + the MDX file.
 */
import type { ReactNode } from "react";
import { getNeighbors } from "../../../app/(marketing)/_content/docsNav";
import { DocsNavBtn } from "./DocsNavBtn";

type Props = {
  slug: string;
  eyebrow: string;
  h1: string;
  lede: string;
  children: ReactNode;
};

export function DocsArticleShell({ slug, eyebrow, h1, lede, children }: Props) {
  const { prev, next } = getNeighbors(slug);
  return (
    <article className="docs-doc">
      <span className="docs-eyebrow">{eyebrow}</span>
      <h1 className="docs-h1">{h1}</h1>
      <p className="docs-lede">{lede}</p>
      {children}
      <div className="docs-footer">
        {prev ? (
          <DocsNavBtn
            direction="prev"
            title={prev.title}
            href={`/docs/${prev.slug}`}
          />
        ) : (
          <span />
        )}
        {next ? (
          <DocsNavBtn
            direction="next"
            title={next.title}
            href={`/docs/${next.slug}`}
          />
        ) : (
          <span />
        )}
      </div>
    </article>
  );
}
