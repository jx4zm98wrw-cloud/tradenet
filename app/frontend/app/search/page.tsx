"use client";

/** /search — query band + filter rail + grid|table results + multi-select Compare. */

import * as React from "react";
import { Suspense } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Button, SegmentedControl, type SegOption } from "@/components/ui";
import { Icon } from "@/components/icons";
import {
  api, NICE_LABELS, countryDisplay,
  type CountBucket, type NiceMode, type SearchMode, type SearchParams as Params,
  type SearchResults, type SortKey,
} from "@/lib/api";
import { formatNumber } from "@/lib/format";
import { QueryBand } from "@/components/search/query-band";
import { FilterRail } from "@/components/search/filter-rail";
import { ResultsGrid } from "@/components/search/results-grid";
import { ResultsTable } from "@/components/search/results-table";
import { recordRecent } from "@/components/cmdk";

const PAGE_SIZE = 50;

export default function SearchPageShell() {
  return (
    <Suspense fallback={null}>
      <SearchPage />
    </Suspense>
  );
}

function SearchPage() {
  const router = useRouter();
  const sp = useSearchParams();

  // URL-state filters (sharable, browser-back works).
  const filters: Params = React.useMemo(() => {
    const ncs = sp.getAll("nice_class");
    return {
      q: sp.get("q") ?? undefined,
      country: sp.get("country") ?? undefined,
      nice_class: ncs.length ? ncs : undefined,
      record_type: sp.get("record_type") ?? undefined,
      applicant_type: sp.get("applicant_type") ?? undefined,
      year: sp.get("year") ? parseInt(sp.get("year")!, 10) : undefined,
      month: sp.get("month") ? parseInt(sp.get("month")!, 10) : undefined,
      gazette_id: sp.get("gazette_id") ?? undefined,
      ip_agency: sp.get("ip_agency") ?? undefined,
      limit: PAGE_SIZE,
      offset: sp.get("offset") ? parseInt(sp.get("offset")!, 10) : 0,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sp.toString()]);

  const [mode, setMode] = React.useState<SearchMode>((sp.get("mode") as SearchMode) || "text");
  const [threshold, setThreshold] = React.useState<number>(
    sp.get("threshold") ? parseFloat(sp.get("threshold")!) : 0.65
  );
  const [niceMode, setNiceMode] = React.useState<NiceMode>(
    (sp.get("nice_class_mode") as NiceMode) || "any"
  );
  const [sort, setSort] = React.useState<SortKey>("similarity");
  const [view, setView] = React.useState<"grid" | "table">("grid");
  const [searchText, setSearchText] = React.useState<string>(filters.q ?? "");
  const [results, setResults] = React.useState<SearchResults | null>(null);
  const [countries, setCountries] = React.useState<CountBucket[]>([]);
  const [classes, setClasses] = React.useState<CountBucket[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());

  React.useEffect(() => setSearchText(filters.q ?? ""), [filters.q]);

  // Re-fetch facets when filters change. Aborts inflight requests on
  // superseding filter changes so a slow "Vietnam" facet response can't
  // overwrite the newer "China" one (same race the CmdK abort solved).
  React.useEffect(() => {
    const controller = new AbortController();
    const init: RequestInit = { signal: controller.signal };
    api.facetsCountries(filters, 20, init).then(setCountries).catch((e) => {
      if (e?.name !== "AbortError") {
        // intentionally silent — facets are best-effort
      }
    });
    api.facetsNiceClasses(filters, 45, init).then(setClasses).catch((e) => {
      if (e?.name !== "AbortError") {
        // intentionally silent
      }
    });
    return () => controller.abort();
  }, [filters]);

  // Fetch results.
  React.useEffect(() => {
    setLoading(true);
    api.scoredSearch({ ...filters, mode, threshold, nice_class_mode: niceMode, sort })
      .then((r) => { setResults(r); setError(null); })
      .catch((e) => setError(e.message ?? String(e)))
      .finally(() => setLoading(false));
  }, [filters, mode, threshold, niceMode, sort]);

  function updateUrl(next: Params, extras: Record<string, string | undefined> = {}) {
    const u = new URLSearchParams();
    for (const [k, v] of Object.entries(next)) {
      if (v === undefined || v === null || v === "" || k === "limit") continue;
      if (k === "offset" && (!v || v === 0)) continue;
      if (Array.isArray(v)) v.forEach((x) => u.append(k, String(x)));
      else u.append(k, String(v));
    }
    for (const [k, v] of Object.entries(extras)) {
      if (v !== undefined && v !== null && v !== "") u.append(k, v);
    }
    router.push(`/search${u.toString() ? `?${u.toString()}` : ""}`);
  }

  function setFilter(patch: Partial<Params>) {
    updateUrl({ ...filters, ...patch, offset: 0 }, {
      mode: mode !== "text" ? mode : undefined,
      threshold: threshold !== 0.65 ? threshold.toString() : undefined,
      nice_class_mode: niceMode !== "any" ? niceMode : undefined,
    });
  }

  function clearAll() {
    setSelected(new Set());
    router.push("/search");
  }

  function goPage(direction: number) {
    const next = Math.max(0, (filters.offset ?? 0) + direction * PAGE_SIZE);
    updateUrl({ ...filters, offset: next });
  }

  function submitSearch() {
    const q = searchText.trim();
    setFilter({ q: q || undefined });
    if (q) recordRecent({ q, scope: buildScopeLabel(filters) });
  }

  function toggleSel(id: string) {
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  const chips = buildChips(filters, setFilter, niceMode);
  const total = results?.total ?? 0;
  const currentOffset = filters.offset ?? 0;
  const highlightClasses = new Set(filters.nice_class ?? []);

  return (
    <>
      <QueryBand
        mode={mode}
        onModeChange={setMode}
        query={searchText}
        onQueryChange={setSearchText}
        onSubmit={submitSearch}
        threshold={threshold}
        onThresholdChange={setThreshold}
        niceMode={niceMode}
        onNiceModeChange={setNiceMode}
        chips={chips}
        onClearAll={clearAll}
      />

      <div className="max-w-container mx-auto px-6 py-6 grid gap-6" style={{ gridTemplateColumns: "240px 1fr" }}>
        <FilterRail
          filters={filters}
          setFilter={setFilter}
          niceMode={niceMode}
          onNiceModeChange={setNiceMode}
          countries={countries}
          classes={classes}
        />

        <main className="min-w-0 space-y-4">
          <Toolbar
            total={total}
            mode={mode}
            query={filters.q ?? ""}
            view={view}
            onViewChange={setView}
            sort={sort}
            onSortChange={setSort}
            scopeLabel={buildScopeLabel(filters)}
            loading={loading}
          />

          {selected.size > 0 && (
            <SelectionBar
              count={selected.size}
              onClear={() => setSelected(new Set())}
              onCompare={() =>
                router.push(`/compare?ids=${Array.from(selected).join(",")}`)
              }
            />
          )}

          {error && <p className="text-rose-600 text-sm">{error}</p>}

          {!results || (loading && results.items.length === 0) ? (
            <SkeletonGrid />
          ) : results.items.length === 0 ? (
            <EmptyState />
          ) : view === "grid" ? (
            <ResultsGrid results={results.items} selected={selected} onToggle={toggleSel} highlightClasses={highlightClasses} />
          ) : (
            <ResultsTable results={results.items} selected={selected} onToggle={toggleSel} highlightClasses={highlightClasses} />
          )}

          {results && results.items.length > 0 && (
            <Pagination
              offset={currentOffset}
              pageSize={PAGE_SIZE}
              total={results.total}
              loading={loading}
              onPrev={() => goPage(-1)}
              onNext={() => goPage(1)}
            />
          )}
        </main>
      </div>
    </>
  );
}

/* =========================================================================== */
/* Subcomponents                                                                */
/* =========================================================================== */

function Toolbar({
  total, mode, query, view, onViewChange, sort, onSortChange, scopeLabel, loading,
}: {
  total: number; mode: SearchMode; query: string;
  view: "grid" | "table"; onViewChange: (v: "grid" | "table") => void;
  sort: SortKey; onSortChange: (s: SortKey) => void;
  scopeLabel: string; loading: boolean;
}) {
  const subject = mode === "image" ? "uploaded image" : query ? `"${query}"` : "your filters";
  return (
    <div className="flex items-start justify-between gap-4 flex-wrap">
      <div className="min-w-0">
        <div className="text-[15px]">
          <strong className="text-ink">{loading ? "Searching…" : `${formatNumber(total)} trademarks`}</strong>
          <span className="text-mute"> match {subject}</span>
        </div>
        {scopeLabel && <p className="text-xs text-mute mt-1">{scopeLabel}</p>}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <SegmentedControl<"grid" | "table">
          value={view}
          onChange={onViewChange}
          options={[
            { value: "grid", label: <Icon.Grid className="w-3.5 h-3.5" />, title: "Grid" },
            { value: "table", label: <Icon.Rows className="w-3.5 h-3.5" />, title: "Table" },
          ]}
        />
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value as SortKey)}
          className="text-sm px-2.5 h-8 border border-line rounded bg-surface"
        >
          <option value="similarity">Sort: Similarity ↓</option>
          <option value="publication-desc">Sort: Publication ↓</option>
          <option value="applicant-asc">Sort: Applicant A→Z</option>
          <option value="class-count">Sort: Class count</option>
        </select>
        <Button variant="ghost" className="shrink-0">
          <Icon.Download className="w-3.5 h-3.5" />
          Export
        </Button>
      </div>
    </div>
  );
}

