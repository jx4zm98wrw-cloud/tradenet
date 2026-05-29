/**
 * Code block with optional language badge in the top-right corner.
 *
 * Server component. No syntax highlighting — the prototype's hand-rolled
 * `<span class="s">`/`<span class="k">` spans can be reproduced in the
 * MDX source if needed (children accepts ReactNode), but most articles
 * just pass a plain string.
 *
 * The `<code>` wrapper for string children keeps semantics correct for
 * screen readers; raw ReactNode children pass through untouched so MDX
 * authors can embed their own highlighted spans.
 */
import type { ReactNode } from "react";

type Props = {
  /** Optional badge in the top-right of the block ("cURL", "JSON", "DSL"). */
  lang?: string;
  /** String → wrapped in `<code>`; ReactNode → rendered as-is. */
  children: ReactNode;
};

export function DocsCode({ lang, children }: Props) {
  return (
    <pre className="docs-code">
      {lang ? <span className="docs-code-lang">{lang}</span> : null}
      {typeof children === "string" ? <code>{children}</code> : children}
    </pre>
  );
}
