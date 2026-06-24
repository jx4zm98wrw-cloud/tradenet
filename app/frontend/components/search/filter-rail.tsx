"use client";

import * as React from "react";
import {
  api, type CountBucket, type SearchParams as Params, type NiceMode,
  countryDisplay, NICE_LABELS, MARK_CATEGORY_LABELS,
} from "@/lib/api";
import { Flag } from "@/components/ui";
import { Icon } from "@/components/icons";
import { formatNumber } from "@/lib/format";

type Props = {
  filters: Params;
  setFilter: (patch: Partial<Params>) => void;
  niceMode: NiceMode;
  onNiceModeChange: (m: NiceMode) => void;
  countries: CountBucket[];
  classes: CountBucket[];
  applicants: CountBucket[];
  ipAgencies: CountBucket[];
  markCategories: CountBucket[];
  grantedFacet: CountBucket[];
};

// Logical display order for the derived classification facet (lifecycle stage,
// not count). Empty buckets (e.g. unknown=0) are hidden at render time.
const MARK_CATEGORY_ORDER = [
  "domestic_application",
  "domestic_registration",
  "madrid_registration",
  "madrid_renewal",
  "unknown",
] as const;

export function FilterRail({
  filters, setFilter, niceMode, onNiceModeChange,
  countries, classes, applicants, ipAgencies, markCategories, grantedFacet,
}: Props) {
  const [countryModal, setCountryModal] = React.useState(false);
  const [classesModal, setClassesModal] = React.useState(false);
  const [applicantModal, setApplicantModal] = React.useState(false);
  const [agencyModal, setAgencyModal] = React.useState(false);

  return (
    <aside className="space-y-5">
      <RailGroup title="Mark category">
        {MARK_CATEGORY_ORDER.map((cat) => {
          const count = markCategories.find((b) => b.key === cat)?.count ?? 0;
          const active = filters.mark_category === cat;
          // Hide buckets with no rows (unless selected) — keeps "Unclassified"
          // out of the rail when the corpus is clean.
          if (count === 0 && !active) return null;
          return (
            <Row
              key={cat}
              checked={active}
              onToggle={() => setFilter({ mark_category: active ? undefined : cat })}
              label={MARK_CATEGORY_LABELS[cat] ?? cat}
              count={count}
              empty={count === 0 && !active}
            />
          );
        })}
      </RailGroup>

      <RailGroup title="Status">
        <Row
          checked={!!filters.granted}
          onToggle={() => setFilter({ granted: filters.granted ? undefined : true })}
          label="Granted"
          count={grantedFacet.find((b) => b.key === "granted")?.count ?? 0}
        />
      </RailGroup>

      <RailGroup
        title="Country"
        trailing={
          <button
            type="button"
            onClick={() => setCountryModal(true)}
            className="text-[11px] text-stamp hover:text-stamp-deep font-medium"
          >
            Show all
          </button>
        }
      >
        {pinSelected(countries, filters.country ? [filters.country] : [], 8).map((c) => {
          const d = countryDisplay(c.key);
          const active = filters.country === c.key;
          return (
            <Row
              key={c.key}
              checked={active}
              onToggle={() => setFilter({ country: active ? undefined : c.key })}
              prefix={<Flag code={c.key} size={14} />}
              label={d.name}
              count={c.count}
              empty={c.count === 0 && !active}
            />
          );
        })}
      </RailGroup>

      <RailGroup
        title="Nice classes"
        subtitle={`Match marks covering ${niceMode === "any" ? "ANY" : "ALL"} selected class`}
        trailing={
          <select
            className="text-[11px] bg-surface border border-line rounded px-1.5 py-0.5"
            value={niceMode}
            onChange={(e) => onNiceModeChange(e.target.value as NiceMode)}
          >
            <option value="any">ANY of selected</option>
            <option value="all">ALL of selected</option>
          </select>
        }
      >
        {pinSelected(classes, filters.nice_class ?? [], 10).map((c) => {
          const active = (filters.nice_class ?? []).includes(c.key);
          const next = active
            ? (filters.nice_class ?? []).filter((x) => x !== c.key)
            : [...(filters.nice_class ?? []), c.key];
          return (
            <Row
              key={c.key}
              checked={active}
              onToggle={() => setFilter({ nice_class: next.length ? next : undefined })}
              prefix={
                <span className={`font-mono text-[11px] font-bold w-6 ${active ? "text-stamp" : "text-mute"} tabular`}>
                  {c.key}
                </span>
              }
              label={c.label || NICE_LABELS[c.key] || "—"}
              count={c.count}
              empty={c.count === 0 && !active}
            />
          );
        })}
        <button
          type="button"
          onClick={() => setClassesModal(true)}
          className="text-[11px] text-stamp hover:text-stamp-deep font-medium ml-1 mt-1 text-left"
        >
          Show all 45 classes →
        </button>
      </RailGroup>

      <RailGroup title="Applicant type">
        {[
          { v: "Company",  label: "Company" },
          { v: "Personal", label: "Personal" },
        ].map((a) => (
          <Row
            key={a.v}
            checked={filters.applicant_type === a.v}
            onToggle={() => setFilter({ applicant_type: filters.applicant_type === a.v ? undefined : a.v })}
            label={a.label}
          />
        ))}
      </RailGroup>

      <RailGroup
        title="Applicant"
        trailing={
          <button
            type="button"
            onClick={() => setApplicantModal(true)}
            className="text-[11px] text-stamp hover:text-stamp-deep font-medium"
          >
            Show all
          </button>
        }
      >
        {pinSelected(applicants, filters.applicant ? [filters.applicant] : [], 8).map((a) => {
          const active = filters.applicant === a.key;
          return (
            <Row
              key={a.key}
              checked={active}
              onToggle={() => setFilter({ applicant: active ? undefined : a.key })}
              label={a.key}
              count={a.count}
              empty={a.count === 0 && !active}
            />
          );
        })}
      </RailGroup>

      <RailGroup
        title="IP agency"
        trailing={
          <button
            type="button"
            onClick={() => setAgencyModal(true)}
            className="text-[11px] text-stamp hover:text-stamp-deep font-medium"
          >
            Show all
          </button>
        }
      >
        {pinSelected(ipAgencies, filters.ip_agency ? [filters.ip_agency] : [], 8).map((a) => {
          const active = filters.ip_agency === a.key;
          return (
            <Row
              key={a.key}
              checked={active}
              onToggle={() => setFilter({ ip_agency: active ? undefined : a.key })}
              label={a.key}
              count={a.count}
              empty={a.count === 0 && !active}
            />
          );
        })}
      </RailGroup>

      <RailGroup title="Grant date" subtitle="Filters by certificate issue date (B-files only).">
        <div className="grid grid-cols-2 gap-2 px-1">
          <DateField
            label="From"
            value={filters.grant_date_from ?? null}
            onChange={(v) => setFilter({ grant_date_from: v || undefined })}
          />
          <DateField
            label="To"
            value={filters.grant_date_to ?? null}
            onChange={(v) => setFilter({ grant_date_to: v || undefined })}
          />
        </div>
      </RailGroup>

      {countryModal && (
        <FullPickerModal
          title="Filter by country"
          fetchAll={() => api.facetsCountries(filters, 300)}
          selected={filters.country ? [filters.country] : []}
          multi={false}
          renderItem={(b) => {
            const d = countryDisplay(b.key);
            return (
              <>
                <Flag code={b.key} size={14} />
                <span className="flex-1 truncate">{d.name}</span>
                <span className="text-[10px] font-mono text-mute uppercase">{b.key}</span>
              </>
            );
          }}
          onToggle={(k) => setFilter({ country: filters.country === k ? undefined : k })}
          onClose={() => setCountryModal(false)}
        />
      )}
      {classesModal && (
        <FullPickerModal
          title="Filter by Nice class"
          fetchAll={() => api.facetsNiceClasses(filters, 300)}
          selected={filters.nice_class ?? []}
          multi={true}
          renderItem={(b) => (
            <>
              <span className="font-mono text-[12px] font-bold w-7 text-stamp tabular shrink-0">{b.key}</span>
              <span className="flex-1 truncate">{b.label || NICE_LABELS[b.key] || "—"}</span>
            </>
          )}
          onToggle={(k) => {
            const cur = filters.nice_class ?? [];
            const next = cur.includes(k) ? cur.filter((x) => x !== k) : [...cur, k];
            setFilter({ nice_class: next.length ? next : undefined });
          }}
          onClose={() => setClassesModal(false)}
        />
      )}
      {applicantModal && (
        <FullPickerModal
          title="Filter by applicant"
          fetchAll={() => api.facetsApplicants(filters, 300)}
          selected={filters.applicant ? [filters.applicant] : []}
          multi={false}
          renderItem={(b) => <span className="flex-1 truncate">{b.key}</span>}
          onToggle={(k) => setFilter({ applicant: filters.applicant === k ? undefined : k })}
          onClose={() => setApplicantModal(false)}
        />
      )}
      {agencyModal && (
        <FullPickerModal
          title="Filter by IP agency"
          fetchAll={() => api.facetsIpAgencies(filters, 300)}
          selected={filters.ip_agency ? [filters.ip_agency] : []}
          multi={false}
          renderItem={(b) => <span className="flex-1 truncate">{b.key}</span>}
          onToggle={(k) => setFilter({ ip_agency: filters.ip_agency === k ? undefined : k })}
          onClose={() => setAgencyModal(false)}
        />
      )}

      <RailGroup title="Publication date">
        <div className="grid grid-cols-2 gap-2 px-1">
          <DateField label="From" value={null} />
          <DateField label="To" value={null} />
        </div>
        <div className="flex gap-1 flex-wrap mt-2 px-1">
          {["This week", "This month", "Last 90 days", "YTD"].map((p) => (
            <button
              key={p}
              type="button"
              className={`text-[11px] px-2 py-1 rounded border border-line hover:bg-paper-2 ${
                p === "Last 90 days" ? "bg-stamp-2 border-stamp-line text-stamp" : "bg-surface text-ink-2"
              }`}
            >
              {p}
            </button>
          ))}
        </div>
      </RailGroup>
    </aside>
  );
}

