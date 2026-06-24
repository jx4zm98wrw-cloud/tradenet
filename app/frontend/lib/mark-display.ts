/** Picks the best visual label for a mark.
 *
 * Real data status: both A-files (applications) and B-files (registrations)
 * can carry a WIPO field-540 wordmark, and the backend now resolves a unified
 * `mark_name` (mark_sample | domestic.mark_text | madrid.mark_text), denormalized
 * on `trademarks`. `mark_name` is null only for genuinely figurative marks with
 * no transcribed name anywhere. Raster logo specimens are also populated
 * (`logo_path`). This helper returns the best available label plus an
 * `isPlaceholder` flag so the UI can render placeholders with a subdued
 * treatment + visible "no specimen" hint, instead of pretending an applicant
 * name is a real wordmark.
 *
 * Wordmark precedence (first non-empty, trimmed, ≥2 chars wins):
 *   1. markText override (caller-supplied, e.g. WIPO/domestic mark_text)
 *   2. m.mark_name (the denormalized resolved name)
 *   3. m.mark_sample (defensive fallback)
 *
 * Render precedence:
 *   - logo_path present → raster specimen (isPlaceholder=false); label =
 *     wordmark || id || "" (NO applicant fallback)
 *   - no logo, wordmark present → { text: wordmark, isPlaceholder: false }
 *   - no logo, no wordmark → { text: "(figurative mark)", isPlaceholder: true }
 *     (the identifier still carries the app/cert/madrid number as a sub-label)
 */
import type { Trademark } from "./api";

export type MarkDisplay = {
  /** What to render inside the specimen plate. */
  text: string;
  /** True when `text` is a placeholder (no real wordmark / image). */
  isPlaceholder: boolean;
  /** Short identifier (app/cert/madrid #) shown as a sub-label on placeholders. */
  identifier: string | null;
  /** URL of the extracted logo PNG when one is on file. Undefined otherwise,
   * which signals the caller to fall back to the typographic specimen. */
  imageUrl?: string;
};

export function markDisplay(
  m: Pick<
    Trademark,
    | "mark_sample"
    | "mark_name"
    | "application_number"
    | "certificate_number"
    | "madrid_number"
    | "logo_path"
  >,
  /** Caller-supplied mark name override (e.g. madrid_records.mark_text /
   * domestic_records.mark_text). Wins over the denormalized `mark_name`. */
  markText?: string | null,
): MarkDisplay {
  const id =
    m.application_number ??
    m.certificate_number ??
    m.madrid_number ??
    null;

  // Resolved wordmark: first non-empty trimmed value, ≥2 chars to count.
  const wordmark =
    [markText, m.mark_name, m.mark_sample]
      .map((v) => v?.trim() ?? "")
      .find((v) => v.length >= 2) ?? "";

  // Real raster logo extracted from the PDF — highest priority. Once present,
  // it's a real specimen so isPlaceholder=false. Label is the wordmark, then
  // the identifier; never the applicant name.
  if (m.logo_path) {
    const url = `/static/image/${m.logo_path}`;
    const label = wordmark || id || "";
    return { text: label, isPlaceholder: false, identifier: id, imageUrl: url };
  }

  // No logo, real wordmark present.
  if (wordmark) {
    return { text: wordmark, isPlaceholder: false, identifier: id };
  }

  // No logo, no wordmark — genuinely figurative. Name is always the literal
  // placeholder; the identifier carries the app/cert/madrid number as a sub-label.
  return { text: "(figurative mark)", isPlaceholder: true, identifier: id };
}
