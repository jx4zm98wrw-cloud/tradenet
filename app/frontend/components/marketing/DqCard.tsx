/**
 * One data-quality card in the 3-up `.dq-grid` near the bottom of
 * `/coverage`. Server component — purely structural, no client state.
 *
 * Markup mirrors `.dq-card` from the prototype
 * (`design_handoff_tradenet_marketing/Tradenet - Marketing.html` lines
 * 826-862). The fill bar's width comes through as inline style
 * `width: {fillPct}%`. `fillColorVar` selects between the default
 * oxblood (`.dq-bar-fill` baseline), `var(--ok)`, or `var(--warn)` —
 * matching the prototype's inline `style="background: var(--ok)"`
 * overrides on specific cards.
 */
type Props = {
  heading: string;
  value: string;
  valueSuffix?: string;
  /** 0–100. Goes straight into `width: {pct}%`. */
  fillPct: number;
  /**
   * Token name for the bar color (`"ok"` / `"warn"`). Omit to keep the
   * default oxblood from `.dq-bar-fill`.
   */
  fillColorVar?: "ok" | "warn";
  meta: string;
};

export function DqCard({
  heading,
  value,
  valueSuffix,
  fillPct,
  fillColorVar,
  meta,
}: Props) {
  const fillStyle: React.CSSProperties = { width: `${fillPct}%` };
  if (fillColorVar) {
    fillStyle.background = `var(--${fillColorVar})`;
  }
  return (
    <div className="dq-card">
      <div className="dq-card-h">{heading}</div>
      <div className="dq-card-value">
        {value}
        {valueSuffix ? (
          <span style={{ fontSize: "0.5em", color: "var(--mute)" }}>
            {valueSuffix}
          </span>
        ) : null}
      </div>
      <div className="dq-bar">
        <div className="dq-bar-fill" style={fillStyle} />
      </div>
      <p className="dq-card-meta">{meta}</p>
    </div>
  );
}
