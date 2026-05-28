"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import * as React from "react";
import { useAuth } from "./auth-context";
import { Icon } from "./icons";
import { IconButton } from "./ui";
import { Kbd } from "./ui/kbd";
import { useCmdK } from "./cmdk";

const TABS = [
  // `/` now serves the public marketing landing — the in-app home moved
  // to `/today` when we split into (marketing) / (app) Route Groups.
  { href: "/today", label: "Today", match: (p: string) => p === "/today" },
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
          {/* Logo links to the in-app home (`/today`), not `/` — `/` is the
              public marketing landing. The marketing site has its own
              MarketingNav with a logo link to `/`. */}
          <Link href="/today" className="flex items-center gap-2.5 no-underline text-ink">
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
          <UserMenu />
        </div>
      </div>
    </header>
  );
}

function UserMenu() {
  const { user, logout, loading } = useAuth();
  const [open, setOpen] = React.useState(false);
  const wrapRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("click", onClick);
    return () => window.removeEventListener("click", onClick);
  }, [open]);

  if (loading || !user) {
    return (
      <div className="w-[30px] h-[30px] rounded-full bg-paper-2 border border-line animate-pulse" />
    );
  }

  // Initials from the user's name (e.g. "Francis Luong" → "FL")
  const initials = user.name
    .split(/\s+/)
    .filter(Boolean)
    .map((p) => p[0]!.toUpperCase())
    .slice(0, 2)
    .join("") || user.email[0]!.toUpperCase();

  return (
    <div className="relative" ref={wrapRef}>
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-[30px] h-[30px] rounded-full bg-paper-3 border border-line grid place-items-center text-[11px] font-semibold text-ink hover:border-line-strong"
        title={`${user.name} (${user.email})`}
      >
        {initials}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-56 bg-surface border border-line rounded shadow-md z-50 overflow-hidden">
          <div className="px-3 py-2 border-b border-line">
            <div className="text-[12.5px] font-semibold truncate">{user.name}</div>
            <div className="text-[11px] text-mute truncate">{user.email}</div>
            <div className="text-[10px] uppercase tracking-wider text-mute font-mono mt-1">
              {user.role}
            </div>
          </div>
          <button
            onClick={() => {
              setOpen(false);
              logout();
            }}
            className="w-full text-left text-[12.5px] px-3 py-2 hover:bg-paper-2 text-ink-2"
          >
            Sign out
          </button>
        </div>
      )}
    </div>
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
