import * as React from "react";

export type PillTone = "ink" | "stamp" | "ok" | "warn" | "mute" | "A" | "B";

const TONES: Record<PillTone, string> = {
  ink:   "bg-paper-2 text-ink-2 border-line",
  stamp: "bg-stamp-2 text-stamp border-stamp-line",
  ok:    "bg-ok-2 text-ok border-[oklch(0.85_0.05_165)]",
  warn:  "bg-warn-2 text-[oklch(0.45_0.13_75)] border-[oklch(0.85_0.07_75)]",
  mute:  "bg-transparent text-mute border-line",
  // Record types use distinct hues to read at-a-glance: A=blue, B=violet
  A:     "bg-[oklch(0.96_0.025_220)] text-[oklch(0.42_0.10_220)] border-[oklch(0.88_0.04_220)]",
  B:     "bg-[oklch(0.96_0.03_300)] text-[oklch(0.42_0.13_300)] border-[oklch(0.88_0.05_300)]",
};

type PillProps = {
  tone?: PillTone;
  size?: "sm" | "md";
  soft?: boolean;
  className?: string;
  children: React.ReactNode;
};

export function Pill({ tone = "ink", size = "md", soft, className = "", children }: PillProps) {
  const t = TONES[tone];
  const sz = size === "sm" ? "px-1.5 py-[1px] text-[10.5px]" : "px-2 py-[2px] text-[11.5px]";
  return (
    <span
      className={`inline-flex items-center gap-1 ${sz} font-semibold leading-snug whitespace-nowrap rounded-full border ${soft ? "bg-transparent" : ""} ${t} ${className}`}
    >
      {children}
    </span>
  );
}

/** Removable chip used in the search filter strip. */
export function FilterChip({
  children,
  onRemove,
  className = "",
}: { children: React.ReactNode; onRemove?: () => void; className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 pl-2 pr-1 py-0.5 rounded-full bg-stamp-2 border border-stamp-line text-xs text-stamp font-medium ${className}`}
    >
      {children}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label="Remove filter"
          className="w-4 h-4 grid place-items-center rounded-full hover:bg-stamp-line/40 text-stamp"
        >
          ×
        </button>
      )}
    </span>
  );
}
