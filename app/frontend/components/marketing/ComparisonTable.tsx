/**
 * Feature-comparison table on `/pricing`.
 *
 * Server component. Renders the prototype's
 * `<div class="compare-table-wrap"><table class="compare-table">…` markup
 * directly from a typed sections array (each section becomes a
 * `compare-section-row` header followed by its rows). Sentinel cell values
 * `"check"` / `"dash"` render as the prototype's ✓ / — glyphs; every other
 * string is plain text.
 *
 * The Firm column header + Firm cells carry the `featured` class so the
 * CSS gradient highlight applies.
 */
import type {
  ComparisonRow,
  ComparisonSection,
} from "@/app/(marketing)/_content/pricing";

type Props = {
  sections: ReadonlyArray<ComparisonSection>;
};

/** Render one tier-column cell, with check/dash sentinels expanded. */
function Cell({ value }: { value: string }) {
  if (value === "check") return <span className="check">✓</span>;
  if (value === "dash") return <span className="dash">—</span>;
  return <>{value}</>;
}

export function ComparisonTable({ sections }: Props) {
  return (
    <div className="compare-table-wrap">
      <table className="compare-table">
        <thead>
          <tr>
            <th>Feature</th>
            <th>Solo</th>
            <th className="featured">Firm</th>
            <th>Enterprise</th>
          </tr>
        </thead>
        <tbody>
          {sections.map((section) => (
            // Use the section label as a stable key — it's a slug-shaped
            // string that's unique per section in the typed content.
            <SectionRows key={section.label} section={section} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SectionRows({ section }: { section: ComparisonSection }) {
  return (
    <>
      <tr className="compare-section-row">
        <td colSpan={4}>{section.label}</td>
      </tr>
      {section.rows.map((row: ComparisonRow) => (
        <tr key={row.feature}>
          <td className="row-label">{row.feature}</td>
          <td>
            <Cell value={row.solo} />
          </td>
          <td className="featured">
            <Cell value={row.firm} />
          </td>
          <td>
            <Cell value={row.enterprise} />
          </td>
        </tr>
      ))}
    </>
  );
}
