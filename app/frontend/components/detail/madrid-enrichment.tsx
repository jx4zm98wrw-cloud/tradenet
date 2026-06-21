"use client";

import * as React from "react";
import type { MadridEnrichment as MadridEnrichmentData } from "@/lib/api";
import { countryDisplay } from "@/lib/api";
import { Card, CardHead, Pill, Flag } from "@/components/ui";
import { formatDate } from "@/lib/format";

const cname = (cc: string) => countryDisplay(cc).name;

// In the VN-only timeline, a WIPO event type ends with the full member-country
// list (e.g. "Renewal, AG, AL, …, VN, ZM"). Strip that trailing list so each
// event reads as a clean VN-scoped action ("Renewal", "International
// Registration", "Statement of grant of protection made under Rule 18ter(1)").
const cleanEventType = (t: string | undefined) =>
  (t ?? "").replace(/,\s*[A-Z]{2}(?:\s*,\s*[A-Z]{2})*\s*$/, "").trim();

// VN-focused prosecution timeline. Rendered as its own card (positioned above
// Goods & services on the detail page) so it leads the Madrid section.
export function MadridTimeline({ e }: { e: MadridEnrichmentData }) {
  // Only events where Vietnam is a party (IR designation, VN provisional
  // refusal, grant, renewals). Other jurisdictions' prosecution is noise here.
  const timeline = [...(e.transaction_history ?? [])]
    .filter((t) => t.date && (t.parties ?? []).includes("VN"))
    .sort((a, b) => ((a.date ?? "") < (b.date ?? "") ? -1 : 1));
  return (
    <Card>
      <CardHead title="Prosecution timeline" />
      <div className="flex flex-col gap-2 px-4 py-4">
        {timeline.length === 0 ? (
          <div className="text-sm text-mute">No transaction history parsed.</div>
        ) : (
          timeline.map((ev, i) => {
            const isVN = (ev.parties ?? []).includes("VN");
            return (
              <div key={i} className={`border-l-2 pl-3 ${isVN ? "border-ok" : "border-line"}`}>
                <div className="text-xs text-mute">
                  {ev.date ? formatDate(ev.date) : ""}
                  {ev.gazette ? ` · Gaz ${ev.gazette}` : ""}
                </div>
                <div className="text-sm text-ink-2">{cleanEventType(ev.type)}</div>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}

// An event counts as VN-related if Vietnam is an explicit party OR the WIPO
// event type names VN OR it is a global IR-wide event with no country
// attribution. The `parties` check alone misses Renewal events — WIPO
// mis-attributes their `parties` to the holder's country — so the `\bVN\b` type
// check is required to catch VN renewals. Global events (representative/holder
// changes, etc.) carry empty `parties` and don't name VN, yet they affect the
// VN designation too — include them. Country-specific non-VN events keep a
// non-empty `parties` (e.g. ["RU"]) and stay excluded. Use all three conditions
// (OR), do not drop any.
const isVnEvent = (e: { type?: string; parties?: string[] }) =>
  (e.parties?.includes("VN") ?? false) ||
  /\bVN\b/.test(e.type ?? "") ||
  (e.parties?.length ?? 0) === 0; // global IR-wide event (no country tag) — affects VN too

// MadridVnTimeline — VN-scoped prosecution events as a 2-column (Event | Date)
// table, mirroring DomesticTimeline so Madrid and domestic marks present an
// identical "Vietnam IP prosecution timeline" card. Rendered only when there is
// at least one VN-related event. Event types render verbatim (they can be long
// and are allowed to wrap); ISO dates are formatted with the shared formatDate.
export function MadridVnTimeline({ e }: { e: MadridEnrichmentData }) {
  const vnEvents = (e.transaction_history ?? [])
    .filter(isVnEvent)
    .slice()
    .sort((a, b) => (a.date ?? "").localeCompare(b.date ?? "")); // ISO dates sort lexically
  if (vnEvents.length === 0) return null;

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
          {vnEvents.map((ev, i) => (
            <tr key={i} className="border-b border-line/60 last:border-b-0">
              <td className="px-4 py-2 text-ink-2">{ev.type ?? "—"}</td>
              <td className="px-4 py-2 text-mute whitespace-nowrap">
                {ev.date ? formatDate(ev.date) : "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

// Designated-jurisdiction chips (~80). Rendered in the right sidebar (under Raw
// INID markers) on the detail page. Shows the first 5 grid rows by default.
export function MadridJurisdictions({ e }: { e: MadridEnrichmentData }) {
  const [show, setShow] = React.useState(false);
  const countries = [...(e.designated_countries ?? [])].sort((a, b) =>
    a === "VN" ? -1 : b === "VN" ? 1 : 0,
  );
  const PREVIEW = 20; // 5 rows × 4 columns
  const collapsible = countries.length > PREVIEW;
  const visible = show ? countries : countries.slice(0, PREVIEW);
  return (
    <Card>
      <CardHead
        title={`Designated jurisdictions (${countries.length})`}
        action={
          collapsible ? (
            <button
              onClick={() => setShow((o) => !o)}
              className="text-[12.5px] font-medium text-stamp hover:text-stamp-deep"
            >
              {show ? "Show less" : `Show all ${countries.length}`}
            </button>
          ) : undefined
        }
      />
      {countries.length === 0 ? (
        <div className="px-4 py-4 text-sm text-mute">No designated jurisdictions parsed.</div>
      ) : (
        <div className="grid grid-cols-4 gap-1.5 px-4 py-4">
          {visible.map((cc) => (
            <span
              key={cc}
              className={`flex items-center justify-center gap-1 rounded px-1.5 py-1 text-xs ${
                cc === "VN" ? "bg-ok-2 font-semibold text-ok" : "bg-paper-2 text-ink-2"
              }`}
              title={cname(cc)}
            >
              <Flag code={cc} size={12} />
              {cc}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

// The 🇻🇳 "Protected in Vietnam" banner. Rendered as its own card so the detail
// page can lead the Madrid section with it (above the Prosecution timeline).
export function MadridVnBanner({ e }: { e: MadridEnrichmentData }) {
  const granted = e.vn_status === "granted";
  return (
    <div
      className={`flex items-center gap-3 rounded-lg border p-4 ${
        granted ? "border-[oklch(0.85_0.05_165)] bg-ok-2" : "border-line bg-paper-2"
      }`}
    >
      <span className="text-2xl leading-none" aria-hidden="true">
        {granted ? "🇻🇳" : "🏳️"}
      </span>
      <div className="min-w-0">
        <div className={`font-semibold ${granted ? "text-ok" : "text-ink"}`}>
          {granted
            ? `Protected in Vietnam — granted${e.vn_grant_date ? ` ${formatDate(e.vn_grant_date)}` : ""}`
            : `VN status: ${e.vn_status ?? "—"}`}
        </div>
        <div className="mt-0.5 text-sm text-mute">
          {e.vn_refusal_date ? `refused ${formatDate(e.vn_refusal_date)} · ` : ""}
          expires {e.expiration_date ? formatDate(e.expiration_date) : "—"}
        </div>
      </div>
    </div>
  );
}

export function MadridEnrichment({ e }: { e: MadridEnrichmentData }) {
  // WIPO label: "Appointment or renunciation of the representative". When the
  // record has no current representative but such an event exists, surface the
  // latest renunciation date instead of a bare em-dash.
  const renounced = (e.transaction_history ?? [])
    .filter((ev) => /renunciation of the representative/i.test(ev.type ?? ""))
    .map((ev) => ev.date)
    .filter(Boolean)
    .sort()
    .at(-1); // latest ISO date

  return (
    <div className="space-y-5">
      {/* WIPO Madrid record card */}
      <Card>
        <CardHead>
          <div className="flex items-center gap-2">
            <h2 className="head-serif m-0 text-sm font-semibold text-ink leading-tight tracking-tight">
              WIPO Madrid record
            </h2>
            <Pill tone="stamp" size="sm">WIPO</Pill>
          </div>
        </CardHead>
        <dl className="grid grid-cols-[120px_1fr] gap-y-2 px-4 py-4 text-sm">
          <dt className="text-mute">IRN</dt>
          <dd className="font-mono">{e.irn}</dd>
          <dt className="text-mute">Holder</dt>
          <dd className="font-medium text-ink">{e.holder_name ?? "—"}</dd>
          <dt className="text-mute">Address</dt>
          <dd>{e.holder_address ?? "—"}</dd>
          <dt className="text-mute">Country</dt>
          <dd className="flex items-center gap-1.5">
            {e.holder_country ? (
              <>
                <Flag code={e.holder_country} size={13} />
                <span>{cname(e.holder_country)}</span>
              </>
            ) : (
              "—"
            )}
          </dd>
          <dt className="text-mute">Legal nature</dt>
          <dd>{e.holder_legal_status ?? "—"}</dd>
          <dt className="text-mute">Representative</dt>
          <dd>
            {e.representative
              ? e.representative
              : renounced
                ? `— (representative renounced, ${formatDate(renounced)})`
                : "—"}
          </dd>
          <dt className="text-mute">Registered</dt>
          <dd>{e.registration_date ? formatDate(e.registration_date) : "—"}</dd>
          <dt className="text-mute">Expiration</dt>
          <dd className="font-medium text-ink">{e.expiration_date ? formatDate(e.expiration_date) : "—"}</dd>
          <dt className="text-mute">Nice</dt>
          <dd>{(e.nice_classes ?? []).join(", ") || "—"}</dd>
          <dt className="text-mute">Basic reg.</dt>
          <dd>{e.basic_registration ?? "—"}</dd>
        </dl>
      </Card>

      {e.source_url && (
        <a
          href={e.source_url}
          target="_blank"
          rel="noreferrer"
          className="inline-block text-xs font-medium text-stamp hover:text-stamp-deep underline"
        >
          View on WIPO Madrid Monitor ↗
        </a>
      )}
    </div>
  );
}
