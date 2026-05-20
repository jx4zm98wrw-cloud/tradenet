"use client";

import * as React from "react";
import {
  api, type CountBucket, type SearchParams as Params, type NiceMode,
  countryDisplay, NICE_LABELS,
} from "@/lib/api";
import { Flag } from "@/components/ui";
import { formatNumber } from "@/lib/format";

type Props = {
  filters: Params;
  setFilter: (patch: Partial<Params>) => void;
  niceMode: NiceMode;
  onNiceModeChange: (m: NiceMode) => void;
  countries: CountBucket[];
  classes: CountBucket[];
};

export function FilterRail({ filters, setFilter, niceMode, onNiceModeChange, countries, classes }: Props) {
  return (
    <aside className="space-y-5">
      <RailGroup title="Record type">
        {[
          { v: "A",          label: "A · Application" },
          { v: "B_domestic", label: "B · Domestic" },
          { v: "B_madrid",   label: "B · Madrid" },
        ].map((r) => (
          <Row
            key={r.v}
            checked={filters.record_type === r.v}
            onToggle={() => setFilter({ record_type: filters.record_type === r.v ? undefined : r.v })}
            label={r.label}
          />
        ))}
      </RailGroup>

      <RailGroup
        title="Country"
        trailing={<button className="text-[11px] text-stamp hover:text-stamp-deep font-medium">Show all 67</button>}
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
        <button className="text-[11px] text-stamp hover:text-stamp-deep font-medium ml-1 mt-1 text-left">
          Show all 45 classes →
        </button>
      </RailGroup>

      <RailGroup title="Applicant">
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

function DateField({ label, value }: { label: string; value: string | null }) {
  return (
    <label className="block">
      <div className="text-[11px] text-mute mb-0.5">{label}</div>
      <input
        type="date"
        defaultValue={value ?? ""}
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
