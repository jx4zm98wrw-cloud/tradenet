/** Picks the best visual label for a mark.
 *
 * Real data status: both A-files (applications) and B-files (registrations)
 * can carry a WIPO field-540 wordmark — extraction scans the B/registration
 * form first, falls back to the A/application form, and `mark_sample` is null
 * only when NEITHER transcribed a 540. (~97% of A-files have one in the source
 * data; the PDF parser misses some, so they're backfilled from the edited CSVs.)
 * Raster logo
 * specimens are also populated (`logo_path`). This helper returns the best
 * available label plus an `isPlaceholder` flag so the UI can render
 * placeholders with a subdued treatment + visible "no specimen" hint, instead
 * of pretending a squeezed applicant-name is a real wordmark.
 *
 * Precedence:
 *   1. imageUrl (real raster — not yet populated; future-proof)
 *   2. mark_sample, 2–24 chars (real WIPO 540 wordmark — A or B files)
 *   3. derived label from applicant_name with Vietnamese / Latin company
 *      prefixes stripped
 *   4. application / certificate / Madrid number tail
 *   5. literal "—"
 */
import type { Trademark } from "./api";

/** Common entity prefixes (VN + Latin); stripped when deriving display labels. */
const ENTITY_PREFIXES: RegExp[] = [
  /^c[ôo]ng\s+ty\s+c[ổo]\s+ph[ầa]n\s+t[ậa]p\s+[đd]o[àa]n\s+/i,
  /^c[ôo]ng\s+ty\s+c[ổo]\s+ph[ầa]n\s+/i,
  /^c[ôo]ng\s+ty\s+tnhh\s+(?:m[ộo]t\s+th[àa]nh\s+vi[êe]n\s+)?/i,
  /^c[ôo]ng\s+ty\s+h[ợo]p\s+danh\s+/i,
  /^c[ôo]ng\s+ty\s+/i,
  /^t[ổo]ng\s+c[ôo]ng\s+ty\s+/i,
  /^t[ậa]p\s+[đd]o[àa]n\s+/i,
  /^doanh\s+nghi[ệe]p\s+(?:t[ưu]\s+nh[âa]n\s+)?/i,
  /^x[íi]\s+nghi[ệe]p\s+/i,
  /^h[ộo]\s+kinh\s+doanh\s+/i,
  /^cty\.?\s+/i,
  /^dntn\s+/i,
  // Surnames stripped only for short personal names — handled later.
];

const TRAILING_SUFFIXES: RegExp[] = [
  /,?\s+(?:co\.|company)\s*,?\s*ltd\.?$/i,
  /,?\s+(?:co\.|company)\s*,?\s*l\.?l\.?c\.?$/i,
  /,?\s+(?:pte\.|pty\.|pvt\.)\s*ltd\.?$/i,
  /,?\s+inc\.?$/i, /,?\s+incorporated$/i,
  /,?\s+ltd\.?$/i, /,?\s+limited$/i,
  /,?\s+corp\.?$/i, /,?\s+corporation$/i,
  /,?\s+gmbh$/i, /,?\s+ag$/i, /,?\s+s\.?a\.?$/i, /,?\s+s\.?a\.?s\.?$/i, /,?\s+s\.?r\.?l\.?$/i,
  /,?\s+plc$/i, /,?\s+b\.?v\.?$/i, /,?\s+oy$/i, /,?\s+aps$/i,
];

function stripEntityPrefixes(name: string): string {
  let s = name.trim();
  for (let i = 0; i < 3; i++) {
    const before = s;
    for (const re of ENTITY_PREFIXES) s = s.replace(re, "").trim();
    for (const re of TRAILING_SUFFIXES) s = s.replace(re, "").trim();
    if (s === before) break;
  }
  return s.trim();
}

/** Compact a long applicant name into a wordmark-sized label.
 * Returns the first ≤2 significant words after stripping entity prefixes.
 * Caps at 16 chars; falls back to first 16 chars if no clean split found. */
function compactApplicantName(name: string): string {
  const stripped = stripEntityPrefixes(name);
  if (!stripped) return name.slice(0, 16);
  // For 1–3-word names: keep as-is if ≤16 chars.
  if (stripped.length <= 16) return stripped;
  // Otherwise take first two words.
  const words = stripped.split(/\s+/).slice(0, 2).join(" ");
  return (words.length <= 16 ? words : words.slice(0, 15) + "…").trim();
}

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

export function markDisplay(m: Pick<Trademark, "mark_sample" | "applicant_name" | "application_number" | "certificate_number" | "madrid_number" | "logo_path">): MarkDisplay {
  const id =
    m.application_number ??
    m.certificate_number ??
    m.madrid_number ??
    null;

  // 0. Real raster logo extracted from the PDF — highest priority. Once present,
  // it's a real specimen so isPlaceholder=false regardless of mark_sample.
  //
  // Label precedence when no mark_sample exists:
  //   1. mark_sample (the WIPO 540 wordmark)
  //   2. compactApplicantName(applicant_name) — human-readable, e.g. "ACME"
  //   3. id (application/cert/madrid number) — last resort, machine-readable
  //
  // Previously fell straight from mark_sample to id, which made CmdK
  // results read like "4-2026-09350" instead of the applicant name when
  // an A-file had a logo but no 540 field. The compacted applicant name is
  // what every other surface (search grid, mark detail hero) already shows.
  if (m.logo_path) {
    const url = `/static/image/${m.logo_path}`;
    const sample = m.mark_sample?.trim();
    const compacted = m.applicant_name ? compactApplicantName(m.applicant_name) : "";
    const label = sample || compacted || id || "";
    return { text: label, isPlaceholder: false, identifier: id, imageUrl: url };
  }

  // 1. Real wordmark in field 540
  if (m.mark_sample) {
    const t = m.mark_sample.trim();
    if (t.length >= 2 && t.length <= 24) {
      return { text: t, isPlaceholder: false, identifier: id };
    }
  }

  // 2. Derived label from applicant name
  if (m.applicant_name) {
    const compact = compactApplicantName(m.applicant_name);
    if (compact && compact.length >= 2) {
      return { text: compact, isPlaceholder: true, identifier: id };
    }
  }

  // 3. Fall back to identifier
  if (id) return { text: id, isPlaceholder: true, identifier: null };

  return { text: "—", isPlaceholder: true, identifier: null };
}
