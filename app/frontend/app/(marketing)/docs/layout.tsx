/**
 * Docs route layout — applies to `/docs` and every `/docs/<slug>`.
 *
 * Renders the 2-col `.docs-shell` grid: sticky `DocsSidebar` on the left,
 * the per-slug article on the right. The actual article header (eyebrow,
 * h1, lede, TOC, footer) is rendered by `[slug]/page.tsx` via
 * `DocsArticleShell` — this layout is just the page chrome.
 *
 * Server component. Sidebar internally marks itself client (needs
 * `usePathname`).
 */
import { DocsSidebar } from "@/components/marketing/docs/DocsSidebar";

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <section className="view">
      <div className="container docs-shell">
        <DocsSidebar />
        <main className="docs-main">{children}</main>
      </div>
    </section>
  );
}