function RailGroup({
  title, subtitle, trailing, children,
}: { title: string; subtitle?: string; trailing?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div>
      <div className="flex items-center justify-between mb-1.5">
        <h4 className="text-[10.5px] font-semibold tracking-[0.1em] uppercase text-mute font-mono">{title}</h4>
        {trailing}
      </div>
      {subtitle && <p className="text-[11px] text-mute mb-1.5">{subtitle}</p>}
      <div className="space-y-0.5">{children}</div>
    </div>
  );
}

function Row({
  checked, onToggle, prefix, label, count, empty,
}: {
  checked: boolean;
  onToggle: () => void;
  prefix?: React.ReactNode;
  label: React.ReactNode;
  count?: number;
  empty?: boolean;
}) {
  return (
    <label
      className={`flex items-center gap-2 py-1 px-1 rounded cursor-pointer transition ${
        checked ? "bg-stamp-2" : empty ? "opacity-50 hover:bg-paper-2" : "hover:bg-paper-2"
      }`}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        className="accent-stamp w-3.5 h-3.5"
      />
      {prefix}
      <span className={`flex-1 text-[13px] ${checked ? "text-stamp font-medium" : "text-ink-2"}`}>{label}</span>
      {typeof count === "number" && (
        <span className={`text-[11px] tabular ${checked ? "text-stamp font-semibold" : "text-mute"}`}>
          {formatNumber(count)}
        </span>
      )}
    </label>
  );
}

