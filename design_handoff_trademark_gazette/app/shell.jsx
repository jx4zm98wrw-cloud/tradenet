// App shell: top nav, sub-nav, cmd-k palette, route container
const { useState, useEffect, useRef, useMemo, useCallback } = React;

function Logo() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <div style={{
        width: 28, height: 28, borderRadius: 5,
        background: "var(--stamp)", display: "grid", placeItems: "center",
        boxShadow: "inset 0 0 0 1px oklch(0.30 0.08 28 / 0.4)",
      }}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M5 4 H19 V8 L12 9.5 L5 8 Z" fill="white" opacity="0.95"/>
          <path d="M11 9 H13 V20 H11 Z" fill="white" opacity="0.95"/>
        </svg>
      </div>
      <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
        <span style={{ fontWeight: 700, fontSize: 14, letterSpacing: "-0.01em" }}>Tradenet</span>
        <span style={{ fontSize: 10, color: "var(--mute)", fontFamily: '"JetBrains Mono", monospace' }}>VN · Gazette</span>
      </div>
    </div>
  );
}

function TopNav({ route, onNav, onOpenCmdK }) {
  const tabs = [
    { id: "dashboard", label: "Today" },
    { id: "search",    label: "Search" },
    { id: "watchlists",label: "Watchlists" },
    { id: "gazettes",  label: "Gazettes" },
  ];
  return (
    <header className="top-nav">
      <div className="container nav-inner">
        <div style={{ display: "flex", alignItems: "center", gap: 28 }}>
          <a href="#" onClick={e => { e.preventDefault(); onNav("dashboard"); }} style={{ textDecoration: "none", color: "inherit" }}>
            <Logo/>
          </a>
          <nav style={{ display: "flex", gap: 2 }}>
            {tabs.map(t => (
              <button key={t.id}
                onClick={() => onNav(t.id)}
                className={"nav-tab" + (route === t.id ? " active" : "")}
              >{t.label}</button>
            ))}
          </nav>
        </div>

        <div className="nav-search" onClick={onOpenCmdK}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <span>Search marks, applicants, classes…</span>
          <kbd>⌘K</kbd>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button className="icon-btn" title="Alerts">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10 21a2 2 0 0 0 4 0"/></svg>
            <span className="badge-dot"></span>
          </button>
          <button className="icon-btn" title="Help">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><path d="M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.8.4-1 .9-1 1.7M12 17h.01"/></svg>
          </button>
          <div className="avatar">{window.CURRENT_USER.initials}</div>
        </div>
      </div>
    </header>
  );
}

function CmdK({ open, onClose, onNav }) {
  const [q, setQ] = useState("");
  const inputRef = useRef(null);
  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 30);
    else setQ("");
  }, [open]);

  const groups = useMemo(() => {
    const query = q.trim().toLowerCase();
    const filter = (arr, fn) => query ? arr.filter(fn) : arr.slice(0, 4);
    return [
      {
        label: "Actions",
        items: filter([
          { icon: "🔍", label: "Run new search", hint: "Enter", action: () => { onNav("search"); onClose(); } },
          { icon: "📷", label: "Search by image upload", hint: "⌘I", action: () => { onNav("search"); onClose(); } },
          { icon: "📋", label: "Create watchlist", hint: "⌘N", action: () => { onNav("watchlists"); onClose(); } },
          { icon: "📤", label: "Generate weekly report", hint: "", action: () => onClose() },
        ], i => i.label.toLowerCase().includes(query)),
      },
      {
        label: "Trademarks",
        items: filter(window.TRADEMARKS, t =>
          t.name.toLowerCase().includes(query) || t.applicant.toLowerCase().includes(query)
        ).map(t => ({
          icon: <span style={{ fontFamily: '"Be Vietnam Pro", sans-serif', fontWeight: 700, fontSize: 11, color: "var(--stamp)", letterSpacing: "0.04em" }}>{t.name.slice(0, 2)}</span>,
          label: t.name,
          sub: t.applicant,
          hint: t.appNo,
          action: () => { onNav(`detail:${t.id}`); onClose(); },
        })),
      },
      {
        label: "Watchlists",
        items: filter(window.WATCHLISTS, w => w.name.toLowerCase().includes(query) || w.client.toLowerCase().includes(query)).map(w => ({
          icon: "📁",
          label: w.name,
          sub: w.client + " · " + w.matter,
          hint: `${w.newCount} new`,
          action: () => { onNav("watchlists"); onClose(); },
        })),
      },
      {
        label: "Recent",
        items: filter(window.RECENT_SEARCHES, s => s.q.toLowerCase().includes(query)).map(s => ({
          icon: "⏱",
          label: s.q,
          sub: s.scope,
          hint: s.when,
          action: () => { onNav("search"); onClose(); },
        })),
      },
    ].filter(g => g.items.length > 0);
  }, [q]);

  if (!open) return null;
  return (
    <div className="cmdk-overlay" onClick={onClose}>
      <div className="cmdk" onClick={e => e.stopPropagation()}>
        <div className="cmdk-search">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          <input ref={inputRef} value={q} onChange={e => setQ(e.target.value)}
            placeholder="Search marks, applicants, agents, app numbers…"/>
          <kbd>esc</kbd>
        </div>
        <div className="cmdk-body">
          {groups.length === 0 && (
            <div style={{ padding: "24px 16px", color: "var(--mute)", fontSize: 13 }}>No matches.</div>
          )}
          {groups.map(g => (
            <div key={g.label} className="cmdk-group">
              <div className="cmdk-group-label">{g.label}</div>
              {g.items.map((it, i) => (
                <button key={i} className="cmdk-item" onClick={it.action}>
                  <span className="cmdk-icon">{it.icon}</span>
                  <span className="cmdk-label">
                    <span>{it.label}</span>
                    {it.sub && <span className="cmdk-sub">{it.sub}</span>}
                  </span>
                  {it.hint && <kbd>{it.hint}</kbd>}
                </button>
              ))}
            </div>
          ))}
        </div>
        <div className="cmdk-footer">
          <span><kbd>↑</kbd><kbd>↓</kbd> navigate</span>
          <span><kbd>↵</kbd> open</span>
          <span>Phonetic, fuzzy, image-similarity all supported</span>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { TopNav, CmdK, Logo });