function SelectionBar({ count, onClear, onCompare }: { count: number; onClear: () => void; onCompare: () => void }) {
  return (
    <div className="sticky top-14 z-30 bg-ink text-white rounded-lg shadow-md px-4 py-2.5 flex items-center justify-between">
      <div className="flex items-center gap-4">
        <button onClick={onClear} className="text-xs text-white/70 hover:text-white">Clear</button>
        <span className="font-semibold text-sm">{count} selected</span>
      </div>
      <div className="flex items-center gap-2">
        <button className="text-xs text-white/85 hover:text-white">+ Add to watchlist</button>
        <button className="text-xs text-white/85 hover:text-white">Tag</button>
        <button className="text-xs text-white/85 hover:text-white">Export</button>
        <button
          onClick={onCompare}
          disabled={count < 2}
          className="ml-2 inline-flex items-center gap-1 bg-stamp hover:bg-stamp-deep text-white text-xs font-medium h-7 px-3 rounded border border-stamp-deep disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Compare {count} marks →
        </button>
      </div>
    </div>
  );
}

function Pagination({
  offset, pageSize, total, loading, onPrev, onNext,
}: {
  offset: number; pageSize: number; total: number; loading: boolean;
  onPrev: () => void; onNext: () => void;
}) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.floor(offset / pageSize) + 1;
  return (
    <div className="flex items-center justify-between text-sm pt-2">
      <span className="text-mute">
        Showing {formatNumber(offset + 1)}–{formatNumber(Math.min(offset + pageSize, total))} of {formatNumber(total)}
      </span>
      <div className="flex items-center gap-1">
        <button
          onClick={onPrev}
          disabled={offset === 0 || loading}
          className="px-2.5 py-1 rounded border border-line hover:bg-paper-2 disabled:opacity-40"
        >
          ‹
        </button>
        <span className="px-2 text-mute text-xs">
          Page {currentPage} of {totalPages}
        </span>
        <button
          onClick={onNext}
          disabled={offset + pageSize >= total || loading}
          className="px-2.5 py-1 rounded border border-line hover:bg-paper-2 disabled:opacity-40"
        >
          ›
        </button>
      </div>
    </div>
  );
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
      {[...Array(6)].map((_, i) => (
        <div key={i} className="bg-surface border border-line rounded-lg overflow-hidden">
          <div className="aspect-[8/5] bg-paper-2 animate-pulse" />
          <div className="p-3 space-y-2">
            <div className="h-3 bg-paper-2 rounded w-3/5 animate-pulse" />
            <div className="h-3 bg-paper-2 rounded w-4/5 animate-pulse" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="bg-surface border border-line rounded-lg px-6 py-16 text-center">
      <p className="text-sm font-medium text-ink">No matches.</p>
      <p className="text-xs text-mute mt-1">Try lowering the similarity threshold or clearing filters.</p>
    </div>
  );
}

/* ----- chips + scope label ----- */

type Chip = { key: string; label: React.ReactNode; onRemove: () => void };

function buildChips(filters: Params, setFilter: (p: Partial<Params>) => void, niceMode: NiceMode): Chip[] {
  const chips: Chip[] = [];
  if (filters.country) {
    const d = countryDisplay(filters.country);
    chips.push({
      key: "country",
      label: <>Country: {d.flag} {d.name}</>,
      onRemove: () => setFilter({ country: undefined }),
    });
  }
  if (filters.record_type) {
    const m: Record<string, string> = { A: "A (Application)", B_domestic: "B Domestic", B_madrid: "B Madrid" };
    chips.push({ key: "rt", label: <>Type: {m[filters.record_type] ?? filters.record_type}</>, onRemove: () => setFilter({ record_type: undefined }) });
  }
  if (filters.applicant_type) {
    chips.push({ key: "at", label: <>Applicant: {filters.applicant_type}</>, onRemove: () => setFilter({ applicant_type: undefined }) });
  }
  if (filters.year) chips.push({ key: "year", label: `Year ${filters.year}`, onRemove: () => setFilter({ year: undefined }) });
  if (filters.month) chips.push({ key: "month", label: `Month ${filters.month}`, onRemove: () => setFilter({ month: undefined }) });
  if (filters.nice_class && filters.nice_class.length > 0) {
    chips.push({
      key: "cls-set",
      label: (
        <>
          Classes: <span className="font-mono">{filters.nice_class.join(", ")}</span>
        </>
      ),
      onRemove: () => setFilter({ nice_class: undefined }),
    });
  }
  if (filters.ip_agency) chips.push({ key: "agent", label: `Agent: ${filters.ip_agency}`, onRemove: () => setFilter({ ip_agency: undefined }) });
  return chips;
}

function buildScopeLabel(filters: Params): string {
  const parts: string[] = [];
  if (filters.applicant_type) parts.push(`${filters.applicant_type} applicants`);
  if (filters.nice_class?.length) parts.push(`Classes ${filters.nice_class.join(", ")}`);
  if (filters.country) {
    const d = countryDisplay(filters.country);
    parts.push(d.name);
  }
  if (filters.year) parts.push(`Year ${filters.year}`);
  if (filters.record_type) parts.push(filters.record_type);
  return parts.join(" · ");
}
