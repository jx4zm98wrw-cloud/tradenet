"use client";

/** Overview dashboard for /admin/gazettes (PR 2 of the gazettes-tab redesign).
 *
 * Renders analytics derived live from GET /api/v1/gazettes/overview:
 *   - Metric cards (Total · Domestic · Madrid reg · Madrid renewal · Coverage %)
 *   - Marks-per-year stacked bar (Chart.js, 4 streams kept distinct)
 *   - Stream-split share bar
 *   - Enrichment (Madrid WIPO % + Domestic NOIP %) — NOT in the overview payload,
 *     so sourced from the existing admin enrichment endpoints
 *   - Madrid origin ranked bars
 *   - Top applicants + Top representatives, each with a Domestic|Madrid toggle
 *
 * The four streams are the four mark_category values; never merged via
 * record_type. Sits between the upload dropzone and the gazette table; PR 3
 * replaces the table below. */

import * as React from "react";
import {
  Chart,
  BarController,
  BarElement,
  CategoryScale,
  LinearScale,
  Tooltip,
  Legend,
  type ChartDataset,
} from "chart.js";
import { Card, SegmentedControl } from "@/components/ui";
import {
  api,
  countryDisplay,
  type GazetteOverview,
  type NamedCount,
} from "@/lib/api";
import { errorMessage, formatNumber } from "@/lib/format";

Chart.register(BarController, BarElement, CategoryScale, LinearScale, Tooltip, Legend);

// Stream colors — fixed by the design spec, identical across the chart, split
// bar, and panels so a stream reads the same everywhere.
const COLOR = {
  applications: "#378ADD", // blue
  domestic_registrations: "#7F77DD", // purple
  madrid_registrations: "#1D9E75", // teal
  madrid_renewals: "#D85A30", // coral
} as const;

// Neutral tick/grid colors that read in both light and dark themes (the app
// supports both; Chart.js can't see CSS vars, so we hardcode a mid-gray).
const TICK = "rgba(136,135,128,0.9)";
const GRID = "rgba(136,135,128,0.15)";

export function GazettesDashboard() {
  const [data, setData] = React.useState<GazetteOverview | null>(null);
  const [enrich, setEnrich] = React.useState<{ madrid: number | null; domestic: number | null }>({
    madrid: null,
    domestic: null,
  });
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    let alive = true;
    api
      .gazettesOverview()
      .then((d) => {
        if (alive) setData(d);
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    // Enrichment % isn't in the overview payload — reuse the existing admin
    // enrichment endpoints (pct_complete is 0..1). Best-effort: a failure here
    // shouldn't blank the whole dashboard.
    Promise.allSettled([api.adminMadridStats(), api.adminDomesticStats()]).then(([m, d]) => {
      if (!alive) return;
      setEnrich({
        madrid: m.status === "fulfilled" ? m.value.pct_complete : null,
        domestic: d.status === "fulfilled" ? d.value.pct_complete : null,
      });
    });
    return () => {
      alive = false;
    };
  }, []);

  if (error && !data) {
    return <p className="text-sm text-rose-600">Overview failed: {error}</p>;
  }
  if (!data) {
    return <div className="text-mute text-sm py-4">Loading overview…</div>;
  }

  const { totals, coverage } = data;
  const domestic = totals.applications + totals.domestic_registrations;
  const coveragePct =
    coverage.expected > 0 ? Math.round((coverage.present / coverage.expected) * 1000) / 10 : 0;

  return (
    <div className="space-y-5">
      {/* Metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <Metric label="Total marks" value={totals.total} />
        <Metric label="Domestic" value={domestic} accent={COLOR.domestic_registrations} />
        <Metric label="Madrid reg" value={totals.madrid_registrations} accent={COLOR.madrid_registrations} />
        <Metric label="Madrid renewal" value={totals.madrid_renewals} accent={COLOR.madrid_renewals} />
        <Metric
          label="Coverage"
          value={`${coveragePct}%`}
          sub={`${formatNumber(coverage.present)} / ${formatNumber(coverage.expected)} issues`}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Marks per year — spans 2 cols on wide screens */}
        <Card className="lg:col-span-2">
          <div className="px-4 py-4">
            <h3 className="text-sm font-semibold mb-3">Marks ingested per year</h3>
            <PerYearChart data={data} />
            <ChartLegend />
          </div>
        </Card>

        {/* Stream split + enrichment stacked in the third column */}
        <div className="space-y-3">
          <Card>
            <div className="px-4 py-4">
              <h3 className="text-sm font-semibold mb-3">Stream split</h3>
              <StreamSplit data={data} />
            </div>
          </Card>
          <Card>
            <div className="px-4 py-4">
              <h3 className="text-sm font-semibold mb-3">Enrichment</h3>
              <EnrichmentRow label="Madrid · WIPO" pct={enrich.madrid} color={COLOR.madrid_registrations} />
              <div className="h-2" />
              <EnrichmentRow label="Domestic · NOIP" pct={enrich.domestic} color={COLOR.domestic_registrations} />
            </div>
          </Card>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        <Card>
          <div className="px-4 py-4">
            <div className="flex items-baseline justify-between mb-3">
              <h3 className="text-sm font-semibold">Madrid origin</h3>
              <span className="text-[10.5px] text-mute font-mono">top holder countries</span>
            </div>
            <MadridOrigin origin={data.madrid_origin} />
          </div>
        </Card>

        <TopPanel
          title="Top applicants"
          domestic={data.top_applicants.domestic}
          madrid={data.top_applicants.madrid}
        />

        <TopPanel
          title="Top representatives"
          domestic={data.top_representatives.domestic}
          madrid={data.top_representatives.madrid}
        />
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: number | string;
  sub?: string;
  accent?: string;
}) {
  return (
    <Card>
      <div className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          {accent && <span className="w-2 h-2 rounded-full" style={{ background: accent }} />}
          <div className="text-[11px] uppercase tracking-[0.08em] text-mute font-mono">{label}</div>
        </div>
        <div className="text-2xl font-semibold tabular mt-1">
          {typeof value === "number" ? formatNumber(value) : value}
        </div>
        {sub && <div className="text-[10.5px] text-mute mt-0.5">{sub}</div>}
      </div>
    </Card>
  );
}

