"use client";

/**
 * Sticky left sidebar for the docs route group.
 *
 * Client component because it uses `usePathname()` to highlight the
 * active article. All other docs chrome (article shell, callouts, code
 * blocks, tables, TOC) is server-rendered.
 *
 * Renders the 5 groups from `DOCS_GROUPS` (verbatim from the prototype).
 * Each link is a Next `<Link>` so navigation is client-side; the
 * surrounding `[slug]/page.tsx` is a server component that streams per
 * slug.
 */
import Link from "next/link";
import { usePathname } from "next/navigation";
import { DOCS_GROUPS } from "../../../app/(marketing)/_content/docsNav";

export function DocsSidebar() {
  const pathname = usePathname();
  return (
    <aside className="docs-sidebar">
      {DOCS_GROUPS.map((group) => (
        <div key={group.heading} className="docs-sb-group">
          <h4>{group.heading}</h4>
          <ul>
            {group.entries.map((entry) => {
              const href = `/docs/${entry.slug}`;
              const active = pathname === href;
              return (
                <li key={entry.slug}>
                  <Link
                    href={href}
                    className={
                      active ? "docs-sb-link active" : "docs-sb-link"
                    }
                  >
                    {entry.title}
                    {entry.num ? (
                      <span className="docs-sb-num">{entry.num}</span>
                    ) : null}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </aside>
  );
}
