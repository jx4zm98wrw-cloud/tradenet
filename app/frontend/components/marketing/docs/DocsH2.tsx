/**
 * Section heading for docs articles — numbered `01`, `02`, ... prefix +
 * scroll target anchor + the rest of the heading text.
 *
 * Why a component instead of inline JSX in MDX:
 *
 *   MDX auto-wraps loose text inside multi-line JSX with a `<p>` tag.
 *   The pattern from the prototype HTML:
 *
 *     <h2 className="docs-h2" id="what">
 *       <span className="docs-h2-num">01</span> What Tradenet does
 *     </h2>
 *
 *   compiles to:
 *
 *     <h2><p><span>01</span> What Tradenet does</p></h2>
 *
 *   …which is invalid HTML (no `<p>` inside `<h2>`), causes the browser
 *   to auto-close the `<h2>` mid-stream, and triggers a React hydration
 *   mismatch in dev because client-DOM and server-string disagree.
 *
 *   This component renders the heading single-line at the JSX level so
 *   the auto-paragraph-wrap never fires. Writers in MDX just say:
 *
 *     <DocsH2 num="01" id="what">What Tradenet does</DocsH2>
 *
 *   …and get the same visual result with no hydration warnings.
 */
import * as React from "react";

type DocsH2Props = {
  /** Two-digit section number, e.g. "01", "02". Rendered in oxblood mono. */
  num: string;
  /** Anchor target id — `#id` deep-links to the heading. */
  id: string;
  children: React.ReactNode;
};

export function DocsH2({ num, id, children }: DocsH2Props) {
  return (
    <h2 className="docs-h2" id={id}>
      <span className="docs-h2-num">{num}</span> {children}
    </h2>
  );
}
