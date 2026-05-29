/**
 * Inline callout box (Tip / Recommendation / Important / Pro tip / etc.).
 *
 * Server component. The prototype uses a single visual variant — left
 * border in stamp red, paper-2 background — with the heading rendered
 * as an uppercase mono caption above the body. Per-callout flavor is
 * encoded purely in `heading` text (no variant prop needed).
 */
import type { ReactNode } from "react";

type Props = {
  heading: string;
  children: ReactNode;
};

export function DocsCallout({ heading, children }: Props) {
  return (
    <div className="docs-callout">
      <strong>{heading}</strong>
      {children}
    </div>
  );
}
