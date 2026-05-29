/**
 * Prev / next button at the bottom of every docs article.
 *
 * Server component. The `next` variant right-aligns its text; both
 * variants use the same outer chrome (.docs-nav-btn) plus a label/title
 * pair styled by `marketing.css`.
 */
import Link from "next/link";

type Props = {
  direction: "prev" | "next";
  title: string;
  href: string;
};

export function DocsNavBtn({ direction, title, href }: Props) {
  const className = direction === "next" ? "docs-nav-btn next" : "docs-nav-btn";
  const label = direction === "next" ? "Next →" : "← Previous";
  return (
    <Link href={href} className={className}>
      <span className="docs-nav-btn-label">{label}</span>
      <span className="docs-nav-btn-title">{title}</span>
    </Link>
  );
}