function PerYearChart({ data }: { data: GazetteOverview }) {
  const ref = React.useRef<HTMLCanvasElement | null>(null);

  React.useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const rows = [...data.per_year].sort((a, b) => a.year - b.year);
    const labels = rows.map((r) => String(r.year));
    const datasets: ChartDataset<"bar">[] = [
      { label: "Applications", data: rows.map((r) => r.applications), backgroundColor: COLOR.applications },
      {
        label: "Domestic regs",
        data: rows.map((r) => r.domestic_registrations),
        backgroundColor: COLOR.domestic_registrations,
      },
      {
        label: "Madrid reg",
        data: rows.map((r) => r.madrid_registrations),
        backgroundColor: COLOR.madrid_registrations,
      },
      {
        label: "Madrid renewal",
        data: rows.map((r) => r.madrid_renewals),
        backgroundColor: COLOR.madrid_renewals,
      },
    ];

    const chart = new Chart(canvas, {
      type: "bar",
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { mode: "index", intersect: false },
        },
        scales: {
          x: {
            stacked: true,
            ticks: { color: TICK, font: { size: 10 } },
            grid: { display: false },
          },
          y: {
            stacked: true,
            ticks: { color: TICK, font: { size: 10 } },
            grid: { color: GRID },
          },
        },
      },
    });
    return () => chart.destroy();
  }, [data]);

  return (
    <div className="relative h-64">
      <canvas ref={ref} />
    </div>
  );
}

function ChartLegend() {
  const items: [string, string][] = [
    ["Applications", COLOR.applications],
    ["Domestic regs", COLOR.domestic_registrations],
    ["Madrid reg", COLOR.madrid_registrations],
    ["Madrid renewal", COLOR.madrid_renewals],
  ];
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3">
      {items.map(([label, color]) => (
        <span key={label} className="inline-flex items-center gap-1.5 text-[11px] text-mute">
          <span className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
          {label}
        </span>
      ))}
    </div>
  );
}

