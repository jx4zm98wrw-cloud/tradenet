"use client";
import * as React from "react";

/** Mark specimen primitives.
 *
 * In production, mark specimens are raster images extracted from the gazette PDF
 * — render those via `imageUrl`. Until that pipeline exists, fall back to a
 * deterministic SVG typographic treatment so each mark still reads as a "real
 * specimen" rather than the original demo's "applicant name in serif".
 */

export type SpecimenStyle =
  | "wordmark-sans-bold"
  | "wordmark-serif"
  | "wordmark-italic-serif"
  | "wordmark-rounded"
  | "wordmark-condensed"
  | "monogram-V"
  | "monogram-circle";

export type SpecimenColor = "ink" | "stamp" | "ok";

export type SpecimenInfo = {
  style: SpecimenStyle;
  color: SpecimenColor;
  text: string;
  imageUrl?: string;
};

const FONTS: Record<SpecimenStyle, {
  family: string; weight: number; italic: boolean; letterSpacing: string; transform: "uppercase" | "none";
}> = {
  "wordmark-sans-bold":    { family: 'var(--font-sans), system-ui, sans-serif',  weight: 800, italic: false, letterSpacing: "0.02em",  transform: "uppercase" },
  "wordmark-serif":        { family: 'var(--font-serif), Georgia, serif',        weight: 600, italic: false, letterSpacing: "0.04em",  transform: "uppercase" },
  "wordmark-italic-serif": { family: 'var(--font-serif), Georgia, serif',        weight: 500, italic: true,  letterSpacing: "0",       transform: "none" },
  "wordmark-rounded":      { family: 'var(--font-sans), system-ui, sans-serif',  weight: 800, italic: false, letterSpacing: "-0.01em", transform: "uppercase" },
  "wordmark-condensed":    { family: 'var(--font-sans), system-ui, sans-serif',  weight: 700, italic: false, letterSpacing: "0.06em",  transform: "uppercase" },
  "monogram-V":            { family: 'var(--font-sans), system-ui, sans-serif',  weight: 700, italic: false, letterSpacing: "1.2px",   transform: "uppercase" },
  "monogram-circle":       { family: 'var(--font-sans), system-ui, sans-serif',  weight: 800, italic: false, letterSpacing: "1px",     transform: "uppercase" },
};

const STYLES: SpecimenStyle[] = [
  "wordmark-sans-bold", "wordmark-serif", "wordmark-italic-serif",
  "wordmark-rounded", "wordmark-condensed",
];

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

/** Stable typographic style picker keyed on an id — until raster mark images land. */
export function pickSpecimenStyle(idOrName: string): SpecimenStyle {
  return STYLES[hashString(idOrName) % STYLES.length];
}

function colorVar(c: SpecimenColor) {
  return { ink: "var(--ink)", stamp: "var(--stamp)", ok: "var(--ok)" }[c];
}

const DIMENSIONS = {
  xs: { w: 64,  h: 40 },
  sm: { w: 240, h: 140 },
  md: { w: 320, h: 200 },
  lg: { w: 520, h: 280 },
} as const;
export type SpecimenSize = keyof typeof DIMENSIONS;

type MarkSpecimenProps = {
  info?: SpecimenInfo;
  /** Convenience: provide name + id and a style is picked deterministically. */
  fallbackText?: string;
  fallbackKey?: string;
  size?: SpecimenSize;
  frame?: boolean;
  plain?: boolean;
  className?: string;
  /** True = derived label, not the real (540) wordmark. Renders a "PLACEHOLDER"
   * watermark and uses faded ink so the user can tell at a glance. */
  placeholder?: boolean;
};

export function MarkSpecimen({
  info, fallbackText, fallbackKey, size = "md", frame = true, plain = false, className = "", placeholder = false,
}: MarkSpecimenProps) {
  const s: SpecimenInfo = info ?? {
    style: pickSpecimenStyle(fallbackKey ?? fallbackText ?? ""),
    color: placeholder ? "ink" : "ink",
    text: fallbackText ?? "—",
  };
  const dims = DIMENSIONS[size];

  // If a real raster specimen URL is present, render it.
  //
  // CSS recipe: position the <img> absolutely with `inset` so the box
  // size is defined symmetrically on both axes (percentage inset values
  // resolve against the parent's width for left/right and height for
  // top/bottom — unlike `padding`, where ALL percentages resolve against
  // width). object-fit:contain then scales the raster's content to fit
  // within that box without overflow.
  //
  // Earlier attempts that used `padding: 14% 7%` on the wrapper failed
  // because `py-[14%]` is computed off the WIDTH per CSS spec; on a
  // 388px-wide hero plate it added ~108px of vertical padding, pushing
  // the plate to a 388×540 portrait box (the aspect-ratio rule was
  // overridden by the padding-induced min-height) and visibly cropping
  // tall logos like the MTV VÀNG diamond at the bottom.
  if (s.imageUrl) {
    const img = (
      <img
        src={s.imageUrl}
        alt={s.text}
        style={{
          position: "absolute",
          top: "8%",
          bottom: "8%",
          left: "6%",
          right: "6%",
          width: "auto",
          height: "auto",
          maxWidth: "88%",
          maxHeight: "84%",
          margin: "auto",
          objectFit: "contain",
          display: "block",
        }}
      />
    );
    return plain ? img : (
      <SpecimenPlate aspect={`${dims.w}/${dims.h}`} frame={frame} className={className}>
        {img}
      </SpecimenPlate>
    );
  }

  const inner =
    s.style === "monogram-V" ? renderMonogramV(s)
    : s.style === "monogram-circle" ? renderMonogramCircle(s)
    : renderWordmark(s);

  if (plain) return <div className={className}>{inner}</div>;
  return (
    <SpecimenPlate aspect={`${dims.w}/${dims.h}`} frame={frame} className={className} placeholder={placeholder}>
      {inner}
    </SpecimenPlate>
  );
}

