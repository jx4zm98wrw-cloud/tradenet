// Auxiliary screens: Watchlists, Gazettes (admin)

function Watchlists({ onNav }) {
  return (
    <div className="container view-pad">
      <div className="page-head">
        <div>
          <h1 className="page-h1">Watchlists</h1>
          <p className="page-sub">Standing queries re-run automatically against every new gazette issue. Findings surface on your dashboard.</p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button className="btn btn-ghost">Import from CSV</button>
          <button className="btn btn-primary">+ New watchlist</button>
        </div>
      </div>

      <div className="watch-grid">
        {window.WATCHLISTS.map(w => {
          const findings = window.TRADEMARKS.filter(t => t.similarToWatch?.watchId === w.id);
          return (
            <article key={w.id} className="watch-card">
              <header className="watch-card-head">
                <div>
                  <h3>{w.name}</h3>
                  <p className="watch-client">{w.client} <span className="dot-sep">·</span> <span style={{ fontFamily: '"JetBrains Mono", monospace', color: "var(--mute)" }}>{w.matter}</span></p>
                </div>
                <div className="watch-count">
                  <div className="watch-count-num" style={{ color: w.newCount > 0 ? "var(--stamp)" : "var(--mute)" }}>
                    {w.newCount > 0 ? `+${w.newCount}` : "0"}
                  </div>
                  <div className="watch-count-label">new this period</div>
                </div>
              </header>
              <div className="watch-query">
                <span className="watch-query-label">Query</span>
                <span className="watch-query-text">{w.queryDesc}</span>
              </div>
              <div className="watch-findings">
                {findings.length === 0 ? (
                  <p style={{ fontSize: 12, color: "var(--mute)", textAlign: "center", padding: 16 }}>No new findings since {fmtDate("2026-04-15")}.</p>
                ) : (
                  <ul>
                    {findings.map(t => (
                      <li key={t.id} onClick={() => onNav(`detail:${t.id}`)}>
                        <div style={{ width: 60 }}><MarkSpecimen mark={t} size="sm"/></div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div className="finding-name" style={{ fontSize: 13 }}>{t.name}</div>
                          <div style={{ fontSize: 11, color: "var(--mute)" }}>{t.applicant}</div>
                        </div>
                        <SimilarityRing score={t.similarToWatch.score} size={28}/>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
              <footer className="watch-card-foot">
                <span style={{ fontSize: 11, color: "var(--mute)" }}>{w.totalCount.toLocaleString()} total · last run {fmtDate(w.lastUpdated)}</span>
                <button className="link-btn">Edit query</button>
              </footer>
            </article>
          );
        })}

        <button className="watch-card watch-card-add">
          <div style={{ fontSize: 22, color: "var(--mute)" }}>+</div>
          <div style={{ fontWeight: 600 }}>New watchlist</div>
          <div style={{ fontSize: 12, color: "var(--mute)" }}>From a saved search, an uploaded image, or an existing mark</div>
        </button>
      </div>
    </div>
  );
}

function Gazettes({ onNav }) {
  return (
    <div className="container view-pad">
      <div className="page-head">
        <div>
          <h1 className="page-h1">Gazettes</h1>
          <p className="page-sub">8 issues processed · 46,758 trademarks total · pipeline healthy. This view is for admins; daily users live on Today.</p>
        </div>
        <button className="btn btn-primary">Upload gazette</button>
      </div>

      <div className="drop-zone">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
        <p>Drop PDFs here, or <span style={{ color: "var(--stamp)" }}>click to browse</span></p>
        <p className="drop-zone-sub">Multiple files OK · A_T*_YYYY.pdf or B_T*_YYYY.pdf · max 500MB each</p>
      </div>

      <div className="card">
        <table className="results-table gazette-table">
          <thead>
            <tr>
              <th>Issue</th>
              <th>Type</th>
              <th>Status</th>
              <th style={{ textAlign: "right" }}>Rows</th>
              <th>Size</th>
              <th>Uploaded</th>
              <th>Processed</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {window.GAZETTES.map(g => (
              <tr key={g.id}>
                <td>
                  <div className="cell-name" style={{ fontSize: 13 }}>{g.issue}</div>
                  <div style={{ fontSize: 11, color: "var(--mute)", fontFamily: '"JetBrains Mono", monospace' }}>{g.file}</div>
                </td>
                <td><Pill tone={g.type === "A" ? "A" : "B"} size="sm">{g.typeLabel}</Pill></td>
                <td>
                  {g.warning ? (
                    <span style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                      <Pill tone="warn" size="sm">⚠ Needs review</Pill>
                      <span style={{ fontSize: 11, color: "var(--mute)", marginTop: 2 }}>{g.warning}</span>
                    </span>
                  ) : (
                    <Pill tone="ok" size="sm">
                      <span className="pulse-dot" style={{ background: "var(--ok)" }}></span>
                      Completed
                    </Pill>
                  )}
                </td>
                <td style={{ textAlign: "right", fontFamily: '"JetBrains Mono", monospace', fontWeight: 600 }}>{g.rows.toLocaleString()}</td>
                <td style={{ color: "var(--mute)", fontSize: 12 }}>{g.sizeMB} MB</td>
                <td style={{ color: "var(--mute)", fontSize: 12 }}>{g.uploadedAgo}</td>
                <td style={{ color: "var(--mute)", fontSize: 12 }}>{g.processed}</td>
                <td style={{ textAlign: "right" }}>
                  <button className="row-more">⋯</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

window.Watchlists = Watchlists;
window.Gazettes = Gazettes;
