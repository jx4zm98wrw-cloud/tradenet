"use client";

/** Group-by-year list for /admin/gazettes (PR 3 of the gazettes-tab redesign).
 *
 * Replaces the old flat, 50-row-capped table. Renders a collapsible accordion
 * keyed by issue_year (newest first, newest open by default). Each year's
 * issues are lazy-fetched on first expand via listGazettes({year}) and cached
 * — so all years are reachable without ever pulling every row at once.
 *
 * A filter bar above the accordion narrows the loaded rows client-side:
 *   - search input ("T6", "2024", filename text)
 *   - A/B type segmented toggle (All / Applications / Registrations)
 *   - status select (All / Completed / Processing / Failed)
 *
 * The type/status filters are also forwarded to listGazettes() so a year that
 * hasn't been expanded yet fetches the already-narrowed subset; the search box
 * is purely client-side over loaded rows. */

import Link from "next/link";
import * as React from "react";
import { Card, Pill, PulseDot, SegmentedControl } from "@/components/ui";
import { Icon } from "@/components/icons";
import { api, type Gazette, type GazetteYearSummary } from "@/lib/api";
import { errorMessage, formatNumber } from "@/lib/format";

type TypeFilter = "all" | "A" | "B";
type StatusFilter = "all" | "completed" | "processing" | "failed";

