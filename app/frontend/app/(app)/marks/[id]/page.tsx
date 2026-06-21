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
  MadridEnrichment,
  MadridJurisdictions,
  MadridTimeline,
  MadridVnBanner,
} from "@/components/detail/madrid-enrichment";
import { DomesticEnrichment, DomesticTimeline } from "@/components/detail/domestic-enrichment";
import { ClampedText } from "@/components/detail/clamped-text";
import { markCategoryMeta } from "@/components/badges";
import {
  api, countryDisplay, NICE_LABELS,
  type ApplicantStats, type CoMark, type InidMarker, type MarkDetail,
  type SimilarMark, type TimelineEvent, type Trademark,
} from "@/lib/api";
import type { PillTone } from "@/components/ui";
import { formatDate, formatNumber } from "@/lib/format";

/** Parse the (511) raw text into a per-class map. VN A-files and B-domestic
 * publish goods/services as "Nhóm 01: …. Nhóm 02: …." where each "Nhóm N:"
 * starts a new class block; the description runs until the next "Nhóm N:"
 * marker or end of text. Madrid B-files publish only a bare class list
 * ("05, 12.") with no per-class descriptions — we return an empty map and
 * the caller renders the whole block as a single paragraph. Keys are
 * zero-padded to match nice_classes ("01" not "1"). */
function parseGoodsServices(raw: string | null): Map<string, string> {
  const out = new Map<string, string>();
  if (!raw) return out;
  const re = /Nhóm\s+(\d+)\s*:\s*([\s\S]*?)(?=\s*Nhóm\s+\d+\s*:|$)/g;
  for (const m of raw.matchAll(re)) {
    const key = m[1].padStart(2, "0");
    const desc = m[2].trim();
    if (desc) out.set(key, desc);
  }
  return out;
}

/** Per-class goods & services. Marks can carry up to 45 Nice classes (Madrid
 * marks often do), so only the first 5 class blocks render by default with a
 * "Show all N classes" toggle — otherwise the panel becomes a wall. The per-
 * class text itself stays clamped to ~5 lines by <ClampedText>; this collapses
 * the NUMBER of classes shown, independently of that. */
