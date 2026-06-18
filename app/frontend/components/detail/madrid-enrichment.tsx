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

export function MadridEnrichment({ e }: { e: MadridEnrichmentData }) {
  const granted = e.vn_status === "granted";

  const countries = [...(e.designated_countries ?? [])].sort((a, b) =>
    a === "VN" ? -1 : b === "VN" ? 1 : 0,
  );

  // VN-focused product: the prosecution timeline shows only events where
  // Vietnam is a party (IR designation, VN provisional refusal, grant,
  // renewals). Other jurisdictions' prosecution is noise here.
  const timeline = [...(e.transaction_history ?? [])]
    .filter((t) => t.date && (t.parties ?? []).includes("VN"))
    .sort((a, b) => ((a.date ?? "") < (b.date ?? "") ? -1 : 1));

  return (
    <div className="space-y-5">
      {/* VN banner */}
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
          <dd>{e.representative ?? "—"}</dd>
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

      {/* Designated jurisdictions */}
      <Card>
        <CardHead title={`Designated jurisdictions (${countries.length})`} />
        <div className="flex flex-wrap gap-1.5 px-4 py-4">
          {countries.length === 0 ? (
            <span className="text-sm text-mute">No designated jurisdictions parsed.</span>
          ) : (
            countries.map((cc) => (
              <span
                key={cc}
                className={`inline-flex items-center gap-1.5 rounded px-2 py-1 text-xs ${
                  cc === "VN" ? "bg-ok-2 font-semibold text-ok" : "bg-paper-2 text-ink-2"
                }`}
                title={cname(cc)}
              >
                <Flag code={cc} size={12} />
                {cc}
              </span>
            ))
          )}
        </div>
      </Card>

      {/* Two-pane: status by jurisdiction + prosecution timeline */}
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
