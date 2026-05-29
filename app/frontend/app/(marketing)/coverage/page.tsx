/**
 * Marketing coverage page (`/coverage`).
 *
 * Server component — no client state. The only interactive child is
 * `<IngestTimeline />`, which marks itself `"use client"` so React can
 * memoize the ~210-cell heat grid on the client without forcing the
 * whole page to hydrate.
 *
 * Section order mirrors the prototype (`data-view="coverage"` block in
 * `design_handoff_tradenet_marketing/Tradenet - Marketing.html` lines
 * 676-881):
 *   1. Hero (eyebrow + 48px serif h1 + sub paragraph)
 *   2. 4-up coverage stats row (`<CoverageStat />` × 4)
 *   3. "What's in the corpus" — 2×2 source-card grid (2 primary + 2 not)
 *   4. Ingest timeline heat grid (`<IngestTimeline />`, client)
 *   5. "Data quality, openly measured" — 3-col DQ card grid
 *   6. Oxblood gradient CTA strip linking to /docs + /login
 *
 * Hover tooltips on the timeline are deterministic (the seed+week
 * formula in marketing.js is reproduced 1:1 in IngestTimeline.tsx) so
 * the grid is pixel-stable for visual regression.
 */
import Link from "next/link";
import { CoverageStat } from "@/components/marketing/CoverageStat";
import { SourceCard } from "@/components/marketing/SourceCard";
import { IngestTimeline } from "@/components/marketing/IngestTimeline";
import { DqCard } from "@/components/marketing/DqCard";
import {
  coverageCta,
  coverageHero,
  coverageStats,
  dqCards,
  sourceCards,
} from "../_content/coverage";

export default function CoveragePage() {
  return (
    <>
      {/* Hero */}
      <section className="view">
        <div className="container coverage-hero">
          <span className="eyebrow">{coverageHero.eyebrow}</span>
          <h1
            className="section-h2"
            style={{ fontSize: 48, marginTop: 14 }}
          >
            {coverageHero.h1}
          </h1>
          <p
            className="section-sub"
            style={{ maxWidth: 680, margin: "8px auto 0" }}
          >
            {coverageHero.sub}
          </p>

          <div className="coverage-stats">
            {coverageStats.map((s) => (
              <CoverageStat
                key={s.label}
                label={s.label}
                value={s.value}
                valueSuffix={s.valueSuffix}
                meta={s.meta}
              />
            ))}
          </div>
        </div>
      </section>

      {/* Sources */}
      <section className="container">
        <div style={{ textAlign: "center", marginBottom: 32 }}>
          <h2
            className="section-h2"
            style={{ fontSize: 30, margin: 0 }}
          >
            What&apos;s in the corpus
          </h2>
          <p className="section-sub" style={{ marginTop: 8 }}>
            Five data sources, normalized into one searchable index.
          </p>
        </div>

        <div className="coverage-sources">
          {sourceCards.map((card) => (
            <SourceCard
              key={card.name}
              name={card.name}
              sub={card.sub}
              primary={card.primary}
              pillLabel={card.pillLabel}
              body={card.body}
              kvs={card.kvs}
            />
          ))}
        </div>
      </section>

      {/* Recent issues timeline */}
      <section className="container" style={{ marginTop: 48 }}>
        <IngestTimeline />
      </section>

      {/* Data quality */}
      <section className="section" style={{ padding: "64px 0 56px" }}>
        <div className="container">
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <h2
              className="section-h2"
              style={{ fontSize: 30, margin: 0 }}
            >
              Data quality, openly measured
            </h2>
            <p className="section-sub" style={{ marginTop: 8 }}>
              We don&apos;t claim &ldquo;complete&rdquo; coverage. We publish
              our actual numbers.
            </p>
          </div>
          <div className="dq-grid">
            {dqCards.map((card) => (
              <DqCard
                key={card.heading}
                heading={card.heading}
                value={card.value}
                valueSuffix={card.valueSuffix}
                fillPct={card.fillPct}
                fillColorVar={card.fillColorVar}
                meta={card.meta}
              />
            ))}
          </div>
        </div>
      </section>

      {/* API teaser CTA strip */}
      <section className="container">
        <div className="cta-strip">
          <div>
            <h2 className="cta-h2">{coverageCta.h2}</h2>
            <p className="cta-sub">{coverageCta.sub}</p>
          </div>
          <div className="cta-actions">
            <Link
              href={coverageCta.primaryHref}
              className="btn btn-primary btn-lg"
            >
              {coverageCta.primaryLabel}
            </Link>
            <Link
              href={coverageCta.secondaryHref}
              className="btn btn-ghost btn-lg"
            >
              {coverageCta.secondaryLabel}
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
