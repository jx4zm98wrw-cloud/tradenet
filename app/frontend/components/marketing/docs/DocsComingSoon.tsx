/**
 * Placeholder shown for any sidebar entry where `written: false` in
 * `docsNav.ts` — 9 stub slugs as of PR 5 (team-invite, text-search,
 * phonetic-search, vienna-search, watchlists, opposition, reports,
 * webhooks, sso).
 *
 * Server component. Friendly, on-brand, points the reader at the
 * Introduction article so they don't bounce.
 */
import Link from "next/link";
import { DocsCallout } from "./DocsCallout";

type Props = {
  title: string;
};

export function DocsComingSoon({ title }: Props) {
  return (
    <article className="docs-doc">
      <span className="docs-eyebrow">Documentation</span>
      <h1 className="docs-h1">{title}</h1>
      <p className="docs-lede">
        This article is coming soon. Check back next month — in the meantime,
        the Introduction and Getting started guides cover most of what you need
        to start using Tradenet productively.
      </p>
      <DocsCallout heading="Need help now?">
        Email{" "}
        <a href="mailto:support@tradenet.vn" style={{ color: "var(--stamp)" }}>
          support@tradenet.vn
        </a>{" "}
        — we typically respond within 2 hours during business hours (GMT+7).
      </DocsCallout>
      <div className="docs-footer">
        <Link
          href="/docs/getting-started"
          className="docs-nav-btn"
          style={{ display: "inline-flex", marginTop: 16 }}
        >
          <span className="docs-nav-btn-label">← Back</span>
          <span className="docs-nav-btn-title">Introduction</span>
        </Link>
        <span />
      </div>
    </article>
  );
}
