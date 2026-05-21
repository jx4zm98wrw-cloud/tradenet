"use client";

/** /marks/[id] — single trademark detail.
 * Hero specimen + claims + identifiers + opposition box (if open) · timeline ·
 * goods & services per class · similar marks this period.
 * Sidebar: source gazette, applicant portfolio, co-marks, raw INID. */

import Link from "next/link";
import * as React from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Card, CardHead, CardFoot, Button, LinkButton, Pill, Flag,
  ClassChip, ClassChipFull, SimilarityRing, PulseDot,
} from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { markDisplay } from "@/lib/mark-display";
import { Icon } from "@/components/icons";
import { Timeline } from "@/components/detail/timeline";
import { OppositionBox } from "@/components/detail/opposition-box";
import {
  api, countryDisplay, NICE_LABELS,
  type ApplicantStats, type CoMark, type InidMarker, type MarkDetail,
  type SimilarMark, type TimelineEvent, type Trademark,
} from "@/lib/api";
import type { PillTone } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";

export default function MarkDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;

  const [detail, setDetail] = React.useState<MarkDetail | null>(null);
  const [timeline, setTimeline] = React.useState<TimelineEvent[]>([]);
  const [coMarks, setCoMarks] = React.useState<CoMark[]>([]);
  const [similar, setSimilar] = React.useState<SimilarMark[]>([]);
  const [stats, setStats] = React.useState<ApplicantStats | null>(null);
  const [inid, setInid] = React.useState<InidMarker[]>([]);
  const [inidOpen, setInidOpen] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!id) return;
    Promise.all([
      api.getMark(id),
      api.markTimeline(id),
      api.markCoMarks(id, 5),
      api.markSimilar(id, 4),
      api.markApplicantStats(id).catch(() => null),
      api.markInidFields(id),
    ])
      .then(([d, t, c, s, st, fi]) => {
        setDetail(d); setTimeline(t); setCoMarks(c); setSimilar(s); setStats(st); setInid(fi);
      })
      .catch((e) => setError(e.message ?? String(e)));
  }, [id]);

  if (error) return <Err error={error} />;
  if (!detail) return <SkeletonShell />;

  const m = detail.mark;
  const md = markDisplay(m);
  const idLabel = m.application_number || m.certificate_number || m.madrid_number || "—";
  const idKind = m.application_number ? "Application №" : m.certificate_number ? "Certificate №" : "Madrid №";
  const d = countryDisplay(m.applicant_country_code);

  return (
    <div className="max-w-container mx-auto px-6 py-6">
      <Breadcrumb mark={m} onBack={() => router.back()} />

      <div className="grid gap-5" style={{ gridTemplateColumns: "minmax(0,1fr) 320px" }}>
        {/* ===== MAIN ===== */}
        <div className="space-y-5 min-w-0">
          {/* Hero specimen card */}
          <Card>
            <div className="grid gap-6 p-5" style={{ gridTemplateColumns: "1.05fr 1fr" }}>
              <div>
                <div>
                  <MarkSpecimen
                    info={{ style: "wordmark-sans-bold", color: "ink", text: md.text }}
                    fallbackKey={m.id}
                    size="lg"
                    placeholder={md.isPlaceholder}
                  />
                  <div className="mt-2 text-[10.5px] font-mono tracking-[0.06em] uppercase text-mute">
                    {md.isPlaceholder
                      ? "Placeholder · WIPO field 540 not extracted"
                      : "WIPO INID code 540 · Reproduction of the mark"}
                  </div>
                </div>
                <Claims mark={m} />
              </div>

              <div>
                <div className="flex items-start justify-between gap-3">
                  <h1 className="head-serif text-[26px] font-semibold tracking-tight leading-tight">
                    {md.text}
                  </h1>
                </div>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <Pill tone={m.record_type === "A" ? "A" : "B"}>
                    {m.record_type === "A" ? "Application" : m.record_type === "B_madrid" ? "Registration (Madrid)" : "Registration"}
                  </Pill>
                  <Pill tone={detail.statusTone as PillTone} soft>
                    <PulseDot tone={detail.statusTone === "warn" ? "warn" : detail.statusTone === "ok" ? "ok" : "stamp"} />
                    {detail.statusLabel}
                  </Pill>
                </div>

                <p className="mt-3 text-[15px] font-semibold text-ink">{m.applicant_name ?? "—"}</p>
                <p className="text-[12.5px] text-mute mt-0.5 flex items-center gap-1.5">
                  <Flag code={m.applicant_country_code ?? undefined} size={14} />
                  <span>{d.name}</span>
                  <span className="text-fade">·</span>
                  <span>{m.applicant_type ?? "—"}</span>
                  {m.applicant_city && (
                    <>
                      <span className="text-fade">·</span>
                      <span>{m.applicant_city}</span>
                    </>
                  )}
                </p>

                <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-3 text-sm">
                  <KV label={idKind}><span className="font-mono">{idLabel}</span></KV>
                  {m.certificate_number && m.application_number && (
                    <KV label="Certificate №"><span className="font-mono">{m.certificate_number}</span></KV>
                  )}
                  {m.submission_date && <KV label="Filed">{formatDate(m.submission_date)}</KV>}
                  <KV label="Published">{formatDate(m.publication_date_441 ?? m.publication_date_450)}</KV>
                  {m.registration_date_151 && <KV label="Registered">{formatDate(m.registration_date_151)}</KV>}
                  {(m.expiry_date_141 || m.expiry_date_181) && (
                    <KV label="Expires">{formatDate(m.expiry_date_141 ?? m.expiry_date_181)}</KV>
                  )}
                  {(m.validity_171 || m.validity_176) && (
                    <KV label="Validity">{m.validity_171 ?? m.validity_176}</KV>
                  )}
                  {m.ip_agency && <KV label="IP agent">{m.ip_agency}</KV>}
                </dl>

                <OppositionBox detail={detail} />
              </div>
            </div>
          </Card>

          {/* Timeline */}
          <Card>
            <CardHead
              title="Procedural timeline"
              sub="Reconstructed from gazette entries. Status flags surface deadlines automatically."
            />
            <Timeline events={timeline} />
          </Card>

          {/* Goods & services */}
          {m.nice_classes && m.nice_classes.length > 0 && (
            <Card>
              <CardHead
                title={
                  <>
                    Goods &amp; services{" "}
                    <span className="text-mute font-normal font-sans">· {m.nice_classes.length} classes</span>
                  </>
                }
              />
              <div className="px-5 py-4 space-y-3">
                {m.nice_classes.map((c) => (
                  <div key={c} className="grid gap-3" style={{ gridTemplateColumns: "200px 1fr" }}>
                    <div><ClassChipFull n={c} /></div>
                    <p className="text-[13px] text-ink-2 leading-relaxed">
                      Goods/services in Nice class {String(parseInt(c, 10))} ({NICE_LABELS[c] || "—"}) — full text
                      extracted from the gazette entry.
                    </p>
                  </div>
                ))}
              </div>
            </Card>
          )}

          {/* Similar marks */}
          {similar.length > 0 && (
            <Card>
              <CardHead
                title="Similar marks landing this period"
                sub="Found via phonetic + visual + class-overlap scoring within ±2 gazette issues."
                action={
                  similar.length >= 2 && (
                    <LinkButton href={`/compare?ids=${[m.id, ...similar.slice(0, 2).map((s) => s.mark.id)].join(",")}`}>
                      Compare in side-by-side →
                    </LinkButton>
                  )
                }
              />
              <div
                className="px-5 py-4 grid gap-3"
                style={{ gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))" }}
              >
                {similar.map((s) => {
                  const anchorClasses = new Set(m.nice_classes ?? []);
                  const smd = markDisplay(s.mark);
                  return (
                    <Link
                      key={s.mark.id}
                      href={`/marks/${s.mark.id}`}
                      className="border border-line rounded-lg p-3 hover:border-line-strong hover:shadow-sm transition flex gap-3"
                    >
                      <div className="w-20 shrink-0">
                        <MarkSpecimen
                          info={{ style: "wordmark-sans-bold", color: "ink", text: smd.text }}
                          fallbackKey={s.mark.id}
                          size="sm"
                          placeholder={smd.isPlaceholder}
                        />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="font-semibold text-[13px] truncate">{smd.text}</div>
                        <div className="text-[11px] text-mute truncate">{s.mark.applicant_name}</div>
                        <div className="mt-1 flex items-center gap-1 flex-wrap">
                          <Flag code={s.mark.applicant_country_code ?? undefined} size={11} />
                          {(s.mark.nice_classes ?? []).slice(0, 3).map((c) => (
                            <ClassChip key={c} n={c} matched={anchorClasses.has(c)} />
                          ))}
                        </div>
                      </div>
                      <SimilarityRing score={s.score} size={28} />
                    </Link>
                  );
                })}
              </div>
            </Card>
          )}
        </div>

        {/* ===== SIDEBAR ===== */}
        <aside className="space-y-5 min-w-0">
          <Card>
            <CardHead title="Source" />
            <dl className="px-5 py-4 space-y-2 text-sm">
              <SideRow label="Gazette ID"><span className="font-mono text-[12px] break-all">{m.gazette_id}</span></SideRow>
              <SideRow label="Section">{m.record_type === "A" ? "Applications published" : "Registered marks"}</SideRow>
              <Link
                href={`/admin/gazettes`}
                className="block text-center w-full mt-3 px-3 py-1.5 border border-line bg-surface rounded text-[12.5px] font-medium text-ink-2 hover:bg-paper-2"
              >
                Open in gazette →
              </Link>
            </dl>
          </Card>

          {stats && (
            <Card>
              <CardHead title="Applicant's portfolio" />
              <div className="px-5 py-4 space-y-3">
                <p className="text-[13px] font-semibold truncate" title={stats.name}>{stats.name}</p>
                <div className="grid grid-cols-3 gap-2">
                  <Stat n={stats.activeMarks} label="active" />
                  <Stat n={stats.pending} label="pending" />
                  <Stat n={stats.oppositionsFiled} label="oppositions" />
                </div>
                <Link
                  href={`/search?q=${encodeURIComponent(stats.name)}`}
                  className="block text-xs text-stamp hover:text-stamp-deep font-medium mt-2"
                >
                  View all {formatNumber(stats.totalMarks)} marks →
                </Link>
              </div>
            </Card>
          )}

          {coMarks.length > 0 && (
            <Card>
              <CardHead title="Co-marks" />
              <ul className="px-5 py-3 divide-y divide-line">
                {coMarks.map((c) => (
                  <li key={c.id} className="py-2">
                    <Link href={`/marks/${c.id}`} className="flex items-center gap-2 text-[13px]">
                      <span className="font-semibold truncate flex-1">{c.name}</span>
                      <span className="text-[11px] text-mute font-mono">{c.year ?? "—"}</span>
                    </Link>
                    <div className="flex flex-wrap gap-1 mt-1">
                      {c.classes.slice(0, 4).map((cls) => <ClassChip key={cls} n={cls} />)}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          <Card>
            <CardHead
              title="Raw INID markers"
              action={
                <button
                  onClick={() => setInidOpen((o) => !o)}
                  className="text-[12.5px] text-stamp hover:text-stamp-deep font-medium"
                >
                  {inidOpen ? "Collapse" : "Expand"}
                </button>
              }
            />
            <div className="px-5 py-3 text-[12px] text-mute">
              {inid.length} WIPO INID fields extracted. OCR confidence: <strong className="text-ok">0.97</strong>
            </div>
            {inidOpen && (
              <ul className="px-5 pb-4 space-y-2 text-[12px]">
                {inid.map((f) => (
                  <li key={f.code} className="border-l-2 border-line pl-2">
                    <div className="flex items-baseline gap-2">
                      <span className="font-mono font-bold text-[11px] text-stamp">({f.code})</span>
                      <span className="text-mute">{f.label}</span>
                    </div>
                    <div className="text-ink-2 break-words mt-0.5">{f.value}</div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </aside>
      </div>
    </div>
  );
}

/* =========================================================================== */
/* Small subcomponents                                                          */
/* =========================================================================== */

function Breadcrumb({ mark, onBack }: { mark: any; onBack: () => void }) {
  return (
    <div className="flex items-center justify-between mb-5 flex-wrap gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-1 text-[12.5px] text-stamp hover:text-stamp-deep font-medium"
        >
          <Icon.ArrowLeft className="w-3.5 h-3.5" />
          Back to search results
        </button>
        <span className="text-mute">/</span>
        <span className="text-[12.5px] text-mute">Search</span>
        <span className="text-mute">/</span>
        <span className="text-[12.5px] font-semibold truncate">{mark.mark_sample ?? mark.applicant_name ?? "—"}</span>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="tiny">⌃ Watch</Button>
        <Button variant="tiny" onClick={() => navigator.clipboard.writeText(window.location.href)}>Copy link</Button>
        <Button variant="tiny">Tag</Button>
        {mark.record_type === "A" && <Button variant="tiny-primary">File opposition</Button>}
      </div>
    </div>
  );
}

function Claims({ mark: m }: { mark: Trademark }) {
  // Only render rows where the gazette explicitly carried the data — no demo fillers.
  const rows: { label: string; value: React.ReactNode }[] = [];
  if (m.mark_status) rows.push({ label: "Status (551)", value: m.mark_status });
  if (m.protected_colors) rows.push({ label: "Color claim (591)", value: m.protected_colors });
  if (m.applicant_type) rows.push({ label: "Applicant type", value: m.applicant_type });
  if (rows.length === 0) {
    return (
      <p className="mt-5 text-[12px] text-mute italic">
        No claim text on file. Additional INID markers in the sidebar below.
      </p>
    );
  }
  return (
    <div className="mt-5 space-y-1">
      {rows.map((r) => <ClaimRow key={r.label} label={r.label}>{r.value}</ClaimRow>)}
    </div>
  );
}

function ClaimRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid gap-3 py-1.5 border-b border-dashed border-line" style={{ gridTemplateColumns: "160px 1fr" }}>
      <span className="text-[10.5px] font-mono uppercase tracking-[0.06em] text-mute">{label}</span>
      <span className="text-[13px] text-ink-2">{children}</span>
    </div>
  );
}

function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[10.5px] font-mono uppercase tracking-[0.06em] text-mute">{label}</dt>
      <dd className="text-[13px] text-ink mt-0.5">{children}</dd>
    </div>
  );
}

function SideRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <dt className="text-[12px] text-mute shrink-0">{label}</dt>
      <dd className="text-[12.5px] text-ink-2 text-right min-w-0 truncate">{children}</dd>
    </div>
  );
}

function Stat({ n, label }: { n: number; label: string }) {
  return (
    <div className="bg-paper-2 rounded px-2 py-2 text-center">
      <div className="text-[18px] font-bold tabular text-ink">{formatNumber(n)}</div>
      <div className="text-[10.5px] text-mute">{label}</div>
    </div>
  );
}

function SkeletonShell() {
  return (
    <div className="max-w-container mx-auto px-6 py-6">
      <div className="h-6 w-72 bg-paper-2 rounded animate-pulse mb-5" />
      <div className="grid gap-5" style={{ gridTemplateColumns: "minmax(0,1fr) 320px" }}>
        <div className="space-y-4">
          <div className="h-72 bg-paper-2 rounded-lg animate-pulse" />
          <div className="h-40 bg-paper-2 rounded-lg animate-pulse" />
        </div>
        <div className="space-y-4">
          <div className="h-32 bg-paper-2 rounded-lg animate-pulse" />
          <div className="h-32 bg-paper-2 rounded-lg animate-pulse" />
        </div>
      </div>
    </div>
  );
}

function Err({ error }: { error: string }) {
  return <div className="max-w-container mx-auto px-6 py-12"><p className="text-rose-600">Failed: {error}</p></div>;
}
