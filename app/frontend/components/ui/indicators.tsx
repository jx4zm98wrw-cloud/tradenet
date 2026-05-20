/** Circular % indicator. Colors degrade with score: ≥0.85 stamp, ≥0.7 warn, else ok.
 * Used in finding rows, search results, and Compare scorecards. */
export function SimilarityRing({ score, size = 36 }: { score: number; size?: number }) {
  const r = (size - 4) / 2;
  const c = 2 * Math.PI * r;
  const dash = c * Math.max(0, Math.min(1, score));
  const stroke = score >= 0.85 ? "var(--stamp)" : score >= 0.7 ? "var(--warn)" : "var(--ok)";
  const pct = Math.round(score * 100);
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--line)" strokeWidth={3} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none"
          stroke={stroke} strokeWidth={3} strokeLinecap="round"
          strokeDasharray={`${dash} ${c}`}
        />
      </svg>
      <div
        className="absolute inset-0 grid place-items-center font-mono font-bold tabular"
        style={{ fontSize: size * 0.28, color: stroke }}
      >
        {pct}
      </div>
    </div>
  );
}

/** Live-state pulse — used in status pills ("Examination pending", "Active"). */
export function PulseDot({ tone = "ok", className = "" }: { tone?: "ok" | "warn" | "stamp"; className?: string }) {
  const c = { ok: "text-ok", warn: "text-warn", stamp: "text-stamp" }[tone];
  return <span className={`pulse-dot ${c} ${className}`} aria-hidden="true" />;
}

/** Horizontal progress bar with three colored bands. */
export function ProgressBar({
  value, height = 4, daysLeft, className = "",
}: {
  value: number;
  height?: number;
  /** When set, color is determined by remaining days: ≤14 stamp · ≤30 warn · else ok. */
  daysLeft?: number;
  className?: string;
}) {
  const pct = Math.max(0, Math.min(100, value * 100));
  let color = "var(--ok)";
  if (typeof daysLeft === "number") {
    if (daysLeft <= 14) color = "var(--stamp)";
    else if (daysLeft <= 30) color = "var(--warn)";
  }
  return (
    <div
      className={`relative w-full overflow-hidden bg-line rounded-full ${className}`}
      style={{ height }}
    >
      <div
        className="absolute inset-y-0 left-0 transition-[width] duration-200"
        style={{ width: `${pct}%`, background: color }}
      />
    </div>
  );
}