export function GazettesByYear({ refreshKey = 0 }: { refreshKey?: number }) {
  const [years, setYears] = React.useState<GazetteYearSummary[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [search, setSearch] = React.useState("");
  const [typeFilter, setTypeFilter] = React.useState<TypeFilter>("all");
  const [statusFilter, setStatusFilter] = React.useState<StatusFilter>("all");

  // Per-year expand state + lazy-loaded rows. Keyed by year.
  const [open, setOpen] = React.useState<Record<number, boolean>>({});
  const [rows, setRows] = React.useState<Record<number, Gazette[]>>({});
  const [loading, setLoading] = React.useState<Record<number, boolean>>({});

  const gazetteType = typeFilter === "all" ? undefined : typeFilter;
  const status = statusFilter === "all" ? undefined : statusFilter;

  // Load the accordion headers. Re-runs when an upload bumps refreshKey so a
  // freshly-ingested year appears (and the newest year defaults open).
  React.useEffect(() => {
    let alive = true;
    api
      .gazetteYears()
      .then((ys) => {
        if (!alive) return;
        setYears(ys);
        setError(null);
        // Open the newest year by default (years come back newest-first).
        if (ys.length > 0) setOpen((prev) => (prev[ys[0].year] ? prev : { ...prev, [ys[0].year]: true }));
      })
      .catch((e) => {
        if (alive) setError(errorMessage(e));
      });
    return () => {
      alive = false;
    };
  }, [refreshKey]);

  // Lazy-fetch a year's rows the first time it opens (or when the server-side
  // type/status filters change while it's open). Cached by a composite key so
  // we don't refetch the same (year, type, status) combination.
  const loadedKeys = React.useRef<Set<string>>(new Set());

  const loadYear = React.useCallback(
    async (year: number) => {
      const key = `${year}|${gazetteType ?? ""}|${status ?? ""}`;
      if (loadedKeys.current.has(key)) return;
      loadedKeys.current.add(key);
      setLoading((p) => ({ ...p, [year]: true }));
      try {
        const r = await api.listGazettes({ year, gazette_type: gazetteType, status });
        setRows((p) => ({ ...p, [year]: r.items }));
      } catch (e) {
        loadedKeys.current.delete(key);
        setError(errorMessage(e));
      } finally {
        setLoading((p) => ({ ...p, [year]: false }));
      }
    },
    [gazetteType, status],
  );

  // When the server-side filters change, drop the cache + rows. Declared
  // before the auto-load effect so on a filter change it runs first (effects
  // fire in declaration order): cache is cleared, then the auto-load effect
  // refetches the open years with the new filter exactly once.
  React.useEffect(() => {
    loadedKeys.current = new Set();
    setRows({});
  }, [gazetteType, status]);

  // Auto-load any open-but-unloaded year. Covers the newest year, which is
  // force-opened after gazetteYears() resolves (bypassing toggle()), as well
  // as manual toggles and filter changes — loadYear's identity changes when
  // gazetteType/status change, so this re-runs and refetches open years with
  // the new filter. loadYear is idempotent (caches by year|type|status).
  React.useEffect(() => {
    for (const [y, isOpen] of Object.entries(open)) {
      if (isOpen) loadYear(Number(y));
    }
  }, [open, loadYear]);

  function toggle(year: number) {
    setOpen((p) => ({ ...p, [year]: !p[year] }));
  }

  // Client-side search filter over a year's loaded rows. Matches "T<n>",
  // the year, or the raw filename, case-insensitively.
  const matchesSearch = React.useCallback(
    (g: Gazette) => {
      const q = search.trim().toLowerCase();
      if (!q) return true;
      const issue = `t${g.issue_number ?? ""}`;
      const hay = `${issue} ${g.issue_year ?? ""} ${g.filename}`.toLowerCase();
      return hay.includes(q);
    },
    [search],
  );

  if (error && !years) {
    return <p className="text-sm text-rose-600">Failed to load gazettes: {error}</p>;
  }
  if (!years) {
    return <div className="text-mute text-sm py-4">Loading gazettes…</div>;
  }

  return (
    <div className="space-y-3">
      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative flex-1 min-w-[180px]">
          <Icon.Search className="w-4 h-4 text-mute absolute left-2.5 top-1/2 -translate-y-1/2" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search issues — T6, 2024…"
            className="w-full pl-8 pr-3 py-1.5 text-sm border border-line rounded-md bg-surface focus:outline-none focus:border-stamp-line"
          />
        </div>
        <SegmentedControl<TypeFilter>
          size="sm"
          value={typeFilter}
          onChange={setTypeFilter}
          options={[
            { value: "all", label: "All" },
            { value: "A", label: "Applications" },
            { value: "B", label: "Registrations" },
          ]}
        />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
          className="text-sm border border-line rounded-md bg-surface px-2.5 py-1.5 focus:outline-none focus:border-stamp-line"
        >
          <option value="all">All statuses</option>
          <option value="completed">Completed</option>
          <option value="processing">Processing</option>
          <option value="failed">Failed</option>
        </select>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {years.length === 0 ? (
        <Card>
          <div className="px-6 py-16 text-center">
            <p className="text-sm font-medium text-ink">No gazettes yet.</p>
            <p className="text-xs text-mute mt-1">Drop a PDF above to ingest your first one.</p>
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {years.map((y) => (
            <YearSection
              key={y.year}
              summary={y}
              open={!!open[y.year]}
              loading={!!loading[y.year]}
              rows={rows[y.year]}
              search={search}
              matchesSearch={matchesSearch}
              onToggle={() => toggle(y.year)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function YearSection({
  summary,
  open,
  loading,
  rows,
  search,
  matchesSearch,
  onToggle,
}: {
  summary: GazetteYearSummary;
  open: boolean;
  loading: boolean;
  rows: Gazette[] | undefined;
  search: string;
  matchesSearch: (g: Gazette) => boolean;
  onToggle: () => void;
}) {
  const visible = (rows ?? []).filter(matchesSearch);

  return (
    <Card>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-paper-2 transition"
        aria-expanded={open}
      >
        <svg
          viewBox="0 0 16 16"
          className={`w-4 h-4 text-mute transition-transform ${open ? "rotate-90" : ""}`}
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          aria-hidden="true"
        >
          <path d="M6 4l4 4-4 4" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="font-semibold text-[15px] tabular">{summary.year}</span>
        <span className="text-[12.5px] text-mute">
          {summary.issue_count} issue{summary.issue_count === 1 ? "" : "s"} · {formatNumber(summary.marks)} marks
        </span>
        {summary.flagged > 0 && (
          <Pill tone="warn" size="sm">
            {summary.flagged} flagged
          </Pill>
        )}
      </button>

      {open && (
        <div className="border-t border-line">
          {loading && !rows ? (
            <div className="px-4 py-6 text-sm text-mute">Loading issues…</div>
          ) : visible.length === 0 ? (
            <div className="px-4 py-6 text-sm text-mute">
              {search.trim() ? "No issues match your search." : "No issues."}
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {visible
                .slice()
                .sort((a, b) => (b.issue_number ?? 0) - (a.issue_number ?? 0))
                .map((g) => (
                  <IssueRow key={g.id} g={g} />
                ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}

function IssueRow({ g }: { g: Gazette }) {
  return (
    <li className="flex items-center gap-3 px-4 py-2.5 text-sm hover:bg-paper-2">
      <span className="font-semibold text-[13px] w-12 shrink-0">T{g.issue_number ?? "?"}</span>
      {g.gazette_type === "A" ? (
        <Pill tone="A" size="sm">
          Applications
        </Pill>
      ) : (
        <Pill tone="B" size="sm">
          Registrations
        </Pill>
      )}
      <StatusPill g={g} />
      <span className="font-mono text-mute tabular text-[12.5px] ml-auto">{formatNumber(g.row_count)} marks</span>
      {g.status === "completed" && (
        <Link
          href={`/search?gazette_id=${g.id}`}
          className="text-[12.5px] font-medium text-stamp hover:text-stamp-deep shrink-0"
        >
          Browse →
        </Link>
      )}
    </li>
  );
}

function StatusPill({ g }: { g: Gazette }) {
  if (g.error_message || g.status === "failed") {
    return (
      <Pill tone="warn" size="sm">
        <PulseDot tone="warn" /> Failed
      </Pill>
    );
  }
  if (g.status === "processing" || g.status === "uploaded") {
    return (
      <Pill tone="warn" size="sm">
        <PulseDot tone="warn" /> {g.status[0].toUpperCase() + g.status.slice(1)}
      </Pill>
    );
  }
  if (g.needs_review) {
    return (
      <Pill tone="warn" size="sm">
        ⚠ Needs review
      </Pill>
    );
  }
  return (
    <Pill tone="ok" size="sm">
      <PulseDot tone="ok" /> Completed
    </Pill>
  );
}
