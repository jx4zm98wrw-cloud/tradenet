"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "./icons";
import { IconButton } from "./ui";
import { Kbd } from "./ui/kbd";
import { useCmdK } from "./cmdk";

const TABS = [
  { href: "/", label: "Today", match: (p: string) => p === "/" || p === "/today" },
  { href: "/search", label: "Search", match: (p: string) => p.startsWith("/search") || p.startsWith("/marks") || p.startsWith("/compare") || p.startsWith("/trademarks") },
  { href: "/watchlists", label: "Watchlists", match: (p: string) => p.startsWith("/watchlists") },
  { href: "/admin/gazettes", label: "Gazettes", match: (p: string) => p.startsWith("/admin") || p.startsWith("/gazettes") },
];

export function TopNav() {
  const pathname = usePathname();
  const { open } = useCmdK();

  return (
    <header className="sticky top-0 z-40 border-b border-line bg-paper/95 backdrop-blur-md">
      <div className="max-w-container mx-auto px-6 h-14 flex items-center justify-between gap-6">
        <div className="flex items-center gap-7">
          <Link href="/" className="flex items-center gap-2.5 no-underline text-ink">
            <Logo />
            <div className="flex flex-col leading-[1.1]">
              <span className="text-[14px] font-bold tracking-tight">Tradenet</span>
              <span className="text-[10px] text-mute font-mono">VN · Gazette</span>
            </div>
          </Link>
          <nav className="flex items-center gap-0.5">
            {TABS.map((t) => {
              const active = t.match(pathname);
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  className={`px-3 py-1.5 rounded-md text-[13.5px] font-medium transition ${
                    active
                      ? "bg-paper-3 text-ink shadow-[inset_0_-2px_0_var(--stamp)]"
                      : "text-ink-2 hover:bg-paper-2 hover:text-ink"
                  }`}
                >
                  {t.label}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Central nav-search that opens Cmd-K */}
        <button
          type="button"
          onClick={open}
          className="flex-1 max-w-[420px] min-w-[220px] h-[34px] px-3 bg-paper-2 border border-line rounded-lg flex items-center gap-2 text-mute text-[13px] hover:bg-surface hover:border-line-strong transition overflow-hidden"
        >
          <Icon.Search className="w-3.5 h-3.5 shrink-0" />
          <span className="flex-1 min-w-0 overflow-hidden whitespace-nowrap text-ellipsis text-left">
            Search marks, applicants, classes…
          </span>
          <Kbd className="ml-auto">⌘K</Kbd>
        </button>

        <div className="flex items-center gap-2.5">
          <IconButton title="Alerts" hasDot>
            <Icon.Bell className="w-4 h-4" />
          </IconButton>
          <IconButton title="Help">
            <Icon.Help className="w-4 h-4" />
          </IconButton>
          <div className="w-[30px] h-[30px] rounded-full bg-paper-3 border border-line grid place-items-center text-[11px] font-semibold text-ink">
            FL
          </div>
        </div>
      </div>
    </header>
  );
}

function Logo() {
  return (
    <div
      className="w-7 h-7 rounded-md bg-stamp grid place-items-center text-white"
      style={{ boxShadow: "inset 0 0 0 1px var(--stamp-deep)" }}
    >
      <Icon.Brand className="w-4 h-4" />
    </div>
  );
}
