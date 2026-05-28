"use client";

/** PR #0 — primitive showcase. Not linked from nav. Open at /dev/showcase to
 * visually verify the design system without touching real pages. Safe to delete
 * once PR #1+ have validated everything in production routes. */

import { Card, CardHead, CardFoot, Button, LinkButton, Pill, FilterChip, Flag, Kbd, SegmentedControl, ClassChip, ClassChipFull, SimilarityRing, PulseDot, ProgressBar, IconButton } from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { Icon } from "@/components/icons";
import { useState } from "react";

export default function Showcase() {
  const [view, setView] = useState<"grid" | "table">("grid");
  return (
    <div className="max-w-container mx-auto px-6 py-8 space-y-8">
      <div>
        <h1 className="head-serif text-2xl font-semibold tracking-tight">Design system showcase</h1>
        <p className="text-sm text-mute mt-1">PR #0 primitives — Be Vietnam Pro · oxblood brand · cozy density.</p>
      </div>

      {/* Buttons */}
      <Card>
        <CardHead title="Buttons" sub="Variants: primary / ghost / tiny / tiny-primary. Plus link-button & icon-button." />
        <div className="p-5 flex flex-wrap items-center gap-3">
          <Button variant="primary">Review findings →</Button>
          <Button variant="ghost">New search</Button>
          <Button variant="tiny">Tag</Button>
          <Button variant="tiny-primary">File opposition</Button>
          <LinkButton href="#">Open in Search →</LinkButton>
          <IconButton title="Alerts" hasDot><Icon.Bell className="w-4 h-4" /></IconButton>
          <Kbd>⌘K</Kbd>
        </div>
      </Card>

      {/* Pills */}
      <Card>
        <CardHead title="Pills" sub="Tones: ink, stamp, ok, warn, mute, A, B." />
        <div className="p-5 flex flex-wrap items-center gap-3">
          <Pill tone="ink">Ink default</Pill>
          <Pill tone="stamp">Stamp</Pill>
          <Pill tone="ok"><span className="pulse-dot text-ok" /> Active registration</Pill>
          <Pill tone="warn"><span className="pulse-dot text-warn" /> Examination pending</Pill>
          <Pill tone="mute">Closed</Pill>
          <Pill tone="A" size="sm">A</Pill>
          <Pill tone="B" size="sm">B</Pill>
          <FilterChip onRemove={() => {}}>Country: 🇻🇳 Vietnam</FilterChip>
          <FilterChip onRemove={() => {}}>Class 5 · Pharmaceuticals</FilterChip>
        </div>
      </Card>

      {/* Class chips */}
      <Card>
        <CardHead title="Class chips" sub="Goods (1–34) amber, services (35–45) blue. Matched = oxblood." />
        <div className="p-5 space-y-3">
          <div className="flex flex-wrap gap-1.5">
            {[1, 5, 10, 25, 29, 30, 32, 35, 36, 41, 42, 44].map((n) => <ClassChip key={n} n={n} />)}
            <ClassChip n={5} matched />
            <ClassChip n={35} matched />
            <ClassChip n={5} dim />
          </div>
          <div className="flex flex-wrap gap-2">
            <ClassChipFull n={5} />
            <ClassChipFull n={5} matched />
            <ClassChipFull n={35} />
            <ClassChipFull n={35} matched />
          </div>
        </div>
      </Card>

      {/* Indicators */}
      <Card>
        <CardHead title="Indicators" />
        <div className="p-5 flex flex-wrap items-center gap-6">
          <SimilarityRing score={0.94} />
          <SimilarityRing score={0.78} />
          <SimilarityRing score={0.62} />
          <SimilarityRing score={0.52} size={52} />
          <div className="w-64 space-y-2">
            <ProgressBar value={0.85} daysLeft={8} />
            <ProgressBar value={0.55} daysLeft={22} />
            <ProgressBar value={0.20} daysLeft={45} />
          </div>
          <span className="inline-flex items-center gap-1.5 text-ok"><PulseDot tone="ok" /> Live</span>
          <span className="inline-flex items-center gap-1.5 text-warn"><PulseDot tone="warn" /> Pending</span>
        </div>
      </Card>

      {/* Specimens */}
      <Card>
        <CardHead title="Mark specimens" sub="All 5 typographic styles + 2 monograms — used as fallback until raster images land." />
        <div className="p-5 grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
          {[
            { style: "wordmark-sans-bold" as const, text: "NEUROFAX", color: "ink" as const },
            { style: "wordmark-serif" as const, text: "NEURAXIS", color: "ink" as const },
            { style: "wordmark-italic-serif" as const, text: "MASAN", color: "stamp" as const },
            { style: "wordmark-rounded" as const, text: "NUROFEN+", color: "stamp" as const },
            { style: "wordmark-condensed" as const, text: "VINAMILK", color: "ok" as const },
            { style: "monogram-V" as const, text: "VINGROUP", color: "stamp" as const },
            { style: "monogram-circle" as const, text: "VX", color: "ink" as const },
            { style: "wordmark-sans-bold" as const, text: "SAMSUNG", color: "ink" as const },
          ].map((s) => (
            <div key={s.text + s.style}>
              <MarkSpecimen info={s} size="md" />
              <p className="mt-2 text-[11px] text-mute font-mono">{s.style}</p>
            </div>
          ))}
        </div>
      </Card>

      {/* Segmented + flags */}
      <Card>
        <CardHead
          title="Segmented control + flags"
          sub="Used for Grid/Table toggle and brand-theme switching."
          action={
            <SegmentedControl
              value={view}
              onChange={(v) => setView(v)}
              options={[
                { value: "grid", label: <Icon.Grid className="w-3.5 h-3.5" />, title: "Grid" },
                { value: "table", label: <Icon.Rows className="w-3.5 h-3.5" />, title: "Table" },
              ]}
            />
          }
        />
        <div className="p-5 flex items-center gap-3 text-sm">
          {["VN", "CN", "US", "KR", "JP", "SG", "GB", "DE", "FR", "IN"].map((c) => (
            <span key={c} className="inline-flex items-center gap-1 text-mute">
              <Flag code={c} size={16} />
              <span className="font-mono text-xs">{c}</span>
            </span>
          ))}
        </div>
      </Card>

      <Card>
        <CardHead title="Card with footer" sub="Cards have rounded-lg + line border. Footer uses paper-2." />
        <div className="p-5 text-sm text-ink-2">
          Card body content. Use the `Card`/`CardHead`/`CardFoot` family for all surface elements.
        </div>
        <CardFoot>
          <span>Footer text · {`<dim>`}</span>
          <LinkButton href="#">Action →</LinkButton>
        </CardFoot>
      </Card>
    </div>
  );
}
