"use client";

import * as React from "react";
import { Icon } from "@/components/icons";
import { Pill, FilterChip } from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { NICE_LABELS, countryDisplay, type SearchMode, type NiceMode } from "@/lib/api";

/** Search query band — full-width white surface above the body grid.
 *  Mode tabs · input row (text / image / vienna) · similarity slider · filter chips. */

const MODES: { id: SearchMode; label: string; icon: (p: any) => React.JSX.Element }[] = [
  { id: "text",     label: "Text",              icon: Icon.Rows },
  { id: "phonetic", label: "Phonetic / fuzzy",  icon: Icon.Wave },
  { id: "image",    label: "Image",             icon: Icon.Image },
  { id: "vienna",   label: "Vienna code",       icon: Icon.Target },
];

type Chip = { key: string; label: React.ReactNode; onRemove: () => void };

type Props = {
  mode: SearchMode;
  onModeChange: (m: SearchMode) => void;
  query: string;
  onQueryChange: (q: string) => void;
  onSubmit: () => void;
  threshold: number;
  onThresholdChange: (t: number) => void;
  niceMode: NiceMode;
  onNiceModeChange: (m: NiceMode) => void;
  chips: Chip[];
  onClearAll: () => void;
};

export function QueryBand(p: Props) {
  return (
    <div className="bg-surface border-b border-line">
      <div className="max-w-container mx-auto px-6 pt-5 pb-4">
        <ModeTabs value={p.mode} onChange={p.onModeChange} />
        <div className="mt-3">
          {p.mode === "image"
            ? <ImageSearchInput />
            : <TextSearchInput mode={p.mode} value={p.query} onChange={p.onQueryChange} onSubmit={p.onSubmit} />}
        </div>
        <Extras
          threshold={p.threshold}
          onThresholdChange={p.onThresholdChange}
          niceMode={p.niceMode}
          onNiceModeChange={p.onNiceModeChange}
          chips={p.chips}
          onClearAll={p.onClearAll}
        />
      </div>
    </div>
  );
}

function ModeTabs({ value, onChange }: { value: SearchMode; onChange: (m: SearchMode) => void }) {
  return (
    <div className="inline-flex items-center gap-1 bg-paper-2 border border-line rounded-md p-0.5">
      {MODES.map((m) => {
        const Active = m.id === value;
        const Ico = m.icon;
        return (
          <button
            key={m.id}
            type="button"
            onClick={() => onChange(m.id)}
            className={`inline-flex items-center gap-1.5 px-3 h-8 rounded text-[13px] font-medium transition ${
              Active ? "bg-stamp-2 text-stamp" : "text-ink-2 hover:text-ink"
            }`}
          >
            <Ico className="w-3.5 h-3.5" />
            {m.label}
          </button>
        );
      })}
    </div>
  );
}

function TextSearchInput({
  mode, value, onChange, onSubmit,
}: { mode: SearchMode; value: string; onChange: (s: string) => void; onSubmit: () => void }) {
  const placeholder = mode === "phonetic"
    ? "Sound-alike: NEUREX, NEUR*, *FAX… (Soundex / Metaphone applied automatically)"
    : mode === "vienna"
    ? "Vienna codes e.g. 02.01.01, 26.01.18 (separate with comma or space)"
    : "Trademark name, applicant, mark, application number…";
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onSubmit(); }}
      className="relative flex items-center bg-paper-2 hover:bg-surface focus-within:bg-surface border border-line focus-within:border-stamp-line focus-within:ring-2 focus-within:ring-stamp-line/30 rounded-lg h-12 px-4 transition"
    >
      <Icon.Search className="w-4 h-4 text-mute shrink-0" />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="flex-1 bg-transparent outline-none text-[15px] text-ink placeholder:text-mute mx-3"
      />
      {mode === "text" && (
        <div className="hidden md:flex items-center gap-1.5 shrink-0">
          {["applicant:", "class:", "agent:"].map((k) => (
            <span key={k} className="font-mono text-[11px] bg-paper-3 border border-line rounded px-1.5 py-0.5 text-mute">
              {k}
            </span>
          ))}
        </div>
      )}
    </form>
  );
}

function ImageSearchInput() {
  return (
    <div className="bg-paper-2 border border-line rounded-lg p-3 flex items-center gap-3">
      <div className="w-[140px] shrink-0">
        <MarkSpecimen
          info={{ style: "wordmark-sans-bold", color: "stamp", text: "NEUREX" }}
          size="sm"
        />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-semibold">NEUREX_specimen.png</div>
        <div className="text-xs text-mute">
          312 × 84 · pHash <span className="font-mono">9b4a3f8e</span> · OCR'd "NEUREX"
        </div>
        <div className="text-xs text-mute mt-1">Matching by: visual (pHash), OCR'd text, Vienna code inference</div>
      </div>
      <div className="flex flex-col gap-1.5 shrink-0">
        <button className="text-xs px-2.5 h-7 border border-line bg-surface rounded hover:bg-paper-2">Replace</button>
        <button className="text-xs px-2.5 h-7 border border-line bg-surface rounded hover:bg-paper-2">Adjust weights</button>
      </div>
    </div>
  );
}

function Extras({
  threshold, onThresholdChange, niceMode, onNiceModeChange, chips, onClearAll,
}: {
  threshold: number; onThresholdChange: (t: number) => void;
  niceMode: NiceMode; onNiceModeChange: (m: NiceMode) => void;
  chips: Chip[]; onClearAll: () => void;
}) {
  return (
    <div className="mt-3 flex items-center gap-4 flex-wrap">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-mute">Similarity ≥</span>
        <input
          type="range"
          min={0.4} max={0.99} step={0.01}
          value={threshold}
          onChange={(e) => onThresholdChange(parseFloat(e.target.value))}
          className="w-40 accent-stamp"
        />
        <span className="font-mono font-semibold text-stamp tabular w-9 text-right">
          {Math.round(threshold * 100)}%
        </span>
      </div>
      {chips.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] text-mute font-medium mr-0.5">Active:</span>
          {chips.map((c) => (
            <FilterChip key={c.key} onRemove={c.onRemove}>{c.label}</FilterChip>
          ))}
          {chips.some((c) => c.key.startsWith("cls-")) && (
            <button
              type="button"
              onClick={() => onNiceModeChange(niceMode === "any" ? "all" : "any")}
              className="text-[10.5px] font-mono font-semibold tracking-wider uppercase bg-paper-3 border border-line rounded px-1.5 py-0.5 text-ink-2 hover:bg-paper-2"
              title="Toggle class-match semantics"
            >
              {niceMode}
            </button>
          )}
          <button
            type="button"
            onClick={onClearAll}
            className="text-[11px] text-mute hover:text-ink underline-offset-2 hover:underline ml-1"
          >
            Clear all
          </button>
        </div>
      )}
      <button className="ml-auto text-[12.5px] font-medium text-stamp hover:text-stamp-deep hover:underline">
        + Save as watchlist
      </button>
    </div>
  );
}