function DateField({
  label, value, onChange,
}: {
  label: string;
  value: string | null;
  onChange?: (v: string) => void;
}) {
  return (
    <label className="block">
      <div className="text-[11px] text-mute mb-0.5">{label}</div>
      <input
        type="date"
        // controlled when onChange is provided, uncontrolled otherwise (the
        // Publication date input is still a stub — leave it uncontrolled so
        // it doesn't break existing behaviour)
        {...(onChange
          ? { value: value ?? "", onChange: (e) => onChange(e.target.value) }
          : { defaultValue: value ?? "" })}
        className="w-full text-[12px] px-2 py-1.5 border border-line rounded bg-surface"
      />
    </label>
  );
}

function pinSelected(items: CountBucket[], selectedKeys: string[], limit: number): CountBucket[] {
  const top = items.slice(0, limit);
  const present = new Set(top.map((x) => x.key));
  const missing: CountBucket[] = [];
  for (const k of selectedKeys) {
    if (!present.has(k)) {
      const found = items.find((x) => x.key === k);
      missing.push(found ?? { key: k, label: null, count: 0 });
    }
  }
  return [...top, ...missing];
}

/* =========================================================================== */
/* Full picker modal — "Show all 67 countries" / "Show all 45 classes"        */
/* =========================================================================== */

