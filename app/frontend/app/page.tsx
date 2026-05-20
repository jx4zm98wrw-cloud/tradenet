"use client";

/** Today — the user's morning landing.
 * Hero with this week's digest + KPI tiles, then a 2-up "findings + oppositions",
 * a 2-up "watchlists + recent activity", and a collapsible pipeline strip.
 * Most data is real; findings + watchlists are mocked until PR #5. */

import Link from "next/link";
import * as React from "react";
import { useRouter } from "next/navigation";
import {
  Card, CardHead, CardFoot, Button, LinkButton, Pill, Flag,
  ClassChip, SimilarityRing, ProgressBar,
} from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { Icon } from "@/components/icons";
import {
  api, type Finding, type OppositionWindow, type Watchlist,
  type TodayDigest, type PipelineStats, countryDisplay,
} from "@/lib/api";

const RECENT_SEARCHES = [
  { id: "s-1", q: "neur*",                      scope: "Class 5,10 · VN+SG+IN",      count: 24, when: "12 min ago", icon: "🔍" },
  { id: "s-2", q: "image: NEUREX_logo.png",     scope: "Visual sim ≥ 0.75",          count: 7,  when: "1 hr ago",   icon: "📷" },
  { id: "s-3", q: "applicant: Masan",           scope: "All classes · Last 90 days", count: 18, when: "yesterday",  icon: "👤" },
  { id: "s-4", q: "vex*",                       scope: "Class 5 · Worldwide",        count: 11, when: "yesterday",  icon: "🔍" },
];

