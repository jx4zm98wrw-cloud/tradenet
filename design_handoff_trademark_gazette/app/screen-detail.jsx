// Detail view — mark specimen, procedural timeline, opposition window, goods/services
const { useState: useStateDt } = React;

function Detail({ markId, onNav, onCompareWith }) {
  const t = window.findMark(markId) || window.TRADEMARKS[0];

  // Procedural timeline events (synthetic)
  const events = buildTimeline(t);
  const openOpp = (window.OPPOSITIONS.find(o => o.markId === t.id) && window.OPPOSITIONS.find(o => o.markId === t.id).status === "open");

  return (
    <div className="container view-pad detail-shell">
      {/* Breadcrumb */}
      <div className="detail-breadcrumb">
        <button className="link-btn" onClick={() => onNav("search")}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          Back to search results
        </button>
        <div className="breadcrumb-trail">
          <span>Search</span><span className="sep">/</span>
          <span>Class 5 · VN, SG, IN, GB, DE</span><span className="sep">/</span>
          <strong>{t.name}</strong>
        </div>
        <div className="detail-actions">
          <button className="btn btn-tiny">⌃ Watch</button>
          <button className="btn btn-tiny">Copy link</button>
          <button className="btn btn-tiny">Tag</button>
          <button className="btn btn-tiny btn-primary">File opposition</button>
        </div>
      </div>

      <div className="detail-grid">
        {/* Main */}
        <div className="detail-main">
          {/* Hero card: specimen + key facts */}
          <section className="card specimen-card">
            <div className="specimen-card-left">
              <div className="specimen-hero">
                <MarkSpecimen mark={t} size="lg"/>
                <div className="specimen-caption">
                  <span>WIPO INID code 540 · Reproduction of the mark</span>
                  <span style={{ fontFamily: '"JetBrains Mono", monospace' }}>pHash 9b4a3f8e</span>
                </div>
              </div>
              <div className="specimen-claims">
                <ClaimRow label="Type of mark">Figurative wordmark</ClaimRow>
                <ClaimRow label="Color claim">Black on white · No color claimed</ClaimRow>
                <ClaimRow label="Transliteration">{t.name}</ClaimRow>
                <ClaimRow label="Disclaimer">No exclusive right is claimed in the word "PHARM" apart from the mark.</ClaimRow>
              </div>
            </div>
            <div className="specimen-card-right">
              <div className="spec-head">
                <h1 className="spec-name">{t.name}</h1>
                <div className="spec-pills">
                  <Pill tone={t.type === "A" ? "A" : "B"}>{t.typeLabel}</Pill>
                  <Pill tone={t.type === "A" ? "warn" : "ok"} soft>
                    <span className="pulse-dot"></span>
                    {t.type === "A" ? "Examination pending" : "Active registration"}
                  </Pill>
                </div>
              </div>
              <p className="spec-applicant-line">{t.applicant}</p>
              <p className="spec-applicant-sub">
                <Flag code={t.country}/> {t.countryName} · {t.applicantType === "company" ? "Company" : "Individual"} · {t.city}
              </p>

              <dl className="spec-grid">
                <KV label="Application №">{t.appNo}</KV>
                {t.certNo && <KV label="Certificate №">{t.certNo}</KV>}
                <KV label="Filed">{fmtDate(t.filedAt)}</KV>
                <KV label="Published">{fmtDate(t.publishedAt)}</KV>
                {t.registeredAt && <KV label="Registered">{fmtDate(t.registeredAt)}</KV>}
                {t.expiresAt && <KV label="Expires">{fmtDate(t.expiresAt)}</KV>}
                {t.examinedAt && <KV label="Substantive exam">{fmtDate(t.examinedAt)}</KV>}
                <KV label="IP agent">{t.agent}</KV>
              </dl>

              {openOpp && <OppositionBox mark={t}/>}
            </div>
          </section>

          {/* Procedural timeline */}
          <section className="card">
            <header className="card-head">
              <div>
                <h2 className="card-title">Procedural timeline</h2>
                <p className="card-sub">Reconstructed from gazette entries. Status flags surface deadlines automatically.</p>
              </div>
            </header>
            <Timeline events={events}/>
          </section>

          {/* Nice classes — full goods/services rendered */}
          <section className="card">
            <header className="card-head">
              <h2 className="card-title">Goods &amp; services <span className="muted-count">· {t.classes.length} classes</span></h2>
            </header>
            <div className="gs-list">
              {t.classes.map(c => (
                <div key={c} className="gs-row">
                  <div className="gs-class">
                    <ClassChipFull n={c} matched={c === 5}/>
                  </div>
                  <p className="gs-text">{describeGoods(c)}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Similar marks landing this period */}
          <section className="card">
            <header className="card-head">
              <div>
                <h2 className="card-title">Similar marks landing this period</h2>
                <p className="card-sub">Found via phonetic + visual + class-overlap scoring within ±2 gazette issues.</p>
              </div>
              <button className="link-btn" onClick={() => onCompareWith(t.id)}>Compare in side-by-side →</button>
            </header>
            <SimilarMarks anchor={t} onNav={onNav}/>
          </section>
        </div>

        {/* Sidebar */}
        <aside className="detail-side">
          <section className="card">
            <header className="card-head"><h3 className="card-title">Source</h3></header>
            <div className="side-body">
              <p className="side-row"><span>Gazette</span><strong style={{ fontFamily: '"JetBrains Mono", monospace' }}>{t.gazette}</strong></p>
              <p className="side-row"><span>Page</span><strong>{t.page}</strong></p>
              <p className="side-row"><span>Issue</span><strong>{t.gazette.split("_")[1]?.replace("T","T")} / {t.gazette.split("_")[2]?.replace(".pdf","")}</strong></p>
              <p className="side-row"><span>Section</span><strong>{t.type === "A" ? "Applications published" : "Registered marks"}</strong></p>
              <button className="btn btn-tiny w-full mt-12" onClick={() => onNav("gazettes")}>Open in gazette →</button>
            </div>
          </section>

          <section className="card">
            <header className="card-head"><h3 className="card-title">Applicant's portfolio</h3></header>
            <div className="side-body">
              <p className="side-applicant-name">{t.applicant}</p>
              <div className="portfolio-stats">
                <div><strong>54</strong><span>active marks</span></div>
                <div><strong>17</strong><span>pending</span></div>
                <div><strong>3</strong><span>oppositions filed</span></div>
              </div>
              <button className="btn btn-tiny w-full" onClick={() => onNav("search")}>View all 54 marks →</button>
            </div>
          </section>

          <section className="card">
            <header className="card-head"><h3 className="card-title">Co-marks</h3></header>
            <div className="side-body">
              {[
                { name: "SAMSUNG GALAXY", year: 2024, classes: [9] },
                { name: "SAMSUNG PAY", year: 2023, classes: [36] },
                { name: "SAMSUNG SDS", year: 2022, classes: [42] },
                { name: "SAMSUNG BESPOKE", year: 2025, classes: [11] },
              ].map(co => (
                <div key={co.name} className="co-mark">
                  <span className="co-name">{co.name}</span>
                  <span className="co-year">{co.year}</span>
                  {co.classes.map(c => <ClassChip key={c} n={c}/>)}
                </div>
              ))}
            </div>
          </section>

          <section className="card">
            <header className="card-head">
              <h3 className="card-title">Raw INID markers</h3>
              <button className="link-btn">Expand</button>
            </header>
            <div className="side-body">
              <p style={{ fontSize: 12, color: "var(--mute)" }}>
                26 WIPO INID fields extracted (210, 220, 511, 540, 551, 731, 740, …).
                <br/>OCR confidence: <strong style={{ color: "var(--ok)" }}>0.97</strong>
              </p>
            </div>
          </section>
        </aside>
      </div>
    </div>
  );
}

function OppositionBox({ mark }) {
  const opp = window.OPPOSITIONS.find(o => o.markId === mark.id);
  if (!opp) return null;
  const pct = Math.max(2, Math.min(100, (opp.daysLeft / 150) * 100)); // 5 months = 150 days
  const urgent = opp.daysLeft <= 14;
  return (
    <div className={"opp-box" + (urgent ? " urgent" : "")}>
      <div className="opp-box-head">
        <div>
          <div className="opp-box-label">Opposition window — open</div>
          <div className="opp-box-days">
            <span className="opp-box-num">{opp.daysLeft}</span>
            <span className="opp-box-unit">days remaining</span>
          </div>
        </div>
        <button className="btn btn-primary btn-sm">File opposition</button>
      </div>
      <div className="opp-box-bar">
        <div className="opp-box-bar-fill" style={{ width: `${100 - pct}%` }}></div>
        <div className="opp-box-bar-marker" style={{ left: "0%" }}>Published<br/>{fmtDateShort(mark.publishedAt)}</div>
        <div className="opp-box-bar-marker" style={{ left: "100%" }}>Window closes<br/>{fmtDateShort(opp.closesAt)}</div>
      </div>
      <div className="opp-box-foot">Under Vietnam Article 112: opposition window = 5 months from publication date. After this date, only invalidation proceedings remain.</div>
    </div>
  );
}

function buildTimeline(t) {
  const evs = [];
  evs.push({ kind: "filed", date: t.filedAt, label: "Application filed", body: `Filed at NOIP HCMC counter · App № ${t.appNo}`, done: true });
  evs.push({ kind: "formal", date: addDays(t.filedAt, 28), label: "Formal examination passed", body: "Compliance with form requirements verified.", done: true });
  if (t.examinedAt) evs.push({ kind: "exam", date: t.examinedAt, label: "Substantive examination", body: "No conflict with prior registrations found at first pass.", done: true });
  evs.push({ kind: "published", date: t.publishedAt, label: "Published in gazette", body: `Published in ${t.gazette} (page ${t.page}). Opposition window opens.`, done: true, anchor: true });
  if (t.type === "A") {
    evs.push({ kind: "opposition", date: window.OPPOSITIONS.find(o => o.markId === t.id)?.closesAt || addDays(t.publishedAt, 150), label: "Opposition window closes", body: "5 months from publication.", done: false, current: true });
    evs.push({ kind: "registration", date: addDays(t.publishedAt, 300), label: "Registration certificate (expected)", body: "Issued ~10 months after publication, absent opposition.", done: false });
  } else {
    if (t.registeredAt) evs.push({ kind: "registered", date: t.registeredAt, label: "Registration certificate issued", body: `Cert № ${t.certNo}. 10-year validity.`, done: true });
    evs.push({ kind: "renewal", date: t.expiresAt, label: "First renewal due", body: "Renewable indefinitely in 10-year increments.", done: false });
  }
  return evs;
}
function addDays(iso, n) {
  if (!iso) return "—";
  const d = new Date(iso); d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

function Timeline({ events }) {
  return (
    <ol className="timeline">
      {events.map((e, i) => (
        <li key={i} className={"timeline-row " + (e.done ? "done " : "") + (e.current ? "current " : "")}>
          <div className="timeline-node">
            <div className="timeline-dot">{e.done ? <CheckIconSm/> : e.current ? "!" : ""}</div>
            {i < events.length - 1 && <div className="timeline-line"></div>}
          </div>
          <div className="timeline-meta">
            <div className="timeline-head">
              <span className="timeline-label">{e.label}</span>
              <span className="timeline-date">{fmtDate(e.date)}</span>
            </div>
            <div className="timeline-body">{e.body}</div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function CheckIconSm() {
  return <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5"><path d="M5 12l5 5 9-11" strokeLinecap="round" strokeLinejoin="round"/></svg>;
}

function ClaimRow({ label, children }) {
  return (
    <div className="claim-row">
      <span className="claim-label">{label}</span>
      <span className="claim-value">{children}</span>
    </div>
  );
}
function KV({ label, children }) {
  return (
    <div className="kv">
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function describeGoods(c) {
  const map = {
    5:  "Pharmaceutical preparations; medicines for human use; vitamin preparations; dietary supplements for medical purposes; antibacterial pharmaceutical preparations; cardiovascular medicines; dermatological preparations.",
    7:  "Industrial machines and machine tools; semiconductor manufacturing equipment; robots (machines); 3D printers; electric motors other than for land vehicles.",
    9:  "Mobile telephones; smartphones; tablet computers; smartwatches; wireless headphones; computer software, recorded; electric batteries.",
    10: "Surgical, medical and veterinary apparatus and instruments; diagnostic devices; thermometers for medical purposes; medical examination gloves.",
    11: "Apparatus for lighting, heating, refrigerating, drying, ventilating; LED lighting fixtures; air conditioners; water purifiers.",
    29: "Meat, fish, poultry; preserved, dried and cooked fruits and vegetables; processed seafood; dairy products including milk, cheese, butter.",
    30: "Coffee, tea, cocoa; rice; pasta and noodles; bread, pastry; ice cream; honey; soy sauce; condiments; instant noodles.",
    32: "Beers; mineral and aerated waters; fruit beverages and fruit juices; soft drinks; energy drinks.",
    35: "Advertising; business management; business administration; office functions; retail services in the field of pharmaceuticals.",
    36: "Insurance services; financial services; banking; mobile payment processing; electronic funds transfer.",
    38: "Telecommunications services; mobile telephony services; data transmission; provision of internet access; streaming of audio and video.",
    41: "Education services; training; entertainment; sporting and cultural activities; online publication of electronic books and journals.",
    42: "Scientific and technological services; research and design; software-as-a-service (SaaS); cloud computing; design of computer hardware.",
    43: "Services for providing food and drink; temporary accommodation; café and restaurant services; bar services.",
    44: "Medical services; pharmacy advice; pharmaceutical consultation; health clinic services; dispensing of pharmaceuticals.",
  };
  return map[c] || "Goods/services in this Nice class — full text extracted from the gazette entry.";
}

function SimilarMarks({ anchor, onNav }) {
  const others = window.TRADEMARKS
    .filter(t => t.id !== anchor.id && t.classes.some(c => anchor.classes.includes(c)))
    .slice(0, 4);
  return (
    <div className="similar-grid">
      {others.map(t => (
        <button key={t.id} className="similar-tile" onClick={() => onNav(`detail:${t.id}`)}>
          <MarkSpecimen mark={t} size="sm"/>
          <div className="similar-meta">
            <div className="similar-name">{t.name}</div>
            <div className="similar-sub">{t.applicant.split(" ").slice(0, 3).join(" ")}{t.applicant.split(" ").length > 3 ? "…" : ""}</div>
            <div className="similar-tags">
              <Flag code={t.country} size={11}/>
              {t.classes.slice(0, 3).map(c => <ClassChip key={c} n={c} matched={anchor.classes.includes(c)}/>)}
            </div>
          </div>
          <div className="similar-score">
            <SimilarityRing score={0.6 + Math.random() * 0.3} size={28}/>
          </div>
        </button>
      ))}
    </div>
  );
}

window.Detail = Detail;
