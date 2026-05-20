// Search — image-similarity, view modes (table/grid/timeline), multi-select compare
const { useState: useStateS, useMemo: useMemoS } = React;

function Search({ onNav, onCompareSelected }) {
  const [mode, setMode] = useStateS("text"); // text | phonetic | image | vienna
  const [view, setView] = useStateS("grid"); // table | grid
  const [query, setQuery] = useStateS("neur");
  const [simThreshold, setSimThreshold] = useStateS(0.65);
  const [selected, setSelected] = useStateS(new Set());
  const [density, setDensity] = useStateS("cozy");

  // Filter chips state (visual only)
  const [filters, setFilters] = useStateS({
    country: ["VN", "SG", "IN", "GB", "DE"],
    classes: [5, 10],
    applicantType: "any",
    period: "Last 90 days",
    typeRecord: "A",
  });

  const results = useMemoS(() => {
    const q = query.trim().toLowerCase();
    return window.TRADEMARKS
      .map(t => {
        // synthetic similarity score for demo
        let score;
        if (mode === "image") score = 0.4 + Math.random() * 0.6; // just for visual
        else if (q.length === 0) score = 0.5;
        else {
          const inName = t.name.toLowerCase().includes(q);
          const phon = q.length > 1 && t.name.toLowerCase().slice(0,3) === q.slice(0,3);
          score = inName ? 0.92 : phon ? 0.78 : t.similarToWatch?.score || 0.4;
        }
        return { t, score };
      })
      .filter(({ t, score }) => {
        if (score < simThreshold) return false;
        if (filters.classes.length && !filters.classes.some(c => t.classes.includes(c))) return false;
        if (filters.country.length && !filters.country.includes(t.country)) return false;
        return true;
      })
      .sort((a, b) => b.score - a.score);
  }, [query, mode, simThreshold, filters]);

  const toggleSel = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };

  const tweakClass = (c) => {
    setFilters(f => ({ ...f, classes: f.classes.includes(c) ? f.classes.filter(x => x !== c) : [...f.classes, c] }));
  };
  const tweakCountry = (cc) => {
    setFilters(f => ({ ...f, country: f.country.includes(cc) ? f.country.filter(x => x !== cc) : [...f.country, cc] }));
  };

  return (
    <div className="search-shell">
      {/* Query bar (full-width band) */}
      <div className="query-band">
        <div className="container">
          <div className="query-modes">
            <button onClick={() => setMode("text")} className={"mode-tab" + (mode === "text" ? " active" : "")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h10"/></svg>
              Text
            </button>
            <button onClick={() => setMode("phonetic")} className={"mode-tab" + (mode === "phonetic" ? " active" : "")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12h2l3 8 4-16 3 8h6"/></svg>
              Phonetic / fuzzy
            </button>
            <button onClick={() => setMode("image")} className={"mode-tab" + (mode === "image" ? " active" : "")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-5-5L5 21"/></svg>
              Image
            </button>
            <button onClick={() => setMode("vienna")} className={"mode-tab" + (mode === "vienna" ? " active" : "")}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 2v20M2 12h20"/><circle cx="12" cy="12" r="9"/></svg>
              Vienna code
            </button>
          </div>

          {mode === "image" ? <ImageSearchInput/> : <TextSearchInput query={query} setQuery={setQuery} mode={mode}/>}

          {/* Similarity threshold + active filter chips */}
          <div className="query-extras">
            <div className="sim-control">
              <span style={{ fontSize: 12, color: "var(--mute)" }}>Similarity ≥</span>
              <input type="range" min="0.4" max="0.99" step="0.01" value={simThreshold}
                onChange={e => setSimThreshold(parseFloat(e.target.value))}/>
              <span className="sim-value">{Math.round(simThreshold * 100)}%</span>
            </div>
            <div className="chip-row">
              <span style={{ fontSize: 11, color: "var(--mute)", fontWeight: 500, marginRight: 4 }}>Active:</span>
              <FilterChip>Period: {filters.period}<button>×</button></FilterChip>
              <FilterChip>
                Classes: <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>05, 10</span>
                <Toggle label="ALL" alt="ANY"/>
                <button>×</button>
              </FilterChip>
              <FilterChip>Type: A (Application)<button>×</button></FilterChip>
              <button className="link-btn" style={{ fontSize: 12 }}>Save as watchlist</button>
            </div>
          </div>
        </div>
      </div>

      <div className="container search-body">
        {/* Left rail */}
        <aside className="search-rail">
          <RailGroup title="Record type">
            <Check checked={filters.typeRecord === "A"} label="A · Application" count={19412}/>
            <Check checked={false} label="B · Domestic registration" count={25508}/>
            <Check checked={false} label="B · Madrid registration" count={1838}/>
          </RailGroup>

          <RailGroup title="Country" trailing={<button className="link-btn">Show all 67</button>}>
            <Check checked={filters.country.includes("VN")} onChange={() => tweakCountry("VN")} flag="VN" label="Vietnam" count={32068}/>
            <Check checked={filters.country.includes("CN")} onChange={() => tweakCountry("CN")} flag="CN" label="China" count={5490}/>
            <Check checked={filters.country.includes("US")} onChange={() => tweakCountry("US")} flag="US" label="United States" count={1847}/>
            <Check checked={filters.country.includes("KR")} onChange={() => tweakCountry("KR")} flag="KR" label="South Korea" count={1402}/>
            <Check checked={filters.country.includes("SG")} onChange={() => tweakCountry("SG")} flag="SG" label="Singapore" count={812}/>
            <Check checked={filters.country.includes("GB")} onChange={() => tweakCountry("GB")} flag="GB" label="United Kingdom" count={617}/>
            <Check checked={filters.country.includes("DE")} onChange={() => tweakCountry("DE")} flag="DE" label="Germany" count={488}/>
            <Check checked={filters.country.includes("IN")} onChange={() => tweakCountry("IN")} flag="IN" label="India" count={401}/>
          </RailGroup>

          <RailGroup title="Nice classes"
            subtitle="Match marks covering ANY selected class"
            trailing={<select className="rail-select"><option>ANY of selected</option><option>ALL of selected</option></select>}
          >
            <ClassCheck n={5} matched checked={filters.classes.includes(5)} onChange={() => tweakClass(5)} count={617}/>
            <ClassCheck n={10} matched checked={filters.classes.includes(10)} onChange={() => tweakClass(10)} count={98}/>
            <ClassCheck n={44} checked={filters.classes.includes(44)} onChange={() => tweakClass(44)} count={61}/>
            <ClassCheck n={35} checked={filters.classes.includes(35)} onChange={() => tweakClass(35)} count={112}/>
            <ClassCheck n={29} checked={filters.classes.includes(29)} onChange={() => tweakClass(29)} count={85}/>
            <button className="link-btn" style={{ alignSelf: "flex-start", marginTop: 4 }}>Show all 45 classes →</button>
          </RailGroup>

          <RailGroup title="Applicant">
            <Check checked={false} label="Company" count={235}/>
            <Check checked={true} label="Personal" count={382}/>
            <Check checked={false} label="Government / SOE" count={9}/>
          </RailGroup>

          <RailGroup title="Publication date">
            <div className="rail-dates">
              <label>From<input type="date" defaultValue="2026-01-01"/></label>
              <label>To<input type="date" defaultValue="2026-05-19"/></label>
            </div>
            <div className="rail-presets">
              <button>This week</button><button>This month</button><button className="active">Last 90 days</button><button>YTD</button>
            </div>
          </RailGroup>
        </aside>

        {/* Results */}
        <main className="search-main">
          {/* Result toolbar */}
          <div className="result-toolbar">
            <div>
              <div className="result-count">
                <strong>{results.length} trademarks</strong>
                <span style={{ color: "var(--mute)" }}> match {mode === "image" ? "uploaded image" : query ? `"${query}"` : "your filters"}</span>
              </div>
              <p className="result-desc">Personal & company applicants · Classes 5, 10 · Vietnam + 4 others · last 90 days</p>
            </div>
            <div className="result-toolbar-right">
              <div className="seg">
                <button className={view === "grid" ? "active" : ""} onClick={() => setView("grid")} title="Grid">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
                </button>
                <button className={view === "table" ? "active" : ""} onClick={() => setView("table")} title="Table">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18M3 12h18M3 18h18"/></svg>
                </button>
              </div>
              <select className="sort-select">
                <option>Sort: Similarity ↓</option>
                <option>Sort: Publication ↓</option>
                <option>Sort: Applicant A→Z</option>
                <option>Sort: Class count</option>
              </select>
              <button className="btn btn-ghost btn-sm">
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/></svg>
                Export
              </button>
            </div>
          </div>

          {/* Selection toolbar */}
          {selected.size > 0 && (
            <div className="sel-bar">
              <div className="sel-bar-left">
                <button className="link-btn" onClick={() => setSelected(new Set())}>Clear</button>
                <strong>{selected.size} selected</strong>
              </div>
              <div className="sel-bar-right">
                <button className="btn btn-tiny">+ Add to watchlist</button>
                <button className="btn btn-tiny">Tag</button>
                <button className="btn btn-tiny">Export</button>
                <button className="btn btn-primary btn-tiny" onClick={() => onCompareSelected(Array.from(selected))}>
                  Compare {selected.size} marks →
                </button>
              </div>
            </div>
          )}

          {/* Results body */}
          {view === "grid" ? (
            <ResultsGrid results={results} selected={selected} onSelect={toggleSel} onNav={onNav}/>
          ) : (
            <ResultsTable results={results} selected={selected} onSelect={toggleSel} onNav={onNav}/>
          )}

          {/* Pagination */}
          <div className="pagination">
            <span style={{ color: "var(--mute)", fontSize: 12 }}>Showing 1–{Math.min(results.length, 50)} of {results.length}</span>
            <div className="pager">
              <button disabled>‹</button>
              <button className="active">1</button>
              <button>2</button>
              <button>3</button>
              <span>…</span>
              <button>13</button>
              <button>›</button>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

function TextSearchInput({ query, setQuery, mode }) {
  const placeholder = mode === "phonetic"
    ? "Sound-alike: NEUREX, NEUR*, *FAX… (Soundex / Metaphone applied automatically)"
    : "Trademark name, applicant, mark, application number…";
  return (
    <div className="query-input">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
      <input value={query} onChange={e => setQuery(e.target.value)} placeholder={placeholder}/>
      <div className="query-helpers">
        <button className="ghost-key">applicant:</button>
        <button className="ghost-key">class:</button>
        <button className="ghost-key">agent:</button>
      </div>
    </div>
  );
}

function ImageSearchInput() {
  return (
    <div className="image-drop">
      <div className="image-drop-preview">
        <MarkSpecimen mark={{ specimen: { style: "wordmark-sans-bold", color: "stamp", text: "NEUREX" }, name: "NEUREX" }} size="sm"/>
      </div>
      <div className="image-drop-meta">
        <div style={{ fontSize: 13, fontWeight: 600 }}>NEUREX_specimen.png</div>
        <div style={{ fontSize: 11, color: "var(--mute)" }}>312 × 84 · pHash <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>9b4a3f8e</span> · OCR'd "NEUREX"</div>
        <div style={{ fontSize: 11, color: "var(--mute)", marginTop: 4 }}>Matching by: visual (pHash), OCR'd text, Vienna code inference</div>
      </div>
      <div className="image-drop-actions">
        <button className="btn btn-tiny">Replace</button>
        <button className="btn btn-tiny">Adjust weights</button>
      </div>
    </div>
  );
}

function FilterChip({ children }) {
  return <span className="filter-chip">{children}</span>;
}
function Toggle({ label, alt }) {
  const [v, setV] = useStateS(true);
  return <button onClick={() => setV(!v)} className="mini-toggle">{v ? label : alt}</button>;
}

function RailGroup({ title, subtitle, trailing, children }) {
  return (
    <div className="rail-group">
      <div className="rail-head">
        <h4>{title}</h4>
        {trailing}
      </div>
      {subtitle && <p className="rail-sub">{subtitle}</p>}
      <div className="rail-body">{children}</div>
    </div>
  );
}

function Check({ checked, onChange, flag, label, count }) {
  return (
    <label className={"rail-check" + (checked ? " checked" : "")}>
      <input type="checkbox" checked={checked} onChange={onChange || (() => {})}/>
      {flag && <Flag code={flag} size={14}/>}
      <span className="rail-check-label">{label}</span>
      <span className="rail-check-count">{count.toLocaleString()}</span>
    </label>
  );
}
function ClassCheck({ n, checked, onChange, matched, count }) {
  return (
    <label className={"rail-check" + (checked ? " checked" : "")}>
      <input type="checkbox" checked={checked} onChange={onChange || (() => {})}/>
      <span style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 11, fontWeight: 700, color: matched ? "var(--stamp)" : "var(--mute)", width: 22 }}>{String(n).padStart(2,"0")}</span>
      <span className="rail-check-label">{window.NICE_CLASSES[n].label}</span>
      <span className="rail-check-count">{count}</span>
    </label>
  );
}

function ResultsGrid({ results, selected, onSelect, onNav }) {
  return (
    <div className="results-grid">
      {results.map(({ t, score }) => (
        <article key={t.id} className={"result-card" + (selected.has(t.id) ? " selected" : "")}>
          <button className="result-sel" onClick={() => onSelect(t.id)} aria-pressed={selected.has(t.id)}>
            {selected.has(t.id) ? <CheckIcon/> : <span className="result-sel-empty"></span>}
          </button>
          <div className="result-similarity">
            <SimilarityRing score={score} size={32}/>
          </div>
          <button className="result-mark" onClick={() => onNav(`detail:${t.id}`)}>
            <MarkSpecimen mark={t} size="md"/>
          </button>
          <div className="result-meta">
            <div className="result-top">
              <span className="result-name">{t.name}</span>
              <Pill tone={t.type === "A" ? "A" : "B"} size="sm">{t.type}</Pill>
            </div>
            <div className="result-applicant">{t.applicant}</div>
            <div className="result-bottom">
              <Flag code={t.country} size={12}/>
              <span style={{ color: "var(--mute)", fontFamily: '"JetBrains Mono", monospace' }}>{t.appNo}</span>
              <span className="dot-sep">·</span>
              <span style={{ color: "var(--mute)" }}>{fmtDate(t.publishedAt)}</span>
            </div>
            <div className="result-classes">
              {t.classes.slice(0, 5).map(c => <ClassChip key={c} n={c} matched={[5,10].includes(c)}/>)}
              {t.classes.length > 5 && <span className="more-classes">+{t.classes.length - 5}</span>}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

function ResultsTable({ results, selected, onSelect, onNav }) {
  return (
    <div className="results-table-wrap">
      <table className="results-table">
        <thead>
          <tr>
            <th style={{ width: 32 }}></th>
            <th style={{ width: 56 }}>Sim</th>
            <th style={{ width: 100 }}>Mark</th>
            <th>Name / Applicant</th>
            <th style={{ width: 60 }}>Type</th>
            <th style={{ width: 160 }}>Classes</th>
            <th style={{ width: 100 }}>Country</th>
            <th style={{ width: 120 }}>Published</th>
            <th style={{ width: 160 }}>Agent</th>
          </tr>
        </thead>
        <tbody>
          {results.map(({ t, score }) => (
            <tr key={t.id} className={selected.has(t.id) ? "selected" : ""} onClick={() => onNav(`detail:${t.id}`)}>
              <td onClick={(e) => { e.stopPropagation(); onSelect(t.id); }}>
                <span className={"row-check" + (selected.has(t.id) ? " checked" : "")}>
                  {selected.has(t.id) && <CheckIcon/>}
                </span>
              </td>
              <td><SimilarityRing score={score} size={28}/></td>
              <td><div style={{ width: 90 }}><MarkSpecimen mark={t} size="sm" frame={false}/></div></td>
              <td>
                <div className="cell-name">{t.name}</div>
                <div className="cell-applicant">{t.applicant}</div>
              </td>
              <td><Pill tone={t.type === "A" ? "A" : "B"} size="sm">{t.type}</Pill></td>
              <td>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {t.classes.map(c => <ClassChip key={c} n={c} matched={[5,10].includes(c)}/>)}
                </div>
              </td>
              <td>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Flag code={t.country}/>
                  <span style={{ fontSize: 12, color: "var(--mute)" }}>{t.country}</span>
                </div>
              </td>
              <td className="cell-mono">{fmtDate(t.publishedAt)}</td>
              <td style={{ color: "var(--mute)", fontSize: 12 }}>{t.agent}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CheckIcon() {
  return <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5"><path d="M5 12l5 5 9-11" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

window.Search = Search;