export default function TodayPage() {
  const router = useRouter();
  const [digest, setDigest] = React.useState<TodayDigest | null>(null);
  const [findings, setFindings] = React.useState<Finding[]>([]);
  const [oppositions, setOpps] = React.useState<OppositionWindow[]>([]);
  const [watchlists, setWatchlists] = React.useState<Watchlist[]>([]);
  const [pipeline, setPipeline] = React.useState<PipelineStats | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    Promise.all([
      api.todayDigest(),
      api.findings(),
      api.oppositionWindows("open", 20),
      api.watchlists(),
      api.pipelineStats(),
    ])
      .then(([d, f, o, w, p]) => {
        setDigest(d);
        setFindings(f);
        setOpps(o);
        setWatchlists(w);
        setPipeline(p);
      })
      .catch((e) => setError(e.message ?? String(e)));
  }, []);

  if (error) {
    return (
      <div className="max-w-container mx-auto px-6 py-12">
        <p className="text-rose-600">Failed to load Today: {error}</p>
      </div>
    );
  }

  const closingSoon = oppositions.filter((o) => o.daysLeft <= 14).length;
  const todayLabel = digest ? formatEyebrow(digest.today) : "—";

  return (
    <div className="max-w-container mx-auto px-6 py-6 space-y-6">
      {/* ===== Hero strip ===== */}
      <section className="grid grid-cols-1 lg:grid-cols-[1.4fr_1fr] gap-6 pb-6 border-b border-line">
        <div>
          <p className="text-[11px] font-semibold tracking-[0.12em] uppercase text-mute font-mono">
            {todayLabel} · This week's digest
          </p>
          <h1 className="head-serif mt-2 text-[30px] leading-[1.25] tracking-[-0.015em] font-semibold">
            <span className="text-stamp">
              {digest ? `${digest.totalNew} new findings` : <Shimmer w={220} />}
            </span>
            <span className="text-mute">
              {digest ? ` across ${digest.watchlistsWithFindings} watchlists.` : ""}
            </span>
          </h1>
          <p className="mt-2 text-sm text-mute">
            {closingSoon} opposition window{closingSoon === 1 ? "" : "s"} closing in the next 14 days · last sync{" "}
            {digest && fmtDateTime(digest.lastSyncAt)}
          </p>
          <div className="mt-4 flex gap-2.5">
            <Button variant="primary" onClick={() => router.push("/watchlists")}>
              Review findings <span aria-hidden>→</span>
            </Button>
            <Button variant="ghost" onClick={() => router.push("/search")}>New search</Button>
          </div>
        </div>

        <KpiRow digest={digest} oppositions={oppositions} />
      </section>

      {/* ===== Two-up: findings + oppositions ===== */}
      <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_1fr] gap-5">
        <Card>
          <CardHead
            title="New findings"
            sub="Marks landed this period that match one of your watchlists, ranked by composite similarity."
            action={<LinkButton href="/search">Open in Search →</LinkButton>}
          />
          <ul className="divide-y divide-line">
            {findings.length === 0 ? (
              <li className="px-5 py-10 text-center text-sm text-mute">No new findings this period.</li>
            ) : findings.map((f) => <FindingRow key={f.mark.id} f={f} onClick={() => router.push(`/marks/${f.mark.id}`)} />)}
          </ul>
          <CardFoot>
            <span>Showing {findings.length} of {findings.length}</span>
            <div className="flex gap-2">
              <Button variant="tiny">Dismiss all</Button>
              <Button variant="tiny">Generate client report</Button>
            </div>
          </CardFoot>
        </Card>

        <Card>
          <CardHead
            title="Opposition windows"
            sub="Days remaining to file opposition against a published application. Vietnam: 5 months from publication."
            action={<LinkButton href="#">Calendar view →</LinkButton>}
          />
          <ul className="divide-y divide-line">
            {oppositions.length === 0 ? (
              <li className="px-5 py-10 text-center text-sm text-mute">No open opposition windows.</li>
            ) : oppositions.slice(0, 6).map((o) => (
              <OppositionRow key={o.markId} o={o} onOpen={() => router.push(`/marks/${o.markId}`)} />
            ))}
          </ul>
        </Card>
      </div>

      {/* ===== Two-up: watchlists + recent activity ===== */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Card>
          <CardHead
            title="Watchlists"
            sub="Saved queries that re-run automatically each gazette issue."
            action={<LinkButton href="/watchlists">+ New watchlist</LinkButton>}
          />
          <ul className="divide-y divide-line">
            {watchlists.map((w) => (
              <li key={w.id} className="px-4 py-3 flex items-center gap-3">
                <span
                  className="w-1 self-stretch rounded-sm"
                  style={{ background: w.newCount > 0 ? "var(--stamp)" : "var(--line-strong)" }}
                />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{w.name}</div>
                  <div className="text-xs text-mute truncate">
                    <span className="text-ink-2">{w.client}</span> · {w.queryDesc}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className={`text-lg font-semibold tabular ${w.newCount > 0 ? "text-stamp" : "text-mute"}`}>
                    {w.newCount > 0 ? `+${w.newCount}` : "—"}
                  </div>
                  <div className="text-[11px] text-mute">{w.totalCount.toLocaleString()} total</div>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card>
          <CardHead title="Your recent activity" sub="Searches you've run. Click to re-execute against the latest gazette." />
          <ul className="divide-y divide-line">
            {RECENT_SEARCHES.map((s) => (
              <li
                key={s.id}
                onClick={() => router.push(`/search?q=${encodeURIComponent(s.q)}`)}
                className="px-4 py-2.5 flex items-center gap-3 hover:bg-paper-2 cursor-pointer"
              >
                <span className="w-7 h-7 rounded grid place-items-center bg-paper-2 text-base">{s.icon}</span>
                <div className="flex-1 min-w-0">
                  <div className="font-mono text-[13px] truncate">{s.q}</div>
                  <div className="text-[11px] text-mute truncate">{s.scope}</div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-sm font-semibold tabular">{s.count}</div>
                  <div className="text-[11px] text-mute">{s.when}</div>
                </div>
              </li>
            ))}
          </ul>
          <CardFoot>
            <span>Last 7 days</span>
            <LinkButton href="/search">View all →</LinkButton>
          </CardFoot>
        </Card>
      </div>

      {/* ===== Pipeline strip (collapsible) ===== */}
      {pipeline && <PipelineCollapse stats={pipeline} />}
    </div>
  );
}

/* =========================================================================== */
/* Subcomponents                                                                */
/* =========================================================================== */

function KpiRow({ digest, oppositions }: { digest: TodayDigest | null; oppositions: OppositionWindow[] }) {
  const opps14 = oppositions.filter((o) => o.daysLeft <= 14).length;
  return (
    <div className="grid grid-cols-3 bg-line gap-px rounded-lg overflow-hidden border border-line">
      <Kpi label="Findings"      value={digest?.totalNew}            sub="across all watchlists"      tone="stamp" />
      <Kpi label="Opposition · 7d" value={digest?.closingIn7Days}    sub={`${opps14} within 14d`}     tone={digest && digest.closingIn7Days > 0 ? "warn" : "mute"} />
      <Kpi label="Watchlists"    value={digest?.activeWatchlists}    sub={`${digest?.watchlistsWithFindings ?? 0} with new findings`} tone="ink" />
    </div>
  );
}

function Kpi({ label, value, sub, tone }: { label: string; value?: number; sub: string; tone: "stamp" | "warn" | "mute" | "ink" }) {
  const toneClass = { stamp: "text-stamp", warn: "text-warn", mute: "text-ink", ink: "text-ink" }[tone];
  return (
    <div className="bg-surface px-4 py-3">
      <p className="text-[10px] font-semibold tracking-wider uppercase font-mono text-mute">{label}</p>
      <p className={`mt-1 text-[32px] font-semibold tabular leading-none ${toneClass}`}>
        {value ?? "—"}
      </p>
      <p className="mt-2 text-[11px] text-mute">{sub}</p>
    </div>
  );
}

function FindingRow({ f, onClick }: { f: Finding; onClick: () => void }) {
  const m = f.mark;
  const d = countryDisplay(m.applicant_country_code);
  const markText = m.mark_sample || m.applicant_name || "—";
  const matchedClasses = new Set(["05"]); // mocked — design highlights class 5
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="w-full text-left grid items-center gap-4 px-4 py-3 hover:bg-paper-2 transition"
        style={{ gridTemplateColumns: "100px 1fr auto" }}
      >
        <div className="w-[100px]">
          <MarkSpecimen
            info={{
              style: "wordmark-sans-bold",
              color: "ink",
              text: trimMark(markText),
            }}
            fallbackKey={m.id}
            size="sm"
          />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">{trimMark(markText)}</span>
            <Pill tone={m.record_type === "A" ? "A" : "B"} size="sm">
              {m.record_type === "A" ? "A" : "B"}
            </Pill>
            {(m.nice_classes ?? []).slice(0, 4).map((c) => (
              <ClassChip key={c} n={c} matched={matchedClasses.has(c)} />
            ))}
          </div>
          <div className="mt-1 text-xs text-ink-2 truncate">{m.applicant_name}</div>
          <div className="mt-1 text-xs text-mute flex items-center gap-1.5 flex-wrap">
            <Flag code={m.applicant_country_code ?? undefined} size={12} />
            <span>{d.name}</span>
            <span className="text-fade">·</span>
            <span className="font-mono">{m.application_number ?? m.certificate_number ?? m.madrid_number ?? "—"}</span>
            <span className="text-fade">·</span>
            <span>published {fmtDate(m.publication_date_441 ?? m.publication_date_450)}</span>
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          <SimilarityRing score={f.score} size={42} />
          <div className="text-right w-[180px]">
            <div className="text-xs text-stamp font-semibold truncate">{f.watchName}</div>
            <div className="text-[11px] text-mute truncate">{f.reason}</div>
          </div>
        </div>
      </button>
    </li>
  );
}

function OppositionRow({ o, onOpen }: { o: OppositionWindow; onOpen: () => void }) {
  const urgent = o.daysLeft <= 14;
  const totalWindow = 150;
  const elapsed = totalWindow - o.daysLeft;
  return (
    <li className={`relative px-4 py-3 flex items-center gap-3 ${urgent ? "bg-gradient-to-r from-stamp-2 to-transparent" : ""}`}>
      <div className="w-16 text-center shrink-0">
        <div className={`text-[28px] leading-none font-bold tabular ${urgent ? "text-stamp" : "text-ink"}`}>
          {o.daysLeft}
        </div>
        <div className="mt-0.5 text-[10px] font-mono uppercase tracking-wider text-mute">days</div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="font-medium text-sm truncate">{trimMark(o.markName ?? "—")}</div>
        <div className="text-xs text-mute truncate">{o.applicant}</div>
        <div className="mt-1 flex items-center gap-1.5 text-xs flex-wrap">
          {o.classes.slice(0, 4).map((c) => <ClassChip key={c} n={c} />)}
          <span className="text-fade">·</span>
          <span className="text-mute">closes {fmtDate(o.closesAt)}</span>
          {o.watchName && (
            <>
              <span className="text-fade">·</span>
              <span className="text-stamp">{o.watchName}</span>
            </>
          )}
        </div>
      </div>
      <Button variant="tiny" onClick={onOpen} className="shrink-0">Open</Button>
      <div className="absolute left-0 right-0 bottom-0">
        <ProgressBar value={Math.max(0.04, Math.min(1, elapsed / totalWindow))} daysLeft={o.daysLeft} height={2} className="rounded-none bg-transparent" />
      </div>
    </li>
  );
}

function PipelineCollapse({ stats }: { stats: PipelineStats }) {
  return (
    <details className="bg-surface border border-line rounded-lg overflow-hidden group">
      <summary className="px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-paper-2 list-none">
        <span className="inline-flex items-center gap-2 text-sm font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-ok" />
          Ingest pipeline · {stats.gazettesProcessed} / {stats.gazettesTotal} gazettes processed
        </span>
        <span className="text-xs text-mute ml-auto truncate">
          Latest: <span className="font-mono">{stats.latestGazetteName}</span>
          {stats.latestGazetteAt && ` · ${relTime(stats.latestGazetteAt)}`}
          {stats.latestGazetteRows && ` · ${stats.latestGazetteRows.toLocaleString()} rows`}
        </span>
        <span className="text-xs text-stamp font-medium shrink-0 group-open:hidden">Show details</span>
        <span className="text-xs text-stamp font-medium shrink-0 hidden group-open:inline">Hide</span>
      </summary>
      <div className="px-4 pb-4 pt-2 border-t border-line">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <PipelineStat label="Total trademarks ingested" value={stats.totalTrademarks.toLocaleString()} />
          <PipelineStat label="This quarter" value={stats.thisQuarter.toLocaleString()} />
          <PipelineStat label="Pages OCR'd" value={stats.pagesOcred.toLocaleString()} />
          <PipelineStat
            label="Manual review queue"
            value={stats.reviewQueue.toLocaleString() + " rows"}
            valueClass={stats.reviewQueue > 0 ? "text-warn" : ""}
          />
        </div>
        <p className="mt-3 text-[11px] text-mute">
          Pipeline details are collapsed by default — full management lives in the Gazettes tab for admins.
        </p>
      </div>
    </details>
  );
}

function PipelineStat({ label, value, valueClass = "" }: { label: string; value: string; valueClass?: string }) {
  return (
    <div className="bg-paper-2 rounded px-3 py-2">
      <p className="text-[11px] text-mute">{label}</p>
      <p className={`text-base font-semibold tabular mt-0.5 ${valueClass}`}>{value}</p>
    </div>
  );
}

/* ----- helpers ----- */

function Shimmer({ w = 160 }: { w?: number }) {
  return <span className="inline-block h-6 align-middle bg-paper-2 rounded animate-pulse" style={{ width: w }} />;
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" })
    + " " + d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function formatEyebrow(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { weekday: "long", day: "2-digit", month: "long" });
}

function relTime(iso: string): string {
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const m = Math.round(diff / 60_000);
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  return new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
}

function trimMark(s: string, max = 40): string {
  return s.length > max ? s.slice(0, max - 1) + "…" : s;
}