function GoodsServices({
  classes,
  wipoGoods,
  raw511,
}: {
  classes: string[];
  wipoGoods: Record<string, string> | null;
  raw511: string | null;
}) {
  const [showAll, setShowAll] = React.useState(false);
  const perClass = parseGoodsServices(raw511);
  const goodsFor = (c: string) => wipoGoods?.[c.padStart(2, "0")] ?? perClass.get(c) ?? null;
  const hasPerClassText = !!wipoGoods || perClass.size > 0;

  // VN-domestic / no per-class text: a chip row + the raw (511) blob, no collapse.
  if (!hasPerClassText) {
    return (
      <div className="px-5 py-4 space-y-3">
        <div className="flex flex-wrap gap-2">
          {classes.map((c) => (
            <ClassChipFull key={c} n={c} />
          ))}
        </div>
        {raw511 && (
          <p className="text-[13px] text-ink-2 leading-relaxed whitespace-pre-wrap">{raw511}</p>
        )}
      </div>
    );
  }

  const PREVIEW = 5;
  const collapsible = classes.length > PREVIEW;
  const visible = showAll ? classes : classes.slice(0, PREVIEW);
  return (
    <div className="px-5 py-4 space-y-3">
      {visible.map((c) => (
        <div key={c} className="grid gap-3" style={{ gridTemplateColumns: "200px 1fr" }}>
          <div>
            <ClassChipFull n={c} />
          </div>
          {goodsFor(c) ? (
            <ClampedText text={goodsFor(c)!} />
          ) : (
            <p className="text-[13px] text-ink-2 leading-relaxed">
              {`Nice class ${parseInt(c, 10)} (${NICE_LABELS[c] || "—"}) — no per-class text in source.`}
            </p>
          )}
        </div>
      ))}
      {collapsible && (
        <button
          onClick={() => setShowAll((v) => !v)}
          className="text-[12.5px] font-medium text-stamp hover:text-stamp-deep"
        >
          {showAll ? "Show fewer" : `Show all ${classes.length} classes`}
        </button>
      )}
    </div>
  );
}

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
  const [isAdmin, setIsAdmin] = React.useState(false);

  React.useEffect(() => {
    api
      .adminCheck()
      .then((c) => setIsAdmin(c.isAdmin))
      .catch(() => setIsAdmin(false));
  }, []);

  React.useEffect(() => {
    if (!id) return;
    // Promise.allSettled, not Promise.all: one failed sidebar (e.g. similar
    // marks 500ing) must not block the whole page from rendering. Core mark
    // detail is the only required call — its failure is the actual page-level
    // error. Sidebar cards fall back to empty/null on individual failure.
    Promise.allSettled([
      api.getMark(id),
      api.markTimeline(id),
      api.markCoMarks(id, 5),
      api.markSimilar(id, 4),
      api.markApplicantStats(id),
      api.markInidFields(id),
    ]).then(([d, t, c, s, st, fi]) => {
      if (d.status === "rejected") {
        setError(d.reason?.message ?? String(d.reason));
        return;
      }
      setDetail(d.value);
      setTimeline(t.status === "fulfilled" ? t.value : []);
      setCoMarks(c.status === "fulfilled" ? c.value : []);
      setSimilar(s.status === "fulfilled" ? s.value : []);
      setStats(st.status === "fulfilled" ? st.value : null);
      setInid(fi.status === "fulfilled" ? fi.value : []);
    });
  }, [id]);

  if (error) return <Err error={error} />;
  if (!detail) return <SkeletonShell />;

  const m = detail.mark;
  // Prefer the WIPO-fetched mark name when the gazette had no 540 sample
  // (e.g. Madrid 3-D/figurative marks like "Hennessy PARADIS").
  const md = markDisplay(m, detail.enrichment?.mark_text ?? detail.domestic?.mark_text);
  const mc = markCategoryMeta(m.mark_category, m.record_type);
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
            <div
              className="grid gap-6 p-5"
              style={{ gridTemplateColumns: "minmax(0, 1.05fr) minmax(0, 1fr)" }}
            >
              <div>
                <div>
                  <MarkSpecimen
                    info={{ style: "wordmark-sans-bold", color: "ink", text: md.text, imageUrl: md.imageUrl }}
                    fallbackKey={m.id}
                    size="lg"
                    placeholder={md.isPlaceholder}
                  />
                  <div className="mt-2 label-meta">
                    {md.isPlaceholder
                      ? "Placeholder · WIPO field 540 not extracted"
                      : "WIPO INID code 540 · Reproduction of the mark"}
                  </div>
                </div>
                <Claims mark={m} />
              </div>

              <div className="min-w-0">
                <div className="flex items-start justify-between gap-3">
                  <h1 className="head-serif text-[26px] font-semibold tracking-tight leading-tight min-w-0 break-words">
                    {md.text}
                  </h1>
                </div>
                <div className="mt-2 flex items-center gap-2 flex-wrap">
                  <Pill tone={mc.tone}>{mc.label}</Pill>
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

          {/* Procedural timeline (gazette-derived). Madrid and domestic-enriched
              marks have their own NOIP/WIPO prosecution timeline below, so hide
              the gazette-derived one for them. */}
          {!detail.enrichment && !detail.domestic && (
            <Card>
              <CardHead
                title="Procedural timeline"
                sub="Reconstructed from gazette entries. Status flags surface deadlines automatically."
              />
              <Timeline events={timeline} />
            </Card>
          )}

          {/* VN protection banner leads the Madrid section, above the timeline. */}
          {detail.enrichment && <MadridVnBanner e={detail.enrichment} />}

          {/* WIPO Prosecution timeline — above Goods & services. */}
          {detail.enrichment && <MadridTimeline e={detail.enrichment} />}

          {/* NOIP domestic prosecution timeline — above Goods & services. */}
          {detail.domestic && <DomesticTimeline e={detail.domestic} />}

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
              <GoodsServices
                classes={m.nice_classes!}
                wipoGoods={detail.enrichment?.goods_services ?? detail.domestic?.goods_services ?? null}
                raw511={detail.raw_511_text ?? null}
              />
            </Card>
          )}

          {/* WIPO Madrid enrichment — only for enriched Madrid marks */}
          {detail.enrichment && <MadridEnrichment e={detail.enrichment} />}

          {/* NOIP domestic enrichment — only for enriched domestic marks */}
          {detail.domestic && <DomesticEnrichment e={detail.domestic} isAdmin={isAdmin} />}

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
                          info={{ style: "wordmark-sans-bold", color: "ink", text: smd.text, imageUrl: smd.imageUrl }}
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
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <SimilarityRing score={s.score} size={28} />
                        {s.visualConfidence === "typographic" && (
                          <span
                            className="text-[9px] font-mono font-semibold tracking-wider text-mute border border-line rounded px-1"
                            title="Visual signal is typographic fallback (no extracted logo PNG on one or both marks). Inspect specimens before relying on the score."
                          >
                            T
                          </span>
                        )}
                      </div>
                    </Link>
                  );
                })}
              </div>
            </Card>
          )}
        </div>

        {/* ===== SIDEBAR ===== */}
        <aside className="space-y-5 min-w-0">
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
                    {/* INID code (111/151/etc.) is kept as a hover-tooltip
                     * for power users cross-referencing the gazette PDF,
                     * but hidden from the visual layout — the label alone
                     * communicates what the field is. */}
                    <div
                      className="text-mute"
                      title={`WIPO INID code (${f.code})`}
                    >
                      {f.label}
                    </div>
                    <InidValue code={f.code} value={f.value} />
                  </li>
                ))}
              </ul>
            )}
          </Card>

          {/* Designated jurisdictions (Madrid marks) — sidebar, under Raw INID. */}
          {detail.enrichment && <MadridJurisdictions e={detail.enrichment} />}
        </aside>
      </div>
    </div>
  );
}

