"use client";

/**
 * Top nav for the public marketing site. Renders the same sticky
 * blur-paper bar from the prototype (`.mk-nav`), but routes via Next's
 * Link instead of the prototype's hash router.
 *
 * Active-tab matching is path-based via `usePathname()`. For PR 1, only
 * `/` (Product) resolves; Pricing/Coverage/Docs links 404 until their
 * respective PRs land — that's intentional per the implementation plan.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";

type Tab = { href: string; label: string; match: (p: string) => boolean };

const TABS: Tab[] = [
  { href: "/", label: "Product", match: (p) => p === "/" },
  { href: "/pricing", label: "Pricing", match: (p) => p.startsWith("/pricing") },
  { href: "/coverage", label: "Coverage", match: (p) => p.startsWith("/coverage") },
  { href: "/docs", label: "Docs", match: (p) => p.startsWith("/docs") },
];

export function MarketingNav() {
  const pathname = usePathname();
  return (
    <header className="mk-nav">
      <div className="container mk-nav-inner">
        <Link href="/" className="mk-brand">
          <span className="mk-brand-mark" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
              <path d="M5 4 H19 V8 L12 9.5 L5 8 Z" fill="white" opacity="0.95" />
              <path d="M11 9 H13 V20 H11 Z" fill="white" opacity="0.95" />
            </svg>
          </span>
          <span className="mk-brand-name">
            Tradenet<span className="mk-brand-tld">.vn</span>
          </span>
        </Link>
        <nav className="mk-nav-links">
          {TABS.map((t) => {
            const active = t.match(pathname);
            return (
              <Link
                key={t.href}
                href={t.href}
                className={active ? "active" : undefined}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
        <div className="mk-nav-cta">
          <Link href="/login" className="btn btn-link">
            Sign in
          </Link>
          <Link href="/login" className="btn btn-primary">
            Start free trial
          </Link>
        </div>
      </div>
    </header>
  );
}
