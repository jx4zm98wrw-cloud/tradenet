"use client";

/**
 * Coverage page heat-grid timeline — 4 rows × 52 weeks of synthetic
 * but deterministic ingest volumes. Ported verbatim from
 * `design_handoff_tradenet_marketing/marketing/marketing.js`
 * (`renderCoverageTimeline`, ~lines 137-193).
 *
 * Why "use client" when the data is deterministic and the values
 * never change at runtime?
 *   - The cells have hover `title` tooltips, which is a runtime-DOM-only
 *     attribute — no harm rendering server-side, but the moment we add
 *     any user interaction (filters, year-toggle) this becomes the
 *     natural place to put it. Marking it now avoids a refactor.
 *   - Marking it client also keeps the `useMemo` semantics honest
 *     (server components can't useMemo). The grid computation runs once
 *     per mount (effectively once per cold load).
 *
 * The cell color buckets match the legend exactly:
 *   load 0 → var(--paper-3)            ·   0 marks
 *   load 1 → oklch(0.86 0.04 28)       · < 2k marks
 *   load 2 → oklch(0.72 0.09 28)       · 2–5k marks
 *   load 3 → var(--stamp)              · 5–8k marks
 *   load 4 → var(--stamp-deep)         · > 8k marks
 *
 * Pseudo-random formula is `((seed * 9301 + w * 49297) % 233280) / 233280`
 * — same constants as the prototype JS, so the rendered grid is
 * pixel-for-pixel identical given the same seeds.
 */
import { useMemo } from "react";

type Row = {
  label: string;
  seed: number;
  /** If true, weeks past 20 force load=0 (used for 2026 in-progress year). */
  partial?: boolean;
};

const ROWS: ReadonlyArray<Row> = [
  { label: "2025 · A", seed: 11 },
  { label: "2025 · B", seed: 23 },
  { label: "2026 · A", seed: 41, partial: true },
  { label: "2026 · B", seed: 59, partial: true },
];

/** Hover tooltip count buckets, indexed by load 0..4 (0 is empty). */
const COUNTS = ["", "< 2k", "2–5k", "5–8k", "> 8k"];

/** Bucket the deterministic pseudo-random `r ∈ [0,1)` into a 0..4 load. */
function bucket(r: number, partial: boolean, w: number): number {
  if (partial && w > 20) return 0;
  if (r < 0.1) return 0;
  if (r < 0.3) return 1;
  if (r < 0.55) return 2;
  if (r < 0.85) return 3;
  return 4;
}

export function IngestTimeline() {
  // Heavy enough (~210 elements) to be worth memoizing.
  const cells = useMemo(() => {
    const out: React.ReactNode[] = [];
    // Header row — empty "wk" corner cell, then 52 week-number cells.
    out.push(
      <div key="corner" className="tl-grid-label">
        wk
      </div>,
    );
    for (let w = 1; w <= 52; w++) {
      out.push(
        <div key={`wk-${w}`} className="tl-grid-week">
          {w % 4 === 1 ? w : ""}
        </div>,
      );
    }
    // 4 data rows.
    for (const { label, seed, partial } of ROWS) {
      out.push(
        <div key={`label-${label}`} className="tl-grid-label">
          {label}
        </div>,
      );
      for (let w = 1; w <= 52; w++) {
        const r = ((seed * 9301 + w * 49297) % 233280) / 233280;
        const load = bucket(r, Boolean(partial), w);
        const title =
          load > 0 ? `${label} · wk ${w} · ${COUNTS[load]} marks` : undefined;
        out.push(
          <div
            key={`${label}-${w}`}
            className="tl-grid-cell"
            data-load={load}
            title={title}
          />,
        );
      }
    }
    return out;
  }, []);

  return (
    <div className="timeline-band">
      <div className="timeline-band-head">
        <div>
          <h3 className="tl-h3">Ingest timeline · last 12 months</h3>
          <p className="tl-sub">
            Every cell is one weekly gazette issue. Color intensity = mark
            count.
          </p>
        </div>
        <div className="tl-legend">
          <span>Volume:</span>
          <span>
            <span
              className="tl-legend-swatch"
              style={{ background: "var(--paper-3)" }}
            />
            0
          </span>
          <span>
            <span
              className="tl-legend-swatch"
              style={{ background: "oklch(0.86 0.04 28)" }}
            />
            &lt; 2k
          </span>
          <span>
            <span
              className="tl-legend-swatch"
              style={{ background: "oklch(0.72 0.09 28)" }}
            />
            2–5k
          </span>
          <span>
            <span
              className="tl-legend-swatch"
              style={{ background: "var(--stamp)" }}
            />
            5–8k
          </span>
          <span>
            <span
              className="tl-legend-swatch"
              style={{ background: "var(--stamp-deep)" }}
            />
            &gt; 8k
          </span>
        </div>
      </div>
      <div className="tl-grid">{cells}</div>
    </div>
  );
}
