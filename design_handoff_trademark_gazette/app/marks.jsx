// Mark specimen renderer + small visual utilities
// Renders stylized wordmarks/monograms so each trademark looks like a real specimen
// rather than the original demo's "SAMSUNG in serif text".

const SPECIMEN_FONTS = {
  "wordmark-sans-bold":     { family: '"Be Vietnam Pro", system-ui, sans-serif', weight: 800, italic: false, letterSpacing: "0.02em", transform: "uppercase" },
  "wordmark-serif":         { family: '"Source Serif 4", Georgia, serif',        weight: 600, italic: false, letterSpacing: "0.04em", transform: "uppercase" },
  "wordmark-italic-serif":  { family: '"Source Serif 4", Georgia, serif',        weight: 500, italic: true,  letterSpacing: "0",       transform: "none" },
  "wordmark-rounded":       { family: '"Be Vietnam Pro", system-ui, sans-serif', weight: 800, italic: false, letterSpacing: "-0.01em", transform: "uppercase" },
  "wordmark-condensed":     { family: '"Be Vietnam Pro", system-ui, sans-serif', weight: 700, italic: false, letterSpacing: "0.06em", transform: "uppercase" },
};

function specimenColor(c) {
  if (c === "stamp") return "var(--stamp)";
  if (c === "ok") return "var(--ok)";
  return "var(--ink)";
}

// Fits text by measuring – simple version: pick font-size based on string length and box width
function fitFontSize(text, boxW, boxH, base) {
  const n = (text || "").length;
  const byWidth = boxW / (n * 0.55);
  const byHeight = boxH * 0.55;
  return Math.min(byWidth, byHeight, base);
}

function MarkSpecimen({ mark, size = "md", frame = true, plain = false }) {
  const s = mark.specimen || { style: "wordmark-sans-bold", color: "ink", text: mark.name };
  const fontDef = SPECIMEN_FONTS[s.style] || SPECIMEN_FONTS["wordmark-sans-bold"];
  const dims = { xs: { w: 64, h: 40 }, sm: { w: 240, h: 140 }, md: { w: 320, h: 200 }, lg: { w: 520, h: 280 } }[size];

  const isMonogram = s.style.startsWith("monogram");
  const color = specimenColor(s.color);

  const renderWordmark = () => {
    const text = s.text || "";
    const display = fontDef.transform === "uppercase" ? text.toUpperCase() : text;
    const vbW = 520, vbH = 280;
    // Pick a fontSize that fits height, then force text width via textLength to fit width
    const fontSize = vbH * 0.62;
    const maxTextWidth = vbW * 0.94;
    return (
      <svg viewBox={`0 0 ${vbW} ${vbH}`} preserveAspectRatio="xMidYMid meet"
        style={{ width: "86%", height: "72%", display: "block" }} role="img" aria-label={text}>
        <text x={vbW / 2} y={vbH / 2} textAnchor="middle" dominantBaseline="central"
          fontFamily={fontDef.family} fontWeight={fontDef.weight}
          fontStyle={fontDef.italic ? "italic" : "normal"}
          letterSpacing={fontDef.letterSpacing}
          fontSize={fontSize} fill={color}
          textLength={display.length > 4 ? maxTextWidth : undefined}
          lengthAdjust="spacingAndGlyphs">
          {display}
        </text>
      </svg>
    );
  };

  const renderMonogramV = () => (
    <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style={{ width: "60%", height: "75%" }}>
      <path d="M14 22 L50 78 L86 22" fill="none" stroke={color} strokeWidth="11" strokeLinejoin="miter" strokeLinecap="butt"/>
      <text x="50" y="94" textAnchor="middle" fontFamily={fontDef.family} fontWeight="700"
        fontSize="9" letterSpacing="1.2" fill={color}>{(s.text || "").toUpperCase()}</text>
    </svg>
  );

  const renderMonogramCircle = () => (
    <svg viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" style={{ width: "60%", height: "78%" }}>
      <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="4"/>
      <text x="50" y="50" textAnchor="middle" dominantBaseline="central"
        fontFamily='"Be Vietnam Pro", sans-serif' fontWeight="800" fontSize="32"
        letterSpacing="1" fill={color}>{s.text || ""}</text>
    </svg>
  );

  let inner;
  if (s.style === "monogram-V") inner = renderMonogramV();
  else if (s.style === "monogram-circle") inner = renderMonogramCircle();
  else inner = renderWordmark();

  if (plain) return inner;

  return (
    <div className="specimen-frame" style={{
      width: "100%", aspectRatio: `${dims.w} / ${dims.h}`,
      display: "grid", placeItems: "center",
      background: frame ? "var(--paper)" : "transparent",
      border: frame ? "1px solid var(--line)" : "none",
      borderRadius: 6,
      position: "relative",
      overflow: "hidden",
    }}>
      {frame && (
        <>
          <CornerTick pos="tl" />
          <CornerTick pos="tr" />
          <CornerTick pos="bl" />
          <CornerTick pos="br" />
        </>
      )}
      {inner}
    </div>
  );
}

function CornerTick({ pos }) {
  const sty = { position: "absolute", width: 8, height: 8, opacity: 0.35 };
  const stroke = "var(--mute)";
  if (pos === "tl") Object.assign(sty, { top: 4, left: 4, borderTop: `1px solid ${stroke}`, borderLeft: `1px solid ${stroke}` });
  if (pos === "tr") Object.assign(sty, { top: 4, right: 4, borderTop: `1px solid ${stroke}`, borderRight: `1px solid ${stroke}` });
  if (pos === "bl") Object.assign(sty, { bottom: 4, left: 4, borderBottom: `1px solid ${stroke}`, borderLeft: `1px solid ${stroke}` });
  if (pos === "br") Object.assign(sty, { bottom: 4, right: 4, borderBottom: `1px solid ${stroke}`, borderRight: `1px solid ${stroke}` });
  return <div style={sty}></div>;
}

