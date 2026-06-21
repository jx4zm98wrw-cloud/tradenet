"use client";

/** DomesticEnrichment — NOIP-authoritative detail card for domestic marks.
 * Rendered on the mark detail page when `detail.domestic` is non-null (i.e.
 * the domestic enrichment sweep has fetched NOIP data for this application).
 * Mirrors the structure of madrid-enrichment.tsx. */

import type { DomesticEnrichment as DomesticEnrichmentData } from "@/lib/api";
import { Card, CardHead, Pill } from "@/components/ui";
import { formatDate } from "@/lib/format";

// NOIP timeline dates are `dd.mm.yyyy` strings (not ISO like the structured
// biblio dates), so `new Date("08.01.2026")` misreads them (→ "Aug 1" or
// "Invalid Date"). Convert to ISO before formatting; pass through anything that
// isn't dd.mm.yyyy rather than rendering "Invalid Date".
function formatNoipDate(raw: string): string {
  const m = raw.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  return m ? formatDate(`${m[3]}-${m[2]}-${m[1]}`) : raw;
}

// Render a label/value row in the <dl> grid, skipping null/empty values.
function Row({ label, value }: { label: string; value: string | null | undefined }) {
  if (!value) return null;
  return (
    <>
      <dt className="text-mute">{label}</dt>
      <dd>{value}</dd>
    </>
  );
}

/** DomesticTimeline — NOIP prosecution events. Rendered as its own card above
 * Goods & services, only when `e.timeline` is non-empty. Each row is a
 * `Record<string, unknown>` from the NOIP API; we render it defensively. */
export function DomesticTimeline({ e }: { e: DomesticEnrichmentData }) {
  const timeline = e.timeline ?? [];
  if (timeline.length === 0) return null;

  // NOIP timeline rows use snake_case keys; common observed shapes:
  // { event: "…", date: "YYYY-MM-DD", status: "…" }
  // We render all string values present, falling back gracefully.
  return (
    <Card>
      <CardHead title="Vietnam IP prosecution timeline" />
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line text-left">
            <th className="px-4 py-2 font-semibold text-mute">Event</th>
            <th className="px-4 py-2 font-semibold text-mute">Date</th>
          </tr>
        </thead>
        <tbody>
          {timeline.map((ev, i) => {
            const date =
              typeof ev["date"] === "string"
                ? ev["date"]
                : typeof ev["event_date"] === "string"
                  ? ev["event_date"]
                  : null;
            const eventName =
              typeof ev["event"] === "string"
                ? ev["event"]
                : typeof ev["event_name"] === "string"
                  ? ev["event_name"]
                  : typeof ev["type"] === "string"
                    ? ev["type"]
                    : null;
            const fallback =
              !eventName && !date
                ? Object.values(ev)
                    .filter((v) => typeof v === "string")
                    .join(" · ") || "—"
                : null;

            return (
              <tr key={i} className="border-b border-line/60 last:border-b-0">
                <td className="px-4 py-2 text-ink-2">{eventName ?? fallback ?? "—"}</td>
                <td className="px-4 py-2 text-mute whitespace-nowrap">
                  {date ? formatNoipDate(date) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}

/** DomesticEnrichment — NOIP record card. Renders only non-null fields.
 * `isAdmin` gates the Fetched row and the source-database link (admin-only). */
export function DomesticEnrichment({ e, isAdmin = false }: { e: DomesticEnrichmentData; isAdmin?: boolean }) {
  return (
    <div className="space-y-5">
      {/* NOIP domestic record card */}
      <Card>
        <CardHead>
          <div className="flex items-center gap-2">
            <h2 className="head-serif m-0 text-sm font-semibold text-ink leading-tight tracking-tight">
              Vietnam IP domestic record
            </h2>
            <Pill tone="stamp" size="sm">VIETNAM IP</Pill>
          </div>
        </CardHead>
        <dl className="grid grid-cols-[140px_1fr] gap-y-2 px-4 py-4 text-sm">
          <Row label="Applicant" value={e.applicant_name} />
          <Row label="Address" value={e.applicant_address} />
          <Row label="Mark type" value={e.mark_type} />
          <Row label="Color claim" value={e.colors} />
          <Row label="Status" value={e.status_code} />
          <Row label="Publication №" value={e.publication_no} />
          <Row label="Granted" value={e.grant_date ? formatDate(e.grant_date) : null} />
          <Row label="Expiry" value={e.expiry_date ? formatDate(e.expiry_date) : null} />
          {e.nice_classes && e.nice_classes.length > 0 && (
            <>
              <dt className="text-mute">Nice classes</dt>
              <dd>{e.nice_classes.join(", ")}</dd>
            </>
          )}
          {e.vienna_codes && e.vienna_codes.length > 0 && (
            <>
              <dt className="text-mute">Vienna codes</dt>
              <dd className="break-words">{e.vienna_codes.join(" · ")}</dd>
            </>
          )}
          {isAdmin && e.fetched_at && (
            <>
              <dt className="text-mute">Fetched</dt>
              <dd className="text-mute text-xs">{formatDate(e.fetched_at)}</dd>
            </>
          )}
        </dl>
      </Card>

      {isAdmin && e.source_url && (
        <a
          href={e.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-block text-xs font-medium text-stamp hover:text-stamp-deep underline"
        >
          View on Vietnam IP trademark database ↗
        </a>
      )}
    </div>
  );
}
