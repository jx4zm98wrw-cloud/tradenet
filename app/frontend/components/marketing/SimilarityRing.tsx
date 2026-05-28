/**
 * Marketing landing SimilarityRing.
 *
 * Mirrors `components/ui/indicators.tsx::SimilarityRing` in behavior (same
 * color ramp at ≥0.85 stamp / ≥0.7 warn / else ok, same `(size-4)/2` radius
 * geometry) but lives separately so it can be styled with the prototype's
 * `.simring` / `.simring-text` CSS classes — the in-app version uses
 * Tailwind utilities (`absolute inset-0 grid place-items-center …`), so
 * the marketing classes wouldn't fire on the same root.
 *
 * Ported from `design_handoff_tradenet_marketing/marketing/marketing.js`
 * `renderRing()`.
 */
type Props = {
  /** 0..1 — clamped before render. */
  score: number;
  /** Outer SVG size in px; default matches the prototype demo rings. */
  size?: number;
};

export function SimilarityRing({ score, size = 44 }: Props) {
  const clamped = Math.max(0, Math.min(1, score));
  const r = (size - 4) / 2;
  const c = 2 * Math.PI * r;
  const dash = c * clamped;
  const color = clamped >= 0.85 ? "var(--stamp)" : clamped >= 0.7 ? "var(--warn)" : "var(--ok)";
  const pct = Math.round(clamped * 100);

  return (
    <div
      className="simring"
      style={{ width: size, height: size, display: "inline-block" }}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={3} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={3}
          strokeDasharray={`${dash} ${c}`}
          strokeLinecap="round"
        />
      </svg>
      <div className="simring-text" style={{ fontSize: size * 0.28, color }}>
        {pct}
      </div>
    </div>
  );
}
