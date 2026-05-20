// Compare — side-by-side conflict review with a scorecard
const { useState: useStateC } = React;

function Compare({ markIds, onNav, onChangeIds }) {
  // Up to 3 marks
  const ids = (markIds && markIds.length >= 2) ? markIds.slice(0, 3) : ["tm-001", "tm-002", "tm-003"];
  const marks = ids.map(id => window.findMark(id)).filter(Boolean);

  // The "anchor" is the first mark (typically the client's mark)
  const anchor = marks[0];
  const others = marks.slice(1);

  return (
    <div className="container view-pad compare-shell">
      <div className="detail-breadcrumb">
        <button className="link-btn" onClick={() => onNav("search")}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          Back to search
        </button>
        <div className="breadcrumb-trail">
          <span>Compare</span><span className="sep">/</span>
          <strong>{marks.map(m => m.name).join(" vs. ")}</strong>
        </div>
        <div className="detail-actions">
          <button className="btn btn-tiny">Add mark to compare</button>
          <button className="btn btn-tiny">Save comparison</button>
          <button className="btn btn-tiny btn-primary">Export PDF report</button>
        </div>
      </div>

      {/* Scorecard band */}
      <ScorecardBand marks={marks}/>

      {/* Mark plates row */}
      <div className="compare-plates" style={{ gridTemplateColumns: `1.2fr repeat(${marks.length}, 1fr)` }}>
        <div className="cmp-label-col">
          <div className="cmp-section">Mark specimen</div>
        </div>
        {marks.map((m, i) => (
          <div key={m.id} className={"cmp-plate-cell" + (i === 0 ? " anchor" : "")}>
            {i === 0 && <div className="anchor-label">Your mark</div>}
            <div className="cmp-plate">
              <MarkSpecimen mark={m} size="lg"/>
            </div>
            <div className="cmp-plate-name">
              <strong>{m.name}</strong>
              <Pill tone={m.type === "A" ? "A" : "B"} size="sm">{m.type}</Pill>
            </div>
            <div className="cmp-plate-applicant">{m.applicant}</div>
          </div>
        ))}
      </div>

      {/* Comparative rows */}
      <div className="compare-rows" style={{ gridTemplateColumns: `1.2fr repeat(${marks.length}, 1fr)` }}>

        <CmpHeader>Identity & status</CmpHeader>
        <CmpRow label="Type">
          {marks.map(m => <span key={m.id}>{m.typeLabel}</span>)}
        </CmpRow>
        <CmpRow label="Status">
          {marks.map(m => (
            <span key={m.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="pulse-dot" style={{ background: m.type === "A" ? "var(--warn)" : "var(--ok)" }}></span>
              {m.type === "A" ? "Pending publication" : "Active"}
            </span>
          ))}
        </CmpRow>
        <CmpRow label="Application №">
          {marks.map(m => <span key={m.id} style={{ fontFamily: '"JetBrains Mono", monospace' }}>{m.appNo}</span>)}
        </CmpRow>
        <CmpRow label="Country / origin">
          {marks.map(m => (
            <span key={m.id} style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Flag code={m.country} size={14}/>{m.countryName}
            </span>
          ))}
        </CmpRow>
        <CmpRow label="Applicant">
          {marks.map(m => <span key={m.id} style={{ fontSize: 12.5 }}>{m.applicant}</span>)}
        </CmpRow>
        <CmpRow label="IP agent">
          {marks.map(m => <span key={m.id} style={{ color: "var(--mute)" }}>{m.agent}</span>)}
        </CmpRow>

        <CmpHeader>Similarity to {anchor.name}</CmpHeader>
        <SimilarityCmp marks={marks}/>

        <CmpHeader>Classes & overlap</CmpHeader>
        <CmpRow label="Nice classes" align="top">
          {marks.map((m, i) => (
            <div key={m.id} style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
              {m.classes.map(c => (
                <ClassChip key={c} n={c} matched={i > 0 && anchor.classes.includes(c)}/>
              ))}
            </div>
          ))}
        </CmpRow>
        <CmpRow label="Overlapping classes" align="top">
          {marks.map((m, i) => {
            if (i === 0) return <span key={m.id} style={{ color: "var(--mute)" }}>—</span>;
            const overlap = m.classes.filter(c => anchor.classes.includes(c));
            return (
              <div key={m.id}>
                <strong style={{ color: overlap.length > 0 ? "var(--stamp)" : "var(--mute)" }}>{overlap.length} of {m.classes.length}</strong>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 4 }}>
                  {overlap.map(c => <ClassChip key={c} n={c} matched/>)}
                </div>
              </div>
            );
          })}
        </CmpRow>

        <CmpHeader>Procedural state</CmpHeader>
        <CmpRow label="Filed">
          {marks.map(m => <span key={m.id} style={{ fontFamily: '"JetBrains Mono", monospace' }}>{fmtDate(m.filedAt)}</span>)}
        </CmpRow>
        <CmpRow label="Published">
          {marks.map(m => <span key={m.id} style={{ fontFamily: '"JetBrains Mono", monospace' }}>{fmtDate(m.publishedAt)}</span>)}
        </CmpRow>
        <CmpRow label="Opposition window">
          {marks.map(m => {
            const opp = window.OPPOSITIONS.find(o => o.markId === m.id);
            if (!opp) return <span key={m.id} style={{ color: "var(--mute)" }}>—</span>;
            const tone = opp.status === "open" ? (opp.daysLeft <= 14 ? "stamp" : "warn") : "mute";
            return (
              <span key={m.id}>
                <Pill tone={tone} size="sm">
                  {opp.status === "open" ? `${opp.daysLeft} days left` : "Closed"}
                </Pill>
                <span style={{ marginLeft: 6, color: "var(--mute)", fontSize: 12 }}>closes {fmtDateShort(opp.closesAt)}</span>
              </span>
            );
          })}
        </CmpRow>
        <CmpRow label="Source gazette">
          {marks.map(m => <span key={m.id} style={{ fontFamily: '"JetBrains Mono", monospace', fontSize: 12 }}>{m.gazette} <span style={{ color: "var(--mute)" }}>p. {m.page}</span></span>)}
        </CmpRow>

        <CmpHeader>Action</CmpHeader>
        <CmpRow label="Recommended">
          {marks.map((m, i) => {
            if (i === 0) return <span key={m.id} style={{ color: "var(--mute)" }}>Anchor (your mark)</span>;
            // crude recommendation derived from class overlap + name similarity
            const overlap = m.classes.filter(c => anchor.classes.includes(c)).length;
            const phonetic = m.name.slice(0, 3) === anchor.name.slice(0, 3);
            let rec = "Monitor only";
            let tone = "mute";
            if (overlap >= 1 && phonetic) { rec = "Consider opposition"; tone = "stamp"; }
            else if (overlap >= 1) { rec = "Watch closely"; tone = "warn"; }
            return <Pill key={m.id} tone={tone}>{rec}</Pill>;
          })}
        </CmpRow>
        <CmpRow label="Quick action">
          {marks.map((m, i) => (
            <div key={m.id} style={{ display: "flex", gap: 6 }}>
              {i > 0 && <button className="btn btn-tiny">File opposition</button>}
              <button className="btn btn-tiny" onClick={() => onNav(`detail:${m.id}`)}>Open detail</button>
            </div>
          ))}
        </CmpRow>
      </div>
    </div>
  );
}

