"use client";

import * as React from "react";
import { Icon } from "@/components/icons";
import { FilterChip } from "@/components/ui";
import { type SearchMode, type NiceMode } from "@/lib/api";

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
  /** Submit the current query. Optional `override` parameter lets callers
   * (Vienna quick-picks) submit a value they just synthesized in the same
   * tick, sidestepping the searchText useState closure. */
  onSubmit: (override?: string) => void;
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
          {p.mode === "image" ? (
            <ImageSearchInput />
          ) : (
            <>
              <TextSearchInput mode={p.mode} value={p.query} onChange={p.onQueryChange} onSubmit={p.onSubmit} />
              {p.mode === "vienna" && (
                <ViennaQuickPicks
                  onAdd={(code) => {
                    const next = appendCode(p.query, code);
                    p.onQueryChange(next);
                    p.onSubmit(next);  // pass directly; avoids the closure-staleness on searchText
                  }}
                />
              )}
            </>
          )}
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
  const [file, setFile] = React.useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = React.useState<string | null>(null);
  const fileInputRef = React.useRef<HTMLInputElement>(null);

  React.useEffect(() => {
    // Revoke the object URL when the file changes / component unmounts so
    // the browser doesn't accumulate blob refs.
    return () => { if (previewUrl) URL.revokeObjectURL(previewUrl); };
  }, [previewUrl]);

  function onPick(f: File | null) {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setFile(f);
    setPreviewUrl(f ? URL.createObjectURL(f) : null);
  }

  if (!file) {
    return (
      <label
        className="block bg-paper-2 hover:bg-paper-3 border-2 border-dashed border-line hover:border-stamp-line rounded-lg cursor-pointer transition"
        onDragOver={(e) => { e.preventDefault(); }}
        onDrop={(e) => { e.preventDefault(); onPick(e.dataTransfer.files?.[0] ?? null); }}
      >
        <div className="py-8 px-4 flex flex-col items-center gap-2 text-center">
          <Icon.Upload className="w-6 h-6 text-mute" />
          <p className="text-sm font-medium text-ink-2">
            Drop a specimen image here, or <span className="text-stamp underline">click to choose</span>
          </p>
          <p className="text-[11.5px] text-mute max-w-md">
            PNG, JPG, or SVG. The image will be hashed (pHash), OCR&apos;d, and the perceptual signature compared to extracted specimens in the gazette corpus.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/svg+xml,image/webp"
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
            className="hidden"
          />
        </div>
        <EnginePendingBanner />
      </label>
    );
  }

  return (
    <div className="bg-paper-2 border border-line rounded-lg">
      <div className="p-3 flex items-center gap-3">
        {previewUrl && (
          <div className="w-[140px] h-[84px] shrink-0 bg-surface border border-line rounded overflow-hidden grid place-items-center">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={previewUrl} alt="Specimen preview" className="max-w-full max-h-full object-contain" />
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold truncate">{file.name}</div>
          <div className="text-xs text-mute">
            {(file.size / 1024).toFixed(1)} KB · {file.type || "image/*"}
          </div>
          <div className="text-xs text-mute mt-1">
            Matching by: visual (pHash) · OCR&apos;d text · Vienna code inference
          </div>
        </div>
        <div className="flex flex-col gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="text-xs px-2.5 h-7 border border-line bg-surface rounded hover:bg-paper-3"
          >
            Replace
          </button>
          <button
            type="button"
            onClick={() => onPick(null)}
            className="text-xs px-2.5 h-7 border border-line bg-surface rounded hover:bg-paper-3 text-mute"
          >
            Clear
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/png,image/jpeg,image/svg+xml,image/webp"
            onChange={(e) => onPick(e.target.files?.[0] ?? null)}
            className="hidden"
          />
        </div>
      </div>
      <EnginePendingBanner />
    </div>
  );
}

/** A subtle one-line disclosure for modes whose backend engine isn't yet
 * online. Lives on both image and Vienna modes so the user understands
 * the picker is staged but matching isn't running yet. */
function EnginePendingBanner() {
  return (
    <div className="px-3 py-1.5 border-t border-line bg-warn-2 text-[11px] text-ink-2">
      <strong className="text-warn">Engine pending:</strong>{" "}
      visual similarity (pHash + Vienna inference) is staged for the next
      release. Selecting a file does nothing yet — switch to Text or
      Phonetic to actually run a search.
    </div>
  );
}

/** Common Vienna codes (figurative-element classification) the user can
 * one-click into the Vienna textbox. The full classification has ~3000
 * entries; this is a curated shortlist matching what the gazettes contain
 * most often. Full picker would be a follow-up. */
const VIENNA_QUICK_PICKS: { code: string; label: string }[] = [
  { code: "01.01", label: "Stars, comets" },
  { code: "02.01", label: "Men" },
  { code: "02.03", label: "Women" },
  { code: "03.07", label: "Birds" },
  { code: "05.03", label: "Leaves, plants" },
  { code: "05.07", label: "Flowers" },
  { code: "07.01", label: "Buildings" },
  { code: "08.01", label: "Foodstuffs" },
  { code: "26.01", label: "Circles" },
  { code: "26.04", label: "Quadrilaterals" },
  { code: "27.05", label: "Letters w/ stylization" },
  { code: "29.01", label: "Colors" },
];

function appendCode(existing: string, code: string): string {
  const codes = existing.split(/[,\s]+/).map((s) => s.trim()).filter(Boolean);
  if (codes.includes(code)) return existing;
  return [...codes, code].join(", ");
}

function ViennaQuickPicks({ onAdd }: { onAdd: (code: string) => void }) {
  return (
    <div className="mt-2 bg-paper-2 border border-line rounded-lg">
      <div className="px-3 py-2 flex items-center justify-between border-b border-line">
        <span className="text-[10.5px] font-mono uppercase tracking-[0.06em] text-mute">Quick picks</span>
        <span className="text-[10.5px] text-mute">Common Vienna codes · click to add</span>
      </div>
      <div className="px-3 py-2 flex flex-wrap gap-1.5">
        {VIENNA_QUICK_PICKS.map((p) => (
          <button
            key={p.code}
            type="button"
            onClick={() => onAdd(p.code)}
            className="inline-flex items-center gap-1.5 px-2 h-6 border border-line bg-surface hover:bg-stamp-2 hover:border-stamp-line hover:text-stamp rounded text-[11.5px]"
            title={p.label}
          >
            <span className="font-mono tabular text-[11px]">{p.code}</span>
            <span className="text-mute group-hover:text-stamp">{p.label}</span>
          </button>
        ))}
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
