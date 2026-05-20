"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { Icon } from "./icons";
import { Kbd } from "./ui/kbd";
import { api, type Trademark } from "@/lib/api";

/* ----- Context: any component can call useCmdK().open() to summon the palette ----- */

type CmdKCtx = { open: () => void; close: () => void; isOpen: boolean };
const Ctx = React.createContext<CmdKCtx>({ open: () => {}, close: () => {}, isOpen: false });
export const useCmdK = () => React.useContext(Ctx);

const RECENT_KEY = "tm:recent-searches";
type Recent = { q: string; scope?: string; when: string };

function readRecent(): Recent[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
  } catch {
    return [];
  }
}
export function recordRecent(r: Omit<Recent, "when">) {
  if (typeof window === "undefined") return;
  const list = readRecent();
  const next = [{ ...r, when: new Date().toISOString() }, ...list.filter((x) => x.q !== r.q)].slice(0, 8);
  localStorage.setItem(RECENT_KEY, JSON.stringify(next));
}

export function CmdKProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setOpen] = React.useState(false);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen(true);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const ctx = React.useMemo<CmdKCtx>(
    () => ({ open: () => setOpen(true), close: () => setOpen(false), isOpen }),
    [isOpen]
  );

  return (
    <Ctx.Provider value={ctx}>
      {children}
      <CmdKPalette open={isOpen} onClose={() => setOpen(false)} />
    </Ctx.Provider>
  );
}

/* ----- Overlay ----- */

type Item = {
  id: string;
  icon: React.ReactNode;
  label: string;
  sub?: string;
  hint?: string;
  onSelect: () => void;
};
type Group = { label: string; items: Item[] };

function CmdKPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const router = useRouter();
  const [q, setQ] = React.useState("");
  const [marks, setMarks] = React.useState<Trademark[]>([]);
  const [active, setActive] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);

  // Focus input on open; reset state on close.
  React.useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 30);
    } else {
      setQ("");
      setActive(0);
      setMarks([]);
    }
  }, [open]);

  // Live trademark search (debounced).
  React.useEffect(() => {
    if (!open) return;
    const t = setTimeout(() => {
      if (!q.trim()) return setMarks([]);
      api.searchTrademarks({ q: q.trim(), limit: 6 }).then((r) => setMarks(r.items)).catch(() => {});
    }, 150);
    return () => clearTimeout(t);
  }, [q, open]);

  const recent = React.useMemo(() => readRecent(), [open]);

  const groups = React.useMemo<Group[]>(() => {
    const ql = q.trim().toLowerCase();
    const matches = (s: string) => !ql || s.toLowerCase().includes(ql);
    const actions: Item[] = [
      {
        id: "act-new-search",
        icon: <Icon.Search className="w-3.5 h-3.5" />,
        label: "Run new search",
        hint: "↵",
        onSelect: () => { router.push("/search"); onClose(); },
      },
      {
        id: "act-image-search",
        icon: <Icon.Image className="w-3.5 h-3.5" />,
        label: "Search by image upload",
        hint: "⌘I",
        onSelect: () => { router.push("/search?mode=image"); onClose(); },
      },
      {
        id: "act-new-watch",
        icon: <Icon.Folder className="w-3.5 h-3.5" />,
        label: "Create watchlist",
        hint: "⌘N",
        onSelect: () => { router.push("/watchlists"); onClose(); },
      },
      {
        id: "act-report",
        icon: <Icon.Download className="w-3.5 h-3.5" />,
        label: "Generate weekly report",
        onSelect: () => { onClose(); },
      },
    ].filter((a) => matches(a.label));

    const tmItems: Item[] = marks.map((t) => ({
      id: `tm-${t.id}`,
      icon: <span className="font-sans font-bold text-[11px] text-stamp tracking-wider">{(t.mark_sample ?? t.applicant_name ?? "").slice(0, 2).toUpperCase()}</span>,
      label: t.mark_sample ?? t.applicant_name ?? "—",
      sub: t.applicant_name ?? undefined,
      hint: t.application_number ?? t.certificate_number ?? t.madrid_number ?? undefined,
      onSelect: () => { router.push(`/marks/${t.id}`); onClose(); },
    }));

    const recentItems: Item[] = recent.filter((r) => matches(r.q)).map((r, i) => ({
      id: `rec-${i}`,
      icon: <Icon.Clock className="w-3.5 h-3.5" />,
      label: r.q,
      sub: r.scope,
      hint: timeAgo(r.when),
      onSelect: () => { router.push(`/search?q=${encodeURIComponent(r.q)}`); onClose(); },
    }));

    return [
      { label: "Actions",    items: actions },
      { label: "Trademarks", items: tmItems },
      { label: "Recent",     items: recentItems },
    ].filter((g) => g.items.length > 0);
  }, [q, marks, recent, router, onClose]);

  // Flatten for keyboard nav.
  const flat = React.useMemo(() => groups.flatMap((g) => g.items), [groups]);
  React.useEffect(() => setActive(0), [q, marks.length]);

  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((a) => Math.min(a + 1, flat.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((a) => Math.max(a - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        flat[active]?.onSelect();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, flat, active]);

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-sm grid"
      style={{ alignItems: "flex-start", justifyItems: "center", paddingTop: "14vh" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-surface border border-line shadow-md rounded-lg w-[640px] max-w-[92vw] overflow-hidden"
        role="dialog" aria-label="Command palette"
      >
        <div className="flex items-center gap-2 px-3 py-2.5 border-b border-line">
          <Icon.Search className="w-4 h-4 text-mute" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search marks, applicants, agents, app numbers…"
            className="flex-1 outline-none bg-transparent text-sm text-ink placeholder:text-mute"
          />
          <Kbd>esc</Kbd>
        </div>

        <div className="max-h-[60vh] overflow-y-auto">
          {groups.length === 0 ? (
            <div className="px-4 py-6 text-mute text-sm">No matches.</div>
          ) : (
            groups.map((g, gi) => {
              const offset = groups.slice(0, gi).reduce((n, x) => n + x.items.length, 0);
              return (
                <div key={g.label} className="py-1">
                  <div className="px-3 pt-2 pb-1 text-[10.5px] font-semibold tracking-wider uppercase text-mute">
                    {g.label}
                  </div>
                  {g.items.map((it, i) => {
                    const idx = offset + i;
                    const isActive = idx === active;
                    return (
                      <button
                        key={it.id}
                        type="button"
                        onMouseEnter={() => setActive(idx)}
                        onClick={it.onSelect}
                        className={`w-full text-left flex items-center gap-3 px-3 py-2 text-sm transition ${
                          isActive ? "bg-stamp-2 text-stamp" : "text-ink hover:bg-paper-2"
                        }`}
                      >
                        <span className={`w-6 h-6 rounded grid place-items-center shrink-0 ${isActive ? "bg-stamp/10" : "bg-paper-2"}`}>
                          {it.icon}
                        </span>
                        <span className="flex-1 min-w-0">
                          <span className="block truncate">{it.label}</span>
                          {it.sub && <span className="block truncate text-xs text-mute">{it.sub}</span>}
                        </span>
                        {it.hint && <Kbd>{it.hint}</Kbd>}
                      </button>
                    );
                  })}
                </div>
              );
            })
          )}
        </div>

        <div className="px-3 py-2 border-t border-line flex items-center justify-between text-[11px] text-mute">
          <span className="flex items-center gap-1.5"><Kbd>↑</Kbd><Kbd>↓</Kbd> navigate</span>
          <span className="flex items-center gap-1.5"><Kbd>↵</Kbd> open</span>
          <span>Phonetic, fuzzy, image-similarity all supported</span>
        </div>
      </div>
    </div>
  );
}

function timeAgo(iso: string): string {
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const m = Math.round(diff / 60_000);
  if (m < 1) return "now";
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.round(h / 24)}d ago`;
}
