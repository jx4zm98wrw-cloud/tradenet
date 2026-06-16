"use client";

/** /compare?ids=… — side-by-side conflict review of 2–3 marks.
 * First id is the anchor ("YOUR MARK"). Scorecard + plates row + comparative rows. */

import Link from "next/link";
import * as React from "react";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Card, Button, Pill, Flag, ClassChip, SimilarityRing, PulseDot, LinkButton,
} from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { formatDateShort } from "@/lib/format";
import { markDisplay } from "@/lib/mark-display";
import { Icon } from "@/components/icons";
import {
  api, countryDisplay, NICE_LABELS,
  type CompareResponse, type PairScore, type Trademark,
} from "@/lib/api";
import type { PillTone } from "@/components/ui";

// Compact date for the compare grid (no year — implied by surrounding context).
// Imported from lib/format to keep a single source of truth across the app.

export default function ComparePageShell() {
  return (
    <Suspense fallback={null}>
      <ComparePage />
    </Suspense>
  );
}

function ComparePage() {
  const router = useRouter();
  const sp = useSearchParams();
  const ids = React.useMemo(() => (sp.get("ids") ?? "").split(",").filter(Boolean).slice(0, 3), [sp]);
  const [data, setData] = React.useState<CompareResponse | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (ids.length < 2) {
      setError("Need at least 2 marks to compare. Add them from Search.");
      return;
    }
    api.compare(ids)
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e.message ?? String(e)));
  }, [ids.join(",")]); // eslint-disable-line

  if (error) {
    return (
      <div className="max-w-container mx-auto px-6 py-12">
        <p className="text-rose-600 mb-3">{error}</p>
        <Link href="/search" className="text-stamp hover:underline">← Back to search</Link>
      </div>
    );
  }
  if (!data) return <SkeletonShell />;

  const anchor = data.marks.find((m) => m.id === data.anchorId)!;
  const others = data.marks.filter((m) => m.id !== data.anchorId);
  const N = data.marks.length;
  const gridCols = `1.2fr repeat(${N}, minmax(0, 1fr))`;

  return (
    <div className="max-w-container mx-auto px-6 py-6 space-y-5">
      {/* Breadcrumb */}
      <div className="flex items-center justify-between mb-1 flex-wrap gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => router.back()} className="inline-flex items-center gap-1 text-[12.5px] text-stamp hover:text-stamp-deep font-medium">
            <Icon.ArrowLeft className="w-3.5 h-3.5" />
            Back to search
          </button>
          <span className="text-mute">/</span>
          <span className="text-[12.5px] text-mute">Compare</span>
          <span className="text-mute">/</span>
          <span className="text-[12.5px] font-semibold truncate">
            {data.marks.map((m) => m.mark_sample ?? m.applicant_name ?? "—").join(" vs. ")}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="tiny">Add mark to compare</Button>
          <Button variant="tiny">Save comparison</Button>
          <Button variant="tiny-primary">Export PDF report</Button>
        </div>
      </div>

      {/* Scorecard band */}
      <ScorecardBand anchor={anchor} scores={data.scores} marks={data.marks} weights={data.weights} />

      {/* Mark plates row */}
      <div className="grid gap-4" style={{ gridTemplateColumns: gridCols }}>
        <CmpLabelHeader>Mark specimen</CmpLabelHeader>
        {data.marks.map((m, i) => (
          <PlateCell key={m.id} mark={m} anchor={i === 0} />
        ))}
      </div>

      {/* Comparative rows */}
      <Card className="overflow-visible">
        <div className="grid gap-x-4" style={{ gridTemplateColumns: gridCols }}>
          <CmpHeader>Identity &amp; status</CmpHeader>
          <CmpRow label="Type" n={N}>
            {data.marks.map((m) => (
              <span key={m.id}>
                {m.record_type === "A" ? "Application" : m.record_type === "B_madrid" ? "Registration (Madrid)" : "Registration"}
              </span>
            ))}
          </CmpRow>
          <CmpRow label="Status" n={N}>
            {data.marks.map((m) => {
              const isA = m.record_type === "A";
              return (
                <span key={m.id} className="flex items-center gap-2">
                  <PulseDot tone={isA ? "warn" : "ok"} />
                  {isA ? "Pending publication" : "Active"}
                </span>
              );
            })}
          </CmpRow>
          <CmpRow label="Application №" n={N}>
            {data.marks.map((m) => (
              <span key={m.id} className="font-mono text-[12.5px]">
                {m.application_number ?? m.certificate_number ?? m.madrid_number ?? "—"}
              </span>
            ))}
          </CmpRow>
          <CmpRow label="Country" n={N}>
            {data.marks.map((m) => {
              const d = countryDisplay(m.applicant_country_code);
              return (
                <span key={m.id} className="flex items-center gap-1.5">
                  <Flag code={m.applicant_country_code ?? undefined} size={14} />
                  <span className="truncate">{d.name}</span>
                </span>
              );
            })}
          </CmpRow>
          <CmpRow label="Applicant" n={N}>
            {data.marks.map((m) => (
              <span key={m.id} className="block text-[12.5px] truncate" title={m.applicant_name ?? ""}>
                {m.applicant_name ?? "—"}
              </span>
            ))}
          </CmpRow>
          <CmpRow label="IP agent" n={N}>
            {data.marks.map((m) => (
              <span key={m.id} className="block text-mute text-[12.5px] truncate" title={m.ip_agency ?? ""}>
                {m.ip_agency ?? "—"}
              </span>
            ))}
          </CmpRow>

          <CmpHeader>Similarity to {anchor.mark_sample ?? anchor.applicant_name ?? "ANCHOR"}</CmpHeader>
          <CmpRow label="Phonetic (Jaro-Winkler + Metaphone)" n={N}>
            <span className="text-mute">—</span>
            {others.map((m, i) => <ScoreInline key={m.id} value={data.scores[i].phonetic} />)}
          </CmpRow>
          <CmpRow label="Visual (pHash on specimens)" n={N}>
            <span className="text-mute">—</span>
            {others.map((m, i) => (
              <ScoreInline
                key={m.id}
                value={data.scores[i].visual}
                hint={visualConfidenceHint(data.scores[i].visualConfidence)}
              />
            ))}
          </CmpRow>
          <CmpRow label="Class overlap (Nice, Jaccard)" n={N}>
            <span className="text-mute">—</span>
            {others.map((m, i) => <ScoreInline key={m.id} value={data.scores[i].classOverlap} />)}
          </CmpRow>
          <CmpRow label="Vienna overlap (figurative, Jaccard)" n={N}>
            <span className="text-mute">—</span>
            {others.map((m, i) => <ScoreInline key={m.id} value={data.scores[i].viennaOverlap} />)}
          </CmpRow>

          <CmpHeader>Classes &amp; overlap</CmpHeader>
          <CmpRow label="Nice classes" n={N} align="top">
            {data.marks.map((m, i) => (
              <div key={m.id} className="flex flex-wrap gap-1">
                {(m.nice_classes ?? []).map((c) => (
                  <ClassChip key={c} n={c} matched={i > 0 && (anchor.nice_classes ?? []).includes(c)} />
                ))}
              </div>
            ))}
          </CmpRow>
          <CmpRow label="Overlapping classes" n={N} align="top">
            <span className="text-mute">—</span>
            {others.map((m, i) => {
              const overlap = (m.nice_classes ?? []).filter((c) => (anchor.nice_classes ?? []).includes(c));
              return (
                <div key={m.id}>
                  <strong className={overlap.length > 0 ? "text-stamp" : "text-mute"}>
                    {overlap.length} of {m.nice_classes?.length ?? 0}
                  </strong>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {overlap.map((c) => <ClassChip key={c} n={c} matched />)}
                  </div>
                </div>
              );
            })}
          </CmpRow>

          <CmpHeader>Procedural state</CmpHeader>
          <CmpRow label="Filed" n={N}>
            {data.marks.map((m) => (
              <span key={m.id} className="font-mono text-[12.5px] tabular">{formatDateShort(m.submission_date)}</span>
            ))}
          </CmpRow>
          <CmpRow label="Published" n={N}>
            {data.marks.map((m) => (
              <span key={m.id} className="font-mono text-[12.5px] tabular">
                {formatDateShort(m.publication_date_441 ?? m.publication_date_450)}
              </span>
            ))}
          </CmpRow>
          <CmpRow label="Source gazette" n={N}>
            {data.marks.map((m) => (
              <Link
                key={m.id}
                href={`/marks/${m.id}`}
                className="text-[12px] font-mono text-stamp hover:underline truncate"
              >
                /marks/{m.id.slice(0, 8)}…
              </Link>
            ))}
          </CmpRow>

          <CmpHeader>Action</CmpHeader>
          <CmpRow label="Recommended" n={N}>
            {data.marks.map((m, i) => {
              if (i === 0) return <span key={m.id} className="text-mute">Anchor (your mark)</span>;
              const s = data.scores[i - 1];
              const tone: PillTone = s.composite >= 0.75 ? "stamp" : s.composite >= 0.55 ? "warn" : "mute";
              const label = s.composite >= 0.75 ? "Consider opposition" : s.composite >= 0.55 ? "Watch closely" : "Monitor only";
              return <Pill key={m.id} tone={tone}>{label}</Pill>;
            })}
          </CmpRow>
          <CmpRow label="Quick action" n={N}>
            {data.marks.map((m, i) => (
              <div key={m.id} className="flex gap-1.5">
                {i > 0 && <Button variant="tiny">File opposition</Button>}
                <Link
                  href={`/marks/${m.id}`}
                  className="inline-flex items-center gap-1 h-[26px] px-2.5 text-xs rounded border border-line bg-surface text-ink-2 hover:bg-paper-2"
                >
                  Open detail
                </Link>
              </div>
            ))}
          </CmpRow>
        </div>
      </Card>
    </div>
  );
}

