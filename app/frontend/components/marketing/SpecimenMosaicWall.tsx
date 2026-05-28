/**
 * 3×3 grid of fake trademark specimens for the left pane of `/login`.
 *
 * Lifted verbatim from the prototype's `.login-stamp-mosaic` block — the
 * cells are inline SVG so we don't need any image assets in /public, and
 * the colors flow from the existing `--ink` / `--stamp` / `--stamp-2`
 * design tokens so theme switching keeps the wall consistent with the
 * rest of the marketing surface.
 *
 * Two cells are tagged `accent` so they pick up the oxblood-tinted
 * background via `.login-stamp-cell.accent` in `marketing.css`. The
 * accent positions match the prototype (cell 2 = VEXIS, cell 7 =
 * NUROFEN+).
 *
 * Server component — pure SVG, no state, no interactivity.
 *
 * Why "fake" names? Real client names would imply endorsement; the
 * prototype mints six made-up wordmarks (NEUREX, VEXIS, Masan, VEXARIS,
 * NUROFEN+, ZENPHARM, BIVAXIS) plus one Λ-shaped icon-only cell and one
 * "VX" circle mark.  All evoke pharma / industrial trademark styling
 * (the categories that drive the bulk of NOIP gazette filings) without
 * any specific real owner.
 */

type Cell = { kind: "text"; text: string; font: "sans" | "serif" | "italic" | "wide"; accent?: boolean }
  | { kind: "icon-circle"; text: string }
  | { kind: "icon-lambda" };

// Order matches the prototype HTML. The two `accent: true` cells get
// the oxblood-tinted background via .login-stamp-cell.accent
const CELLS: Cell[] = [
  { kind: "text", text: "NEUREX", font: "sans" },
  { kind: "text", text: "VEXIS", font: "serif", accent: true },
  { kind: "icon-lambda" },
  { kind: "text", text: "Masan", font: "italic" },
  { kind: "icon-circle", text: "VX" },
  { kind: "text", text: "VEXARIS", font: "wide" },
  { kind: "text", text: "NUROFEN+", font: "sans", accent: true },
  { kind: "text", text: "ZENPHARM", font: "sans" },
  { kind: "text", text: "BIVAXIS", font: "serif" },
];

export function SpecimenMosaicWall() {
  return (
    <div className="login-stamp-mosaic" aria-hidden="true">
      {CELLS.map((cell, i) => (
        <div
          key={i}
          className={`login-stamp-cell${"accent" in cell && cell.accent ? " accent" : ""}`}
        >
          <SpecimenSvg cell={cell} />
        </div>
      ))}
    </div>
  );
}

function SpecimenSvg({ cell }: { cell: Cell }) {
  if (cell.kind === "icon-lambda") {
    // Big oxblood-stroke V/Λ shape — pure icon, no text
    return (
      <svg viewBox="0 0 100 60">
        <path d="M30 12 L50 48 L70 12" fill="none" stroke="var(--ink)" strokeWidth={6} strokeLinejoin="miter" />
      </svg>
    );
  }
  if (cell.kind === "icon-circle") {
    // Outlined circle with monogram inside
    return (
      <svg viewBox="0 0 100 60">
        <circle cx={50} cy={30} r={20} fill="none" stroke="var(--stamp)" strokeWidth={2.5} />
        <text
          x={50}
          y={30}
          textAnchor="middle"
          dominantBaseline="central"
          fontFamily="var(--font-sans), 'Be Vietnam Pro', sans-serif"
          fontWeight={800}
          fontSize={16}
          fill="var(--stamp)"
        >
          {cell.text}
        </text>
      </svg>
    );
  }
  // text variants
  const props = textProps(cell.font);
  return (
    <svg viewBox="0 0 100 60">
      <text
        x={50}
        y={30}
        textAnchor="middle"
        dominantBaseline="central"
        fill={cell.accent ? "var(--stamp)" : "var(--ink)"}
        {...props}
      >
        {cell.text}
      </text>
    </svg>
  );
}

/**
 * Font / weight / size combos straight from the prototype — each tweaks
 * the apparent "brand identity" of the cell so the wall reads like a
 * collection of distinct marks instead of variations on a single label.
 */
function textProps(font: "sans" | "serif" | "italic" | "wide") {
  switch (font) {
    case "sans":
      return {
        fontFamily: "var(--font-sans), 'Be Vietnam Pro', sans-serif",
        fontWeight: 800,
        fontSize: 18,
      } as const;
    case "serif":
      return {
        fontFamily: "var(--font-serif), 'Source Serif 4', serif",
        fontWeight: 600,
        fontSize: 18,
      } as const;
    case "italic":
      return {
        fontFamily: "var(--font-serif), 'Source Serif 4', serif",
        fontWeight: 500,
        fontStyle: "italic" as const,
        fontSize: 20,
      } as const;
    case "wide":
      return {
        fontFamily: "var(--font-sans), 'Be Vietnam Pro', sans-serif",
        fontWeight: 700,
        fontSize: 14,
        letterSpacing: 2,
      } as const;
  }
}