/* ---- renderers ---- */

function renderWordmark(s: SpecimenInfo) {
  const def = FONTS[s.style];
  const display = def.transform === "uppercase" ? s.text.toUpperCase() : s.text;
  const vbW = 520, vbH = 280;
  const fontSize = vbH * 0.62;
  const maxTextWidth = vbW * 0.94;
  return (
    <svg
      viewBox={`0 0 ${vbW} ${vbH}`}
      preserveAspectRatio="xMidYMid meet"
      style={{ width: "86%", height: "72%", display: "block" }}
      role="img"
      aria-label={s.text}
    >
      <text
        x={vbW / 2} y={vbH / 2}
        textAnchor="middle" dominantBaseline="central"
        fontFamily={def.family} fontWeight={def.weight}
        fontStyle={def.italic ? "italic" : "normal"}
        letterSpacing={def.letterSpacing}
        fontSize={fontSize} fill={colorVar(s.color)}
        textLength={display.length > 4 ? maxTextWidth : undefined}
        lengthAdjust="spacingAndGlyphs"
      >
        {display}
      </text>
    </svg>
  );
}

function renderMonogramV(s: SpecimenInfo) {
  const c = colorVar(s.color);
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style={{ width: "60%", height: "75%" }} role="img" aria-label={s.text}>
      <path d="M14 22 L50 78 L86 22" fill="none" stroke={c} strokeWidth="11" strokeLinejoin="miter" />
      <text
        x="50" y="94" textAnchor="middle"
        fontFamily="var(--font-sans)" fontWeight={700} fontSize={9}
        letterSpacing="1.2" fill={c}
      >
        {s.text.toUpperCase()}
      </text>
    </svg>
  );
}

function renderMonogramCircle(s: SpecimenInfo) {
  const c = colorVar(s.color);
  return (
    <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style={{ width: "60%", height: "78%" }} role="img" aria-label={s.text}>
      <circle cx="50" cy="50" r="40" fill="none" stroke={c} strokeWidth="4" />
      <text
        x="50" y="50" textAnchor="middle" dominantBaseline="central"
        fontFamily="var(--font-sans)" fontWeight={800} fontSize={32}
        letterSpacing="1" fill={c}
      >
        {s.text}
      </text>
    </svg>
  );
}

/* ---- plate frame ---- */

export function SpecimenPlate({
  children, aspect = "8/5", frame = true, className = "", placeholder = false,
}: {
  children: React.ReactNode;
  aspect?: string;
  frame?: boolean;
  className?: string;
  placeholder?: boolean;
}) {
  return (
    <div
      className={`grid place-items-center relative overflow-hidden ${frame ? "bg-paper border border-line rounded" : "bg-transparent"} ${className}`}
      style={{ aspectRatio: aspect.replace("/", " / ") }}
    >
      {frame && (
        <>
          <CornerTick pos="tl" />
          <CornerTick pos="tr" />
          <CornerTick pos="bl" />
          <CornerTick pos="br" />
        </>
      )}
      {/* Subdue the specimen content + watermark when it's a derived placeholder. */}
      <div className={placeholder ? "opacity-50 grid place-items-center w-full h-full" : "grid place-items-center w-full h-full"}>
        {children}
      </div>
      {placeholder && (
        <div
          className="absolute bottom-1 left-1/2 -translate-x-1/2 text-[10px] font-mono tracking-[0.12em] uppercase text-mute pointer-events-none"
          aria-label="Specimen image not yet extracted"
        >
          no specimen on file
        </div>
      )}
    </div>
  );
}

function CornerTick({ pos }: { pos: "tl" | "tr" | "bl" | "br" }) {
  const style: React.CSSProperties = { position: "absolute", width: 8, height: 8, opacity: 0.35 };
  const borderColor = "var(--mute)";
  const map: Record<typeof pos, React.CSSProperties> = {
    tl: { top: 4, left: 4, borderTop: `1px solid ${borderColor}`, borderLeft: `1px solid ${borderColor}` },
    tr: { top: 4, right: 4, borderTop: `1px solid ${borderColor}`, borderRight: `1px solid ${borderColor}` },
    bl: { bottom: 4, left: 4, borderBottom: `1px solid ${borderColor}`, borderLeft: `1px solid ${borderColor}` },
    br: { bottom: 4, right: 4, borderBottom: `1px solid ${borderColor}`, borderRight: `1px solid ${borderColor}` },
  };
  return <div style={{ ...style, ...map[pos] }} />;
}