/* =========================================================================== */
/* Subcomponents                                                                */
/* =========================================================================== */

function ScorecardBand({
  anchor, scores, marks, weights,
}: { anchor: Trademark; scores: PairScore[]; marks: Trademark[]; weights: Record<string, number> }) {
  const w = {
    phonetic: weights.phonetic ?? 0.4,
    visual: weights.visual ?? 0.25,
    classOverlap: weights.classOverlap ?? 0.2,
    viennaOverlap: weights.viennaOverlap ?? 0.15,
  };
  const otherNames = marks
    .filter((m) => m.id !== anchor.id)
    .map((m) => m.mark_sample ?? m.applicant_name ?? "—")
    .join(", ");
  return (
    <Card className="overflow-visible">
      <div className="px-5 py-5 border-b border-line">
        <p className="text-[10.5px] font-semibold tracking-[0.1em] uppercase text-mute font-mono">Conflict scorecard</p>
        <h2 className="head-serif text-[22px] font-semibold tracking-tight mt-2">
          {anchor.mark_sample ?? anchor.applicant_name ?? "—"}{" "}
          <span className="text-mute font-normal">vs.</span>{" "}
          {otherNames}
        </h2>
        <p className="text-[12.5px] text-mute mt-1.5">
          Composite = {pct(w.phonetic)}% phonetic · {pct(w.visual)}% visual (pHash) ·{" "}
          {pct(w.classOverlap)}% class · {pct(w.viennaOverlap)}% Vienna. Verdict requires both
          composite ≥ threshold AND sight-or-sound similarity (examiner conjunction rule) —
          class overlap alone is not enough.
        </p>
      </div>
      <div className="px-5 py-4 grid gap-4" style={{ gridTemplateColumns: `repeat(${scores.length}, minmax(0,1fr))` }}>
        {scores.map((s) => {
          const m = marks.find((x) => x.id === s.markId)!;
          return (
            <div key={s.markId} className="border border-line rounded-lg p-4">
              <div className="flex items-start gap-3 justify-between">
                <div className="min-w-0">
                  <div className="text-[14px] font-semibold truncate">{m.mark_sample ?? m.applicant_name ?? "—"}</div>
                  <div className="text-[11.5px] text-mute truncate">{m.applicant_name}</div>
                </div>
                <SimilarityRing score={s.composite} size={52} />
              </div>
              <div className="mt-2"><Pill tone={s.verdictTone as PillTone}>{s.verdict}</Pill></div>
              <div className="mt-3 space-y-1.5">
                <ScoreBar label="Phonetic" value={s.phonetic} />
                <ScoreBar
                  label="Visual"
                  value={s.visual}
                  hint={visualConfidenceHint(s.visualConfidence)}
                />
                <ScoreBar label="Class" value={s.classOverlap} />
                <ScoreBar label="Vienna" value={s.viennaOverlap} />
              </div>
              {s.visualConfidence === "typographic" && (
                <p
                  className="mt-2 text-[10.5px] text-mute leading-snug"
                  title="Neither mark had an extracted logo PNG; the visual score is the typographic Jaro-Winkler on the wordmark text, not a perceptual-hash comparison."
                >
                  Visual = typographic proxy (no logo on one or both marks).
                </p>
              )}
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// Map a backend visualConfidence flag to a short hover tooltip the user
// can read alongside the visual score. The actual badge rendering lives
// in ScoreBar / ScoreInline (kept here so all three call sites share one source).
function visualConfidenceHint(c: PairScore["visualConfidence"] | undefined): string | undefined {
  if (c === "phash") return "Perceptual hash on extracted specimens (high confidence).";
  if (c === "typographic") return "Typographic JW on wordmark text — fallback only (inspect specimens).";
  if (c === "none") return "No visual signal available for this mark.";
  return undefined;
}

function ScoreBar({ label, value, hint }: { label: string; value: number; hint?: string }) {
  const v = Math.round(value * 100);
  const color = value >= 0.8 ? "var(--stamp)" : value >= 0.6 ? "var(--warn)" : "var(--ok)";
  return (
    <div className="grid gap-2 items-center" style={{ gridTemplateColumns: "100px 1fr 32px" }} title={hint}>
      <span className="text-[11.5px] text-mute">{label}</span>
      <div className="h-1.5 rounded bg-line overflow-hidden">
        <div className="h-full transition-all" style={{ width: `${v}%`, background: color }} />
      </div>
      <span className="text-[11.5px] font-mono font-bold tabular text-right" style={{ color }}>{v}</span>
    </div>
  );
}

function ScoreInline({ value, hint }: { value: number; hint?: string }) {
  const v = Math.round(value * 100);
  const color = value >= 0.8 ? "text-stamp" : value >= 0.6 ? "text-warn" : "text-ok";
  return (
    <span className="flex items-center gap-2" title={hint}>
      <SimilarityRing score={value} size={28} />
      <span className={`font-semibold ${color}`}>{v}%</span>
    </span>
  );
}

function PlateCell({ mark, anchor }: { mark: Trademark; anchor: boolean }) {
  const md = markDisplay(mark);
  return (
    <div className={`relative rounded-lg p-3 ${anchor ? "bg-stamp-2 border border-stamp-line" : ""}`}>
      {anchor && (
        <span className="absolute top-2 right-2 text-[9.5px] font-mono font-semibold tracking-[0.1em] uppercase text-stamp bg-surface px-1.5 py-0.5 rounded">
          Your mark
        </span>
      )}
      <MarkSpecimen
        info={{ style: "wordmark-sans-bold", color: anchor ? "stamp" : "ink", text: md.text, imageUrl: md.imageUrl }}
        fallbackKey={mark.id}
        size="lg"
        placeholder={md.isPlaceholder}
      />
      <div className="mt-2 flex items-center gap-2">
        <strong className="text-[13.5px] truncate">{md.text}</strong>
        <Pill tone={mark.record_type === "A" ? "A" : "B"} size="sm">{mark.record_type === "A" ? "A" : "B"}</Pill>
      </div>
      <div className="text-[11.5px] text-mute truncate" title={mark.applicant_name ?? ""}>
        {mark.applicant_name}
      </div>
    </div>
  );
}

function CmpLabelHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10.5px] font-semibold tracking-[0.1em] uppercase text-mute font-mono py-2">
      {children}
    </div>
  );
}

function CmpHeader({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="col-span-full text-[10.5px] font-semibold tracking-[0.1em] uppercase text-mute font-mono bg-paper-2 px-4 py-1.5 border-y border-line"
    >
      {children}
    </div>
  );
}

function CmpRow({
  label, children, n, align = "center",
}: { label: string; children: React.ReactNode | React.ReactNode[]; n: number; align?: "top" | "center" }) {
  const cells = React.Children.toArray(children);
  return (
    <>
      <div
        className={`px-4 py-2.5 text-[12.5px] text-ink-2 font-medium border-b border-line bg-paper`}
        style={{ alignSelf: align === "top" ? "start" : "center" }}
      >
        {label}
      </div>
      {cells.slice(0, n).map((cell, i) => (
        <div
          key={i}
          className="px-3 py-2.5 text-[13px] text-ink border-b border-line min-w-0"
          style={{ alignSelf: align === "top" ? "start" : "center" }}
        >
          {cell}
        </div>
      ))}
    </>
  );
}

function pct(n: number): number {
  return Math.round(n * 100);
}

function SkeletonShell() {
  return (
    <div className="max-w-container mx-auto px-6 py-6 space-y-5">
      <div className="h-6 w-72 bg-paper-2 rounded animate-pulse" />
      <div className="h-44 bg-paper-2 rounded-lg animate-pulse" />
      <div className="h-72 bg-paper-2 rounded-lg animate-pulse" />
    </div>
  );
}
