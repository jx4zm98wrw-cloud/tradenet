/**
 * Bordered, uppercase-mono-headed reference table used throughout the
 * docs articles (Vienna categories, Nice classes, INID codes, glossary).
 *
 * Server component. `rows` is a 2-D array of ReactNodes so MDX authors
 * can embed `<strong>`, `<span class="mono">`, and inline links inside
 * cells.
 */
import type { ReactNode } from "react";

type Props = {
  headers: ReadonlyArray<string>;
  rows: ReadonlyArray<ReadonlyArray<ReactNode>>;
};

export function DocsTable({ headers, rows }: Props) {
  return (
    <div className="docs-table-wrap">
      <table className="docs-table">
        <thead>
          <tr>
            {headers.map((h) => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, ri) => (
            <tr key={ri}>
              {row.map((cell, ci) => (
                <td key={ci}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
