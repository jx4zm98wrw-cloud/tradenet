/**
 * Marketing landing page (`/`).
 *
 * Server component — every section on this page is static. The only
 * interactive piece (the SimilarityRing) renders the same DOM on every
 * load and doesn't need client hydration. Marketing nav is the only
 * client component on the route, isolated in `MarketingNav.tsx`.
 *
 * Section order mirrors `design_handoff_tradenet_marketing/IMPLEMENTATION_PLAN.md`:
 *   1. Hero (two-column: copy + scorecard demo)
 *   2. Stats strip (4-up)
 *   3. Features (4-up grid)
 *   4. Deep-dive: Image similarity (paper-2 bg, mosaic left)
 *   5. Deep-dive: Opposition calendar (reversed split)
 *   6. Deep-dive: Conflict scorecard (paper-2 bg)
 *   7. Coverage grid (4×2 recent gazettes)
 *   8. CTA strip (oxblood gradient)
 *
 * Stat values, feature copy, and scorecard data come from `_content/landing.ts`.
 * For PR 1 they're hard-coded — the IMPLEMENTATION_PLAN calls out wiring
 * `GET /api/v1/stats/overview` with ISR 1h in a follow-up; not in scope here.
 */
import { landing } from "./_content/landing";
import { SimilarityRing } from "@/components/marketing/SimilarityRing";

/** Decorative corner ticks on the prototype's mark-plate (4 corners). */
function PlateTicks() {
  const base = { width: 6, height: 6, opacity: 0.4 } as const;
  return (
    <>
      <span
        className="hd-mark-tick"
        style={{ ...base, top: 3, left: 3, borderTop: "1px solid var(--mute)", borderLeft: "1px solid var(--mute)" }}
      />
      <span
        className="hd-mark-tick"
        style={{ ...base, top: 3, right: 3, borderTop: "1px solid var(--mute)", borderRight: "1px solid var(--mute)" }}
      />
      <span
        className="hd-mark-tick"
        style={{ ...base, bottom: 3, left: 3, borderBottom: "1px solid var(--mute)", borderLeft: "1px solid var(--mute)" }}
      />
      <span
        className="hd-mark-tick"
        style={{ ...base, bottom: 3, right: 3, borderBottom: "1px solid var(--mute)", borderRight: "1px solid var(--mute)" }}
      />
    </>
  );
}

/** Inline icon set for the feature cards. Stroked, 22×22, currentColor. */
function FeatureIcon({ kind }: { kind: "image" | "bell" | "calendar" | "grid" }) {
  const svgProps = {
    width: 22,
    height: 22,
    viewBox: "0 0 24 24",
    fill: "none" as const,
    stroke: "currentColor" as const,
    strokeWidth: 2 as const,
  };
  switch (kind) {
    case "image":
      return (
        <svg {...svgProps}>
          <rect x={3} y={3} width={18} height={18} rx={2} />
          <circle cx={9} cy={9} r={2} />
          <path d="m21 15-5-5L5 21" />
        </svg>
      );
    case "bell":
      return (
        <svg {...svgProps}>
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10 21a2 2 0 0 0 4 0" />
        </svg>
      );
    case "calendar":
      return (
        <svg {...svgProps}>
          <rect x={3} y={4} width={18} height={18} rx={2} />
          <path d="M16 2v4M8 2v4M3 10h18" />
          <path d="M12 14v4M9 16h6" />
        </svg>
      );
    case "grid":
      return (
        <svg {...svgProps}>
          <rect x={3} y={3} width={7} height={7} />
          <rect x={14} y={3} width={7} height={7} />
          <rect x={3} y={14} width={7} height={7} />
          <rect x={14} y={14} width={7} height={7} />
        </svg>
      );
  }
}

