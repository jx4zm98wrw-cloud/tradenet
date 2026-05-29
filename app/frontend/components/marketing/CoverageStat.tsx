/**
 * One stat tile in the 4-up `.coverage-stats` row at the top of
 * `/coverage`. Server component — purely structural, no client state.
 *
 * Markup mirrors `.coverage-stat` from the prototype (see
 * `design_handoff_tradenet_marketing/Tradenet - Marketing.html` lines
 * 686-707). The optional `valueSuffix` renders inline at 0.5em with
 * muted color, matching the prototype's inline `<span style="…">` —
 * those styles are kept inline (not promoted to a class) because they
 * appear only inside coverage stat / DQ card values and would otherwise
 * pollute the shared sheet.
 */
type Props = {
  label: string;
  /** The big serif numeral / phrase. */
  value: string;
  /** Optional muted suffix rendered inside the value at 0.5em. */
  valueSuffix?: string;
  meta: string;
};

export function CoverageStat({ label, value, valueSuffix, meta }: Props) {
  return (
    <div className="coverage-stat">
      <div className="coverage-stat-label">{label}</div>
      <div className="coverage-stat-value">
        {value}
        {valueSuffix ? (
          <span style={{ fontSize: "0.5em", color: "var(--mute)" }}>
            {valueSuffix}
          </span>
        ) : null}
      </div>
      <div className="coverage-stat-meta">{meta}</div>
    </div>
  );
}