/** Generic full-list picker. Fetches the un-truncated facet list, supports
 * incremental search, and toggles selection through the parent's setFilter.
 * `multi` distinguishes country-style (radio, single) from class-style
 * (checkbox, array). */
function FullPickerModal({
  title,
  fetchAll,
  selected,
  multi,
  renderItem,
  onToggle,
  onClose,
}: {
  title: string;
  fetchAll: () => Promise<CountBucket[]>;
  selected: string[];
  multi: boolean;
  renderItem: (b: CountBucket) => React.ReactNode;
  onToggle: (key: string) => void;
  onClose: () => void;
}) {
  const [items, setItems] = React.useState<CountBucket[] | null>(null);
  const [search, setSearch] = React.useState("");

  React.useEffect(() => {
    let cancelled = false;
    fetchAll().then((data) => {
      if (!cancelled) setItems(data);
    }).catch(() => {
      if (!cancelled) setItems([]);
    });
    return () => { cancelled = true; };
  }, [fetchAll]);

  // Close on Escape.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const q = search.trim().toLowerCase();
  const filtered = items?.filter((b) => {
    if (!q) return true;
    const haystack = `${b.key} ${b.label ?? ""} ${countryDisplay(b.key).name ?? ""} ${NICE_LABELS[b.key] ?? ""}`.toLowerCase();
    return haystack.includes(q);
  }) ?? [];

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-sm grid"
      style={{ alignItems: "flex-start", justifyItems: "center", paddingTop: "8vh" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-surface border border-line rounded-lg shadow-md w-[480px] max-w-[94vw] overflow-hidden flex flex-col"
        style={{ maxHeight: "78vh" }}
        role="dialog"
        aria-label={title}
      >
        <header className="px-4 py-3 border-b border-line flex items-center justify-between shrink-0">
          <h2 className="head-serif text-[15px] font-semibold tracking-tight">{title}</h2>
          <button
            type="button"
            onClick={onClose}
            className="w-7 h-7 grid place-items-center rounded hover:bg-paper-2"
            aria-label="Close"
          >
            <Icon.X className="w-4 h-4 text-mute" />
          </button>
        </header>

        <div className="px-4 py-2.5 border-b border-line shrink-0">
          <div className="relative">
            <Icon.Search className="w-4 h-4 text-mute absolute left-2 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              autoFocus
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search…"
              className="w-full text-sm pl-8 pr-3 h-9 border border-line rounded bg-paper-2 focus:bg-surface focus:border-stamp-line outline-none"
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto py-1">
          {items === null ? (
            <p className="px-4 py-6 text-sm text-mute text-center">Loading…</p>
          ) : filtered.length === 0 ? (
            <p className="px-4 py-6 text-sm text-mute text-center">No matches.</p>
          ) : (
            <ul className="px-2">
              {filtered.map((b) => {
                const active = selected.includes(b.key);
                return (
                  <li key={b.key}>
                    <button
                      type="button"
                      onClick={() => onToggle(b.key)}
                      className={`w-full flex items-center gap-2 py-1.5 px-2 rounded text-[13px] text-left transition ${
                        active ? "bg-stamp-2 text-stamp" : "hover:bg-paper-2 text-ink-2"
                      }`}
                    >
                      <input
                        type={multi ? "checkbox" : "radio"}
                        checked={active}
                        readOnly
                        tabIndex={-1}
                        className="accent-stamp w-3.5 h-3.5 shrink-0"
                      />
                      {renderItem(b)}
                      <span className="text-[11px] tabular text-mute shrink-0">
                        {formatNumber(b.count)}
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <footer className="px-4 py-2.5 border-t border-line flex items-center justify-between bg-paper-2 shrink-0">
          <span className="text-[12px] text-mute">
            {selected.length === 0 ? "No selection" : `${selected.length} selected`}
          </span>
          <button
            type="button"
            onClick={onClose}
            className="text-[12.5px] font-medium px-3 h-7 rounded bg-stamp hover:bg-stamp-deep text-white"
          >
            Done
          </button>
        </footer>
      </div>
    </div>
  );
}