/** Wordmark rendered as SVG text inside a mosaic cell or mark plate. */
function WordmarkSVG({
  text,
  font,
  weight,
  size,
  fill,
  letterSpacing,
  viewBox = "0 0 200 80",
}: {
  text: string;
  font: "sans" | "serif";
  weight: 600 | 700 | 800;
  size: number;
  fill: string;
  letterSpacing?: number;
  viewBox?: string;
}) {
  const family =
    font === "sans"
      ? "Be Vietnam Pro, sans-serif"
      : "Source Serif 4, serif";
  // Mark-plate SVGs in the hero use a slightly different viewBox
  // (200×60) with central y=30 vs the mosaic (200×80, y=40).
  const cy = viewBox === "0 0 200 80" ? 40 : 30;
  return (
    <svg viewBox={viewBox} preserveAspectRatio="xMidYMid meet">
      <text
        x={100}
        y={cy}
        textAnchor="middle"
        dominantBaseline="central"
        fontFamily={family}
        fontWeight={weight}
        fontSize={size}
        letterSpacing={letterSpacing}
        fill={fill}
      >
        {text}
      </text>
    </svg>
  );
}

export default function MarketingLandingPage() {
  const { hero, scorecard, stats, featuresSection, features, imageSimilarity, opposition, scorecardDeep, coverageSection, coverage, cta } = landing;

  return (
    <>
      {/* HERO */}
      <div className="hero">
        <div className="hero-bg" />
        <div className="container hero-inner">
          <div className="hero-left">
            <span className="eyebrow hero-eyebrow">{hero.eyebrow}</span>
            <h1 className="hero-h1">
              {hero.h1Plain.lead}
              <span className="stamp">{hero.h1Plain.stampWord}</span>
              {hero.h1Plain.middle}
              <span className="strike">{hero.h1Plain.strikeWord}</span>
              {hero.h1Plain.tail}
            </h1>
            <p className="hero-sub">{hero.sub}</p>
            <div className="hero-ctas">
              {/* Primary CTA routes to /login (signup pane will land in PR 3). */}
              <a href="/login" className="btn btn-primary btn-lg">{hero.ctaPrimary}</a>
              <button type="button" className="btn btn-ghost btn-lg">
                <svg width={14} height={14} viewBox="0 0 24 24" fill="currentColor">
                  <path d="M8 5v14l11-7z" />
                </svg>
                {hero.ctaGhost}
              </button>
            </div>
            <p className="hero-microcopy">{hero.microcopy}</p>
          </div>

          {/* Hero demo: conflict scorecard preview */}
          <aside className="hero-demo" aria-label="Conflict scorecard preview">
            <div className="hero-demo-head">
              <span className="hero-demo-title">{scorecard.title}</span>
              <span className="hero-demo-status">{scorecard.status}</span>
            </div>

            <div className="hero-demo-mark-row">
              <div className="hd-mark">
                <div className="hd-mark-plate">
                  <PlateTicks />
                  <WordmarkSVG
                    text={scorecard.yours.name}
                    font="sans"
                    weight={800}
                    size={36}
                    fill="var(--stamp)"
                    letterSpacing={1.2}
                    viewBox="0 0 200 60"
                  />
                </div>
                <div className="hd-mark-name">{scorecard.yours.name}</div>
                <div className="hd-mark-meta">{scorecard.yours.meta}</div>
              </div>
              <div className="hd-vs">
                <span>VS</span>
                <div className="hd-vs-line" />
              </div>
              <div className="hd-mark">
                <div className="hd-mark-plate">
                  <PlateTicks />
                  <WordmarkSVG
                    text={scorecard.other.name}
                    font="sans"
                    weight={800}
                    size={32}
                    fill="var(--ink)"
                    letterSpacing={1.2}
                    viewBox="0 0 200 60"
                  />
                </div>
                <div className="hd-mark-name">{scorecard.other.name}</div>
                <div className="hd-mark-meta">{scorecard.other.meta}</div>
              </div>
            </div>

            <div
              className="hero-demo-mark-row"
              style={{ gridTemplateColumns: "repeat(3, 1fr)" }}
            >
              {scorecard.rings.map((r) => (
                <div key={r.label} className="hd-ring-wrap">
                  <SimilarityRing score={r.score} size={44} />
                  <span
                    style={{
                      fontSize: 10,
                      color: "var(--mute)",
                      fontFamily: "var(--font-mono), JetBrains Mono, monospace",
                      textTransform: "uppercase",
                      letterSpacing: "0.08em",
                    }}
                  >
                    {r.label}
                  </span>
                </div>
              ))}
            </div>

            <div className="hero-demo-foot">
              <span className="hd-verdict">
                <span className="hd-verdict-dot" />
                {scorecard.verdict}
              </span>
              <span
                style={{
                  fontSize: 11,
                  color: "var(--mute)",
                  fontFamily: "var(--font-mono), JetBrains Mono, monospace",
                }}
              >
                Opposition closes in{" "}
                <strong style={{ color: "var(--stamp)" }}>
                  {scorecard.oppositionClosesInDays} days
                </strong>
              </span>
            </div>
          </aside>
        </div>
      </div>

      {/* STATS */}
      <section className="stats">
        <div className="container stats-grid">
          {stats.map((s) => (
            <div key={s.label} className="stat">
              <div className="stat-value">
                {s.value}
                {"unit" in s && s.unit ? (
                  <span style={{ fontSize: "0.5em", color: "var(--mute)" }}>{s.unit}</span>
                ) : null}
              </div>
              <div className="stat-label">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* FEATURES */}
      <section className="section" id="features">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">{featuresSection.eyebrow}</span>
            <h2 className="section-h2">{featuresSection.h2}</h2>
            <p className="section-sub">{featuresSection.sub}</p>
          </div>

          <div className="features">
            {features.map((f) => (
              <article key={f.title} className="feature-card">
                <div className="feature-icon">
                  <FeatureIcon kind={f.icon} />
                </div>
                <h3 className="feature-h3">{f.title}</h3>
                <p className="feature-body">{f.body}</p>
                <div className="feature-foot">{f.tech}</div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* DEEP DIVE: Image similarity */}
      <section
        className="section"
        style={{
          background: "var(--paper-2)",
          borderTop: "1px solid var(--line)",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <div className="container split">
          <div className="viz">
            <div className="viz-eyebrow">
              <span>{imageSimilarity.vizEyebrow.left}</span>
              <span>{imageSimilarity.vizEyebrow.right}</span>
            </div>
            <div className="spec-mosaic">
              {imageSimilarity.mosaic.map((cell) => (
                <div
                  key={cell.word}
                  className={`spec-mosaic-cell${cell.matched ? " matched" : ""}`}
                >
                  <span className="score-tag">{cell.score}</span>
                  <WordmarkSVG
                    text={cell.word}
                    font={cell.font as "sans" | "serif"}
                    weight={cell.weight}
                    size={cell.size}
                    fill={cell.fill}
                    letterSpacing={"letterSpacing" in cell ? cell.letterSpacing : undefined}
                  />
                </div>
              ))}
            </div>
          </div>
          <div>
            <span className="eyebrow">{imageSimilarity.eyebrow}</span>
            <h3 className="split-h3">{imageSimilarity.h3}</h3>
            {imageSimilarity.bodyParas.map((p, i) => (
              <p key={i} className="split-body">{p}</p>
            ))}
            <ul className="split-bullets">
              {imageSimilarity.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* DEEP DIVE: Opposition calendar */}
      <section className="section">
        <div className="container split reverse">
          <div className="viz">
            <div className="viz-eyebrow">
              <span>{opposition.vizEyebrow.left}</span>
              <span>{opposition.vizEyebrow.right}</span>
            </div>
            <div className="opp-cal">
              {opposition.rows.map((row, i) => (
                <div key={i} className="opp-cal-row">
                  <div
                    className={`opp-cal-days${row.urgency === "urgent" ? " urgent" : ""}`}
                    style={row.urgency === "warn" ? { color: "var(--warn)" } : undefined}
                  >
                    {row.days}
                    <small>days</small>
                  </div>
                  <div>
                    <div className="opp-cal-mark">{row.mark}</div>
                    <div className="opp-cal-meta">{row.meta}</div>
                    <div className="opp-cal-bar" style={{ marginTop: 6 }}>
                      <div
                        className="opp-cal-bar-fill"
                        style={{ width: `${row.barPct}%`, background: row.barColor }}
                      />
                    </div>
                  </div>
                  <button type="button" className="btn btn-sm btn-ghost">{row.cta}</button>
                </div>
              ))}
            </div>
          </div>
          <div>
            <span className="eyebrow">{opposition.eyebrow}</span>
            <h3 className="split-h3">{opposition.h3}</h3>
            {opposition.bodyParas.map((p, i) => (
              <p key={i} className="split-body">{p}</p>
            ))}
            <ul className="split-bullets">
              {opposition.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* DEEP DIVE: Scorecard */}
      <section
        className="section"
        style={{
          background: "var(--paper-2)",
          borderTop: "1px solid var(--line)",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <div className="container split">
          <div className="viz">
            <div className="viz-eyebrow">
              <span>{scorecardDeep.vizEyebrow.left}</span>
              <span>{scorecardDeep.vizEyebrow.right}</span>
            </div>

            <div style={{ display: "flex", alignItems: "flex-start", gap: 18, marginBottom: 18 }}>
              <div>
                <div style={{ fontFamily: "var(--font-serif), Source Serif 4, serif", fontSize: 20, fontWeight: 600 }}>
                  {scorecardDeep.otherName}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--mute)", marginTop: 2 }}>
                  {scorecardDeep.otherApplicant}
                </div>
              </div>
              <div style={{ marginLeft: "auto" }}>
                <SimilarityRing score={scorecardDeep.composite} size={52} />
              </div>
            </div>

            <div style={{ marginBottom: 14 }}>
              <span className="pill pill-stamp">
                <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--stamp)", display: "inline-block" }} />
                {scorecardDeep.verdict}
              </span>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {scorecardDeep.bars.map((b) => (
                <div
                  key={b.label}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "100px 1fr 32px",
                    gap: 8,
                    alignItems: "center",
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: "var(--mute)" }}>{b.label}</span>
                  <div style={{ height: 5, background: "var(--paper-3)", borderRadius: 3, overflow: "hidden" }}>
                    <div style={{ width: `${b.pct}%`, height: "100%", background: b.color }} />
                  </div>
                  <span className="mono tnum" style={{ textAlign: "right", fontWeight: 700 }}>{b.pct}</span>
                </div>
              ))}
            </div>
          </div>
          <div>
            <span className="eyebrow">{scorecardDeep.eyebrow}</span>
            <h3 className="split-h3">{scorecardDeep.h3}</h3>
            {scorecardDeep.bodyParas.map((p, i) => (
              <p key={i} className="split-body">{p}</p>
            ))}
            <ul className="split-bullets">
              {scorecardDeep.bullets.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* COVERAGE */}
      <section className="section" id="coverage">
        <div className="container">
          <div className="section-head">
            <span className="eyebrow">{coverageSection.eyebrow}</span>
            <h2 className="section-h2">{coverageSection.h2}</h2>
            <p className="section-sub">{coverageSection.sub}</p>
          </div>

          <div className="coverage">
            {coverage.map((c) => (
              <div key={c.label} className="coverage-cell">
                <span className="coverage-issue">
                  <span className="coverage-dot" />
                  {c.label}
                </span>
                <span className="coverage-count">{c.count}</span>
                <span className="coverage-meta">{c.meta}</span>
              </div>
            ))}
          </div>

          <p className="text-center mt-24" style={{ fontSize: 13, color: "var(--mute)" }}>
            {coverageSection.footnote}
          </p>
        </div>
      </section>

      {/* CTA STRIP */}
      <section className="container">
        <div className="cta-strip">
          <div>
            <h2 className="cta-h2">{cta.h2}</h2>
            <p className="cta-sub">{cta.sub}</p>
          </div>
          <div className="cta-actions">
            <a href="/login" className="btn btn-primary btn-lg">{cta.primary}</a>
            <a href="/pricing" className="btn btn-ghost btn-lg">{cta.ghost}</a>
          </div>
        </div>
      </section>
    </>
  );
}