// ----- Small visual utilities -----

const FLAG = { VN: "🇻🇳", CN: "🇨🇳", US: "🇺🇸", KR: "🇰🇷", JP: "🇯🇵", SG: "🇸🇬", GB: "🇬🇧", DE: "🇩🇪", IN: "🇮🇳", FR: "🇫🇷", TH: "🇹🇭" };
function Flag({ code, size = 16 }) {
  return <span style={{ fontSize: size, lineHeight: 1, fontFamily: '"Apple Color Emoji","Segoe UI Emoji",sans-serif' }}>{FLAG[code] || "🏳️"}</span>;
}

function ClassChip({ n, matched = false, dim = false }) {
  const cls = window.NICE_CLASSES[n];
  if (!cls) return null;
  const group = cls.group; // goods | services
  let bg, fg, bd;
  if (dim) {
    bg = "transparent"; fg = "var(--fade)"; bd = "var(--line)";
  } else if (matched) {
    bg = "var(--stamp-2)"; fg = "var(--stamp)"; bd = "var(--stamp-line)";
  } else if (group === "services") {
    bg = "oklch(0.96 0.025 220)"; fg = "oklch(0.42 0.10 220)"; bd = "oklch(0.88 0.04 220)";
  } else {
    bg = "oklch(0.97 0.02 95)"; fg = "oklch(0.45 0.09 80)"; bd = "oklch(0.88 0.04 90)";
  }
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: "1px 6px 1px 4px",
      background: bg, color: fg, border: `1px solid ${bd}`,
      borderRadius: 4, fontSize: 11, fontFamily: '"JetBrains Mono", monospace',
      fontWeight: 500, fontVariantNumeric: "tabular-nums",
      whiteSpace: "nowrap",
    }}>
      <span style={{ fontWeight: 700 }}>{String(n).padStart(2, "0")}</span>
    </span>
  );
}

function ClassChipFull({ n, matched = false }) {
  const cls = window.NICE_CLASSES[n];
  if (!cls) return null;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 6,
      padding: "3px 8px",
      background: matched ? "var(--stamp-2)" : "var(--paper-2)",
      color: matched ? "var(--stamp)" : "var(--ink-2)",
      border: `1px solid ${matched ? "var(--stamp-line)" : "var(--line)"}`,
      borderRadius: 5, fontSize: 12,
    }}>
      <span style={{ fontFamily: '"JetBrains Mono", monospace', fontWeight: 700, fontSize: 11 }}>
        {String(n).padStart(2, "0")}
      </span>
      <span style={{ color: matched ? "var(--stamp)" : "var(--ink-2)" }}>{cls.label}</span>
    </span>
  );
}

function SimilarityRing({ score, size = 36 }) {
  // score 0..1
  const r = (size - 4) / 2;
  const c = 2 * Math.PI * r;
  const dash = c * score;
  let color = "var(--ok)";
  if (score >= 0.85) color = "var(--stamp)";
  else if (score >= 0.7) color = "var(--warn)";
  const pct = Math.round(score * 100);
  return (
    <div style={{ position: "relative", width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: "rotate(-90deg)" }}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--line)" strokeWidth="3" />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="3"
          strokeDasharray={`${dash} ${c}`} strokeLinecap="round" />
      </svg>
      <div style={{
        position: "absolute", inset: 0, display: "grid", placeItems: "center",
        fontFamily: '"JetBrains Mono", monospace', fontSize: size * 0.28, fontWeight: 700,
        color, fontVariantNumeric: "tabular-nums",
      }}>{pct}</div>
    </div>
  );
}

function Pill({ children, tone = "ink", soft = false, size = "md" }) {
  const tones = {
    ink:   { bg: "var(--paper-2)",   fg: "var(--ink-2)",  bd: "var(--line)" },
    stamp: { bg: "var(--stamp-2)",   fg: "var(--stamp)",  bd: "var(--stamp-line)" },
    ok:    { bg: "var(--ok-2)",      fg: "var(--ok)",     bd: "oklch(0.85 0.05 165)" },
    warn:  { bg: "var(--warn-2)",    fg: "oklch(0.45 0.13 75)", bd: "oklch(0.85 0.07 75)" },
    mute:  { bg: "transparent",      fg: "var(--mute)",   bd: "var(--line)" },
    A:     { bg: "oklch(0.96 0.025 220)", fg: "oklch(0.42 0.10 220)", bd: "oklch(0.88 0.04 220)" },
    B:     { bg: "oklch(0.96 0.03 300)",  fg: "oklch(0.42 0.13 300)", bd: "oklch(0.88 0.05 300)" },
  };
  const t = tones[tone] || tones.ink;
  const pad = size === "sm" ? "1px 6px" : "2px 8px";
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: pad, background: soft ? "transparent" : t.bg, color: t.fg,
      border: `1px solid ${t.bd}`, borderRadius: 999,
      fontSize: size === "sm" ? 10.5 : 11.5, fontWeight: 600, letterSpacing: 0.01,
      lineHeight: 1.3, whiteSpace: "nowrap",
    }}>{children}</span>
  );
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}
function fmtDateShort(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

Object.assign(window, {
  MarkSpecimen, Flag, ClassChip, ClassChipFull, SimilarityRing, Pill,
  fmtDate, fmtDateShort,
});