function StreamSplit({ data }: { data: GazetteOverview }) {
  const { totals } = data;
  const segs: { label: string; value: number; color: string }[] = [
    { label: "Applications", value: totals.applications, color: COLOR.applications },
    { label: "Domestic regs", value: totals.domestic_registrations, color: COLOR.domestic_registrations },
    { label: "Madrid reg", value: totals.madrid_registrations, color: COLOR.madrid_registrations },
    { label: "Madrid renewal", value: totals.madrid_renewals, color: COLOR.madrid_renewals },
  ];
  const total = totals.total || 1;
  return (
    <div>
      <div className="flex h-3 w-full rounded-full overflow-hidden bg-line">
        {segs.map((s) => (
          <div
            key={s.label}
            style={{ width: `${(s.value / total) * 100}%`, background: s.color }}
            title={`${s.label}: ${formatNumber(s.value)}`}
          />
        ))}
      </div>
      <ul className="mt-3 space-y-1.5">
        {segs.map((s) => (
          <li key={s.label} className="flex items-center justify-between text-[12px]">
            <span className="inline-flex items-center gap-1.5 text-ink-2">
              <span className="w-2 h-2 rounded-full" style={{ background: s.color }} />
              {s.label}
            </span>
            <span className="font-mono text-mute tabular">
              {formatNumber(s.value)}
              <span className="ml-1.5 text-[10.5px]">{Math.round((s.value / total) * 100)}%</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EnrichmentRow({ label, pct, color }: { label: string; pct: number | null; color: string }) {
  const value = pct == null ? null : Math.round(pct * 1000) / 10;
  return (
    <div>
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[12px] text-ink-2">{label}</span>
        <span className="text-[12px] font-mono text-mute tabular">{value == null ? "—" : `${value}%`}</span>
      </div>
      <div className="h-2 bg-line rounded overflow-hidden">
        <div className="h-full transition-all" style={{ width: `${value ?? 0}%`, background: color }} />
      </div>
    </div>
  );
}

function MadridOrigin({ origin }: { origin: GazetteOverview["madrid_origin"] }) {
  if (origin.length === 0) {
    return <p className="text-xs text-mute">No Madrid origin data yet.</p>;
  }
  const max = Math.max(...origin.map((o) => o.n), 1);
  return (
    <ul className="space-y-2">
      {origin.map((o) => {
        const d = countryDisplay(o.country);
        return (
          <li key={o.country} className="flex items-center gap-2 text-[12px]">
            <span className="w-16 shrink-0 inline-flex items-center gap-1 truncate" title={d.name}>
              <span>{d.flag}</span>
              <span className="font-mono">{o.country}</span>
            </span>
            <div className="flex-1 h-2 bg-line rounded overflow-hidden">
              <div
                className="h-full"
                style={{ width: `${(o.n / max) * 100}%`, background: COLOR.madrid_registrations }}
              />
            </div>
            <span className="w-12 text-right font-mono text-mute tabular">{formatNumber(o.n)}</span>
          </li>
        );
      })}
    </ul>
  );
}

function TopPanel({
  title,
  domestic,
  madrid,
}: {
  title: string;
  domestic: NamedCount[];
  madrid: NamedCount[];
}) {
  const [tab, setTab] = React.useState<"domestic" | "madrid">("domestic");
  const rows = tab === "domestic" ? domestic : madrid;
  const barColor = tab === "domestic" ? COLOR.domestic_registrations : COLOR.madrid_registrations;
  const max = Math.max(...rows.map((r) => r.n), 1);

  return (
    <Card>
      <div className="px-4 py-4">
        <div className="flex items-center justify-between mb-3 gap-2">
          <h3 className="text-sm font-semibold">{title}</h3>
          <SegmentedControl<"domestic" | "madrid">
            size="sm"
            value={tab}
            onChange={setTab}
            options={[
              { value: "domestic", label: "Domestic" },
              { value: "madrid", label: "Madrid" },
            ]}
          />
        </div>
        {rows.length === 0 ? (
          <p className="text-xs text-mute">No data.</p>
        ) : (
          <ul className="space-y-2">
            {rows.map((r) => (
              <li key={r.name} className="text-[12px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-ink-2" title={r.name}>
                    {r.name}
                  </span>
                  <span className="font-mono text-mute tabular shrink-0">{formatNumber(r.n)}</span>
                </div>
                <div className="h-1.5 bg-line rounded overflow-hidden mt-1">
                  <div className="h-full" style={{ width: `${(r.n / max) * 100}%`, background: barColor }} />
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Card>
  );
}