/* =========================================================================== */
/* Small subcomponents                                                          */
/* =========================================================================== */

/** Render a single INID-marker value. For most codes this is just the raw
 * string. For (511) Nice classification, only the class numbers are shown
 * here — the goods/services descriptions already render in the main
 * "Goods & services" panel above, and reproducing them in the sidebar
 * card was creating a visible duplicate. If the gazette only carried a
 * bare class list (no per-class descriptions — typical Madrid B-files),
 * the original value is rendered as-is. */
function InidValue({ code, value }: { code: string; value: string | null }) {
  if (!value) return null;
  if (code === "511") {
    const perClass = parseGoodsServices(value);
    if (perClass.size >= 1) {
      const classes = Array.from(perClass.keys()).map((k) => `Nhóm ${Number(k)}`).join(", ");
      return <div className="text-ink-2 break-words mt-0.5">{classes}</div>;
    }
  }
  return <div className="text-ink-2 break-words mt-0.5">{value}</div>;
}

function Breadcrumb({ mark, onBack }: { mark: Trademark; onBack: () => void }) {
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
  // Only render rows where the gazette explicitly carried the data — no demo
  // fillers. Field set is dataset-driven: 531 Vienna (~57% coverage) sits first
  // since it describes the figurative elements of the specimen shown above;
  // 551 Status was dropped (0% populated across the corpus); validity (171/176)
  // is registration-only so it's null on applications.
  const rows: { label: string; value: React.ReactNode }[] = [];
  if (m.vienna_codes && m.vienna_codes.length > 0) {
    rows.push({ label: "Vienna codes (531)", value: m.vienna_codes.join(" · ") });
  }
  if (m.protected_colors) rows.push({ label: "Color claim (591)", value: m.protected_colors });
  if (m.validity_171) rows.push({ label: "Validity (171)", value: m.validity_171 });
  else if (m.validity_176) rows.push({ label: "Validity (176)", value: m.validity_176 });
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
      <span className="label-meta">{label}</span>
      <span className="text-[13px] text-ink-2">{children}</span>
    </div>
  );
}

function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="label-meta">{label}</dt>
      <dd className="text-[13px] text-ink mt-0.5">{children}</dd>
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
