"use client";

/** DomesticEnrichment — NOIP-authoritative detail card for domestic marks.
 * Rendered on the mark detail page when `detail.domestic` is non-null (i.e.
 * the domestic enrichment sweep has fetched NOIP data for this application).
 * Mirrors the structure of madrid-enrichment.tsx. */

import type { DomesticEnrichment as DomesticEnrichmentData } from "@/lib/api";
import { Card, CardHead, Pill } from "@/components/ui";
import { formatDate } from "@/lib/format";

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

// Render a label/value row that is always shown (shows "—" when missing).
function RowAlways({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <>
      <dt className="text-mute">{label}</dt>
      <dd className="font-medium text-ink">{value ?? "—"}</dd>
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
      <CardHead title="NOIP prosecution timeline" />
      <div className="flex flex-col gap-2 px-4 py-4">
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
          const status =
            typeof ev["status"] === "string" ? ev["status"] : null;

          return (
            <div key={i} className="border-l-2 border-ok pl-3">
              {date && (
                <div className="text-xs text-mute">{formatDate(date)}</div>
              )}
              {eventName && (
                <div className="text-sm text-ink-2">{eventName}</div>
              )}
              {status && !eventName && (
                <div className="text-sm text-ink-2">{status}</div>
              )}
              {!date && !eventName && !status && (
                <div className="text-sm text-mute">
                  {Object.values(ev)
                    .filter((v) => typeof v === "string")
                    .join(" · ") || "—"}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

/** DomesticEnrichment — NOIP record card. Renders only non-null fields. */
export function DomesticEnrichment({ e }: { e: DomesticEnrichmentData }) {
  return (
    <div className="space-y-5">
      {/* NOIP domestic record card */}
      <Card>
        <CardHead>
          <div className="flex items-center gap-2">
            <h2 className="head-serif m-0 text-sm font-semibold text-ink leading-tight tracking-tight">
              NOIP domestic record
            </h2>
            <Pill tone="stamp" size="sm">NOIP</Pill>
          </div>
        </CardHead>
        <dl className="grid grid-cols-[140px_1fr] gap-y-2 px-4 py-4 text-sm">
          <RowAlways label="Application №" value={e.application_number} />
          <Row label="Applicant" value={e.applicant_name} />
          <Row label="Address" value={e.applicant_address} />
          <Row label="Representative" value={e.representative} />
          <Row label="Mark type" value={e.mark_type} />
          <Row label="Color claim" value={e.colors} />
          <Row label="Status" value={e.status_code} />
          <Row label="Filed" value={e.filing_date ? formatDate(e.filing_date) : null} />
          <Row label="Publication №" value={e.publication_no} />
          <Row label="Published" value={e.publication_date ? formatDate(e.publication_date) : null} />
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
          {e.fetched_at && (
            <>
              <dt className="text-mute">Fetched</dt>
              <dd className="text-mute text-xs">{formatDate(e.fetched_at)}</dd>
            </>
          )}
        </dl>
      </Card>

      {e.source_url && (
        <a
          href={e.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-block text-xs font-medium text-stamp hover:text-stamp-deep underline"
        >
          View on NOIP trademark database ↗
        </a>
      )}
    </div>
  );
}
