// Dashboard — re-anchored around the user's watchlists & deadlines
const { useState: useStateD } = React;

function Dashboard({ onNav }) {
  const u = window.CURRENT_USER;
  const watchlists = window.WATCHLISTS;
  const totalNew = watchlists.reduce((a, w) => a + w.newCount, 0);
  const openOpps = window.OPPOSITIONS.filter(o => o.status === "open").sort((a,b) => a.daysLeft - b.daysLeft);
  const closingSoon = openOpps.filter(o => o.daysLeft <= 14);
  const findings = window.TRADEMARKS.filter(t => t.similarToWatch).sort((a,b) => b.similarToWatch.score - a.similarToWatch.score);

  return (
    <div className="container view-pad">
      {/* ===== Hero strip ===== */}
      <div className="hero">
        <div className="hero-left">
          <p className="hero-eyebrow">Tuesday 19 May · This week's digest</p>
          <h1 className="hero-h1">
            <span style={{ color: "var(--stamp)" }}>{totalNew} new findings</span>
            <span style={{ color: "var(--mute)" }}> across {watchlists.filter(w => w.newCount > 0).length} watchlists.</span>
          </h1>
          <p className="hero-sub">
            {closingSoon.length} opposition window{closingSoon.length === 1 ? "" : "s"} closing in the next 14 days · last sync {fmtDate("2026-05-19")} 08:14
          </p>
          <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
            <button className="btn btn-primary" onClick={() => onNav("watchlists")}>Review findings →</button>
            <button className="btn btn-ghost" onClick={() => onNav("search")}>New search</button>
          </div>
        </div>
        <div className="hero-right">
          <KpiRow openOpps={openOpps} totalNew={totalNew} watchlists={watchlists}/>
        </div>
      </div>

      {/* ===== Two columns ===== */}
      <div className="grid-2 mt-24">
        {/* Findings */}
        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">New findings</h2>
              <p className="card-sub">Marks landed this period that match one of your watchlists, ranked by composite similarity.</p>
            </div>
            <button className="link-btn" onClick={() => onNav("search")}>Open in Search →</button>
          </header>
          <div className="finding-list">
            {findings.map(t => (
              <button key={t.id} className="finding-row" onClick={() => onNav(`detail:${t.id}`)}>
                <div className="finding-mark">
                  <MarkSpecimen mark={t} size="sm"/>
                </div>
                <div className="finding-meta">
                  <div className="finding-top">
                    <span className="finding-name">{t.name}</span>
                    <Pill tone={t.type === "A" ? "A" : "B"} size="sm">{t.type}</Pill>
                    {t.classes.map(c => <ClassChip key={c} n={c} matched={c === 5}/>)}
                  </div>
                  <div className="finding-applicant">{t.applicant}</div>
                  <div className="finding-bottom">
                    <Flag code={t.country} size={12}/>
                    <span style={{ color: "var(--mute)" }}>{t.countryName}</span>
                    <span className="dot-sep">·</span>
                    <span style={{ fontFamily: '"JetBrains Mono", monospace', color: "var(--mute)" }}>{t.appNo}</span>
                    <span className="dot-sep">·</span>
                    <span style={{ color: "var(--mute)" }}>published {fmtDate(t.publishedAt)}</span>
                  </div>
                </div>
                <div className="finding-right">
                  <SimilarityRing score={t.similarToWatch.score} size={42}/>
                  <div className="finding-watch">
                    <div className="finding-watch-name">{watchlists.find(w => w.id === t.similarToWatch.watchId)?.name}</div>
                    <div className="finding-watch-reason">{t.similarToWatch.reason}</div>
                  </div>
                </div>
              </button>
            ))}
          </div>
          <footer className="card-foot">
            <span style={{ color: "var(--mute)", fontSize: 12 }}>Showing {findings.length} of {findings.length}</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-tiny">Dismiss all</button>
              <button className="btn btn-tiny">Generate client report</button>
            </div>
          </footer>
        </section>

        {/* Opposition windows */}
        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">Opposition windows</h2>
              <p className="card-sub">Days remaining to file opposition against a published application. Vietnam: 5 months from publication date.</p>
            </div>
            <button className="link-btn">Calendar view →</button>
          </header>
          <ul className="opp-list">
            {openOpps.map(o => (
              <li key={o.markId} className={"opp-row " + (o.daysLeft <= 14 ? "opp-urgent" : "")}>
                <div className="opp-days">
                  <span className="opp-days-num">{o.daysLeft}</span>
                  <span className="opp-days-label">days</span>
                </div>
                <div className="opp-meta">
                  <div className="opp-name">{o.markName}</div>
                  <div className="opp-applicant">{o.applicant}</div>
                  <div className="opp-bottom">
                    {o.classes.map(c => <ClassChip key={c} n={c}/>)}
                    <span className="dot-sep">·</span>
                    <span style={{ color: "var(--mute)" }}>closes {fmtDate(o.closesAt)}</span>
                    {o.watchId && (
                      <>
                        <span className="dot-sep">·</span>
                        <span style={{ color: "var(--stamp)" }}>{window.WATCHLISTS.find(w => w.id === o.watchId)?.name}</span>
                      </>
                    )}
                  </div>
                </div>
                <div className="opp-actions">
                  <button className="btn btn-tiny" onClick={() => onNav(`detail:${o.markId}`)}>Open</button>
                </div>
                <div className="opp-bar" aria-hidden="true">
                  <div className="opp-bar-fill" style={{
                    width: `${Math.max(4, Math.min(100, (o.daysLeft / 60) * 100))}%`,
                    background: o.daysLeft <= 14 ? "var(--stamp)" : o.daysLeft <= 30 ? "var(--warn)" : "var(--ok)",
                  }}></div>
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      {/* ===== Watchlists + Recent ===== */}
      <div className="grid-2 mt-24">
        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">Watchlists</h2>
              <p className="card-sub">Saved queries that re-run automatically each gazette issue.</p>
            </div>
            <button className="link-btn">+ New watchlist</button>
          </header>
          <ul className="watchlist-list">
            {watchlists.map(w => (
              <li key={w.id} className="watchlist-row">
                <div className="watchlist-marker" style={{ background: w.newCount > 0 ? "var(--stamp)" : "var(--line-strong)" }}></div>
                <div className="watchlist-meta">
                  <div className="watchlist-name">{w.name}</div>
                  <div className="watchlist-desc">{w.client} · <span style={{ color: "var(--mute)" }}>{w.queryDesc}</span></div>
                </div>
                <div className="watchlist-counts">
                  <div className="wl-new">{w.newCount > 0 ? `+${w.newCount}` : "—"}</div>
                  <div className="wl-total">{w.totalCount.toLocaleString()} total</div>
                </div>
              </li>
            ))}
          </ul>
        </section>

        <section className="card">
          <header className="card-head">
            <div>
              <h2 className="card-title">Your recent activity</h2>
              <p className="card-sub">Searches you've run. Click to re-execute against the latest gazette.</p>
            </div>
          </header>
          <ul className="recent-list">
            {window.RECENT_SEARCHES.map(s => (
              <li key={s.id} className="recent-row" onClick={() => onNav("search")}>
                <div className="recent-icon">
                  {s.q.startsWith("image:") ? "📷" : s.q.startsWith("applicant:") ? "👤" : "🔍"}
                </div>
                <div className="recent-meta">
                  <div className="recent-q" style={{ fontFamily: '"JetBrains Mono", monospace' }}>{s.q}</div>
                  <div className="recent-scope">{s.scope}</div>
                </div>
                <div className="recent-right">
                  <div className="recent-count">{s.count}</div>
                  <div className="recent-when">{s.when}</div>
                </div>
              </li>
            ))}
          </ul>
          <footer className="card-foot">
            <span style={{ color: "var(--mute)", fontSize: 12 }}>Last 7 days</span>
            <button className="link-btn" onClick={() => onNav("search")}>View all →</button>
          </footer>
        </section>
      </div>

      {/* ===== Admin / pipeline (collapsed) ===== */}
      <PipelineCollapse/>
    </div>
  );
}

function KpiRow({ openOpps, totalNew, watchlists }) {
  const closingThisWeek = openOpps.filter(o => o.daysLeft <= 7).length;
  const closingNextTwo = openOpps.filter(o => o.daysLeft <= 14).length;
  const activeWatchlists = watchlists.length;
  return (
    <div className="kpi-row">
      <Kpi label="Findings" value={totalNew} sub="across all watchlists" tone="stamp"/>
      <Kpi label="Opposition · 7d" value={closingThisWeek} sub={`${closingNextTwo} within 14d`} tone={closingThisWeek > 0 ? "warn" : "mute"}/>
      <Kpi label="Watchlists" value={activeWatchlists} sub="3 with new findings" tone="ink"/>
    </div>
  );
}

function Kpi({ label, value, sub, tone }) {
  const toneColor = { stamp: "var(--stamp)", warn: "oklch(0.50 0.13 75)", ink: "var(--ink)", mute: "var(--ink)" }[tone];
  return (
    <div className="kpi">
      <div className="kpi-label">{label}</div>
      <div className="kpi-value" style={{ color: toneColor }}>{value}</div>
      <div className="kpi-sub">{sub}</div>
    </div>
  );
}

function PipelineCollapse() {
  const [open, setOpen] = useStateD(false);
  return (
    <details className="pipeline-collapse mt-24" open={open} onToggle={e => setOpen(e.target.open)}>
      <summary>
        <span className="pipeline-label">
          <span className="pipeline-dot" style={{ background: "var(--ok)" }}></span>
          Ingest pipeline · 8 / 8 gazettes processed
        </span>
        <span className="pipeline-meta">Latest: B_T4_2026.pdf · 2 min ago · 9,499 rows</span>
        <span className="pipeline-toggle">{open ? "Hide" : "Show details"}</span>
      </summary>
      <div className="pipeline-detail">
        <div className="pipeline-stats">
          <div><span>Total trademarks ingested</span><strong>46,758</strong></div>
          <div><span>This quarter</span><strong>23,777</strong></div>
          <div><span>Pages OCR'd</span><strong>11,420</strong></div>
          <div><span>Manual review queue</span><strong style={{ color: "var(--warn)" }}>14 rows</strong></div>
        </div>
        <p style={{ fontSize: 12, color: "var(--mute)", marginTop: 8 }}>
          Pipeline details are now collapsed by default — they live in the Gazettes tab for admins.
        </p>
      </div>
    </details>
  );
}

window.Dashboard = Dashboard;