function ScorecardBand({ marks }) {
  const anchor = marks[0];
  // Compute a synthetic composite score per non-anchor mark
  const cards = marks.slice(1).map(m => {
    const overlap = m.classes.filter(c => anchor.classes.includes(c)).length;
    const classScore = overlap / Math.max(1, anchor.classes.length);
    const phon = m.name.slice(0, 3).toLowerCase() === anchor.name.slice(0, 3).toLowerCase() ? 0.85 : 0.4;
    const vis  = 0.55 + Math.random() * 0.3;
    const composite = (phon * 0.4 + vis * 0.3 + classScore * 0.3);
    const verdict = composite >= 0.75 ? { tone: "stamp", label: "Likely conflict" }
                   : composite >= 0.55 ? { tone: "warn",  label: "Possible conflict" }
                   :                     { tone: "ok",    label: "Low risk" };
    return { m, phon, vis, classScore, composite, verdict };
  });
  return (
    <section className="scorecard-band">
      <header>
        <div>
          <div className="band-eyebrow">Conflict scorecard</div>
          <h2 className="band-title">{anchor.name} <span style={{ color: "var(--mute)" }}>vs.</span> {cards.map(c => c.m.name).join(", ")}</h2>
          <p className="band-sub">Composite = 40% phonetic · 30% visual (pHash + Vienna) · 30% class overlap. Tune weights in your matter settings.</p>
        </div>
      </header>
      <div className="scorecard-cards">
        {cards.map(({ m, phon, vis, classScore, composite, verdict }) => (
          <div key={m.id} className="scorecard">
            <div className="scorecard-head">
              <div>
                <div className="scorecard-name">{m.name}</div>
                <div className="scorecard-applicant">{m.applicant}</div>
              </div>
              <SimilarityRing score={composite} size={52}/>
            </div>
            <div className="scorecard-verdict">
              <Pill tone={verdict.tone}>{verdict.label}</Pill>
            </div>
            <div className="scorecard-bars">
              <ScoreBar label="Phonetic" value={phon}/>
              <ScoreBar label="Visual"   value={vis}/>
              <ScoreBar label="Class overlap" value={classScore}/>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function ScoreBar({ label, value }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "var(--stamp)" : value >= 0.6 ? "var(--warn)" : "var(--ok)";
  return (
    <div className="score-bar">
      <span className="score-bar-label">{label}</span>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${pct}%`, background: color }}></div>
      </div>
      <span className="score-bar-pct">{pct}</span>
    </div>
  );
}

function SimilarityCmp({ marks }) {
  const anchor = marks[0];
  return (
    <>
      <CmpRow label="Phonetic (Metaphone + Levenshtein)">
        {marks.map((m, i) => i === 0
          ? <span key={m.id} style={{ color: "var(--mute)" }}>—</span>
          : <ScoreInline key={m.id} value={m.name.slice(0,3).toLowerCase() === anchor.name.slice(0,3).toLowerCase() ? 0.88 : 0.42}/>
        )}
      </CmpRow>
      <CmpRow label="Visual (pHash + Vienna code)">
        {marks.map((m, i) => i === 0
          ? <span key={m.id} style={{ color: "var(--mute)" }}>—</span>
          : <ScoreInline key={m.id} value={0.55 + Math.random() * 0.3}/>
        )}
      </CmpRow>
      <CmpRow label="Semantic (NLP on goods/services)">
        {marks.map((m, i) => i === 0
          ? <span key={m.id} style={{ color: "var(--mute)" }}>—</span>
          : <ScoreInline key={m.id} value={m.classes.some(c => anchor.classes.includes(c)) ? 0.81 : 0.3}/>
        )}
      </CmpRow>
    </>
  );
}

function ScoreInline({ value }) {
  const pct = Math.round(value * 100);
  const color = value >= 0.8 ? "var(--stamp)" : value >= 0.6 ? "var(--warn)" : "var(--ok)";
  return (
    <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <SimilarityRing score={value} size={28}/>
      <span style={{ color, fontWeight: 600 }}>{pct}%</span>
    </span>
  );
}

function CmpHeader({ children }) {
  return <div className="cmp-header">{children}</div>;
}

function CmpRow({ label, children, align = "center" }) {
  const cells = React.Children.toArray(children);
  return (
    <>
      <div className="cmp-label" style={{ alignSelf: align === "top" ? "start" : "center" }}>{label}</div>
      {cells.map((cell, i) => (
        <div key={i} className="cmp-cell" style={{ alignSelf: align === "top" ? "start" : "center" }}>{cell}</div>
      ))}
    </>
  );
}

window.Compare = Compare;
