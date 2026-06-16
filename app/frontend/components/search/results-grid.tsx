"use client";

import * as React from "react";
import Link from "next/link";
import { Icon } from "@/components/icons";
import { Pill, Flag, ClassChip, SimilarityRing } from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { markDisplay } from "@/lib/mark-display";
import { countryDisplay, type ScoredMark } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Props = {
  results: ScoredMark[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  highlightClasses?: Set<string>;
};

export function ResultsGrid({ results, selected, onToggle, highlightClasses = new Set() }: Props) {
  return (
    <div
      className="grid gap-4 grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5"
    >
      {results.map(({ mark: m, score }) => {
        const isSel = selected.has(m.id);
        const d = countryDisplay(m.applicant_country_code);
        const md = markDisplay(m);
        return (
          <article
            key={m.id}
            className={`bg-surface border rounded-lg overflow-hidden flex flex-col transition ${
              isSel ? "border-stamp ring-2 ring-stamp-2" : "border-line hover:border-line-strong hover:shadow-md"
            }`}
          >
            <div className="relative">
              <button
                type="button"
                onClick={() => onToggle(m.id)}
                aria-label="Select"
                className={`absolute top-2 left-2 z-10 w-5 h-5 rounded grid place-items-center border ${
                  isSel ? "bg-stamp text-white border-stamp-deep" : "bg-surface/85 border-line hover:border-line-strong"
                }`}
              >
                {isSel && <Icon.Check className="w-3 h-3" />}
              </button>
              <div className="absolute top-2 right-2 z-10 bg-surface/85 rounded-full backdrop-blur-sm">
                <SimilarityRing score={score} size={34} />
              </div>
              <Link href={`/marks/${m.id}`} className="block border-b border-line">
                <MarkSpecimen
                  info={{ style: "wordmark-sans-bold", color: "ink", text: md.text, imageUrl: md.imageUrl }}
                  fallbackKey={m.id}
                  size="md"
                  placeholder={md.isPlaceholder}
                  className="!rounded-none !border-0"
                />
              </Link>
            </div>
            <div className="p-3 flex-1 flex flex-col gap-1.5">
              <Link href={`/marks/${m.id}`} className="block">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="font-semibold text-[13.5px] truncate">{md.text}</span>
                  <Pill tone={m.record_type === "A" ? "A" : "B"} size="sm">
                    {m.record_type === "A" ? "A" : "B"}
                  </Pill>
                </div>
                <div className="text-xs text-ink-2 truncate mt-0.5">{m.applicant_name}</div>
              </Link>
              <div className="text-[11.5px] text-mute flex items-center gap-1.5 flex-wrap mt-auto">
                <Flag code={m.applicant_country_code ?? undefined} size={12} />
                <span className="font-mono">{m.application_number ?? m.certificate_number ?? m.madrid_number ?? "—"}</span>
                <span className="text-fade">·</span>
                <span>{formatDate(m.publication_date_441 ?? m.publication_date_450)}</span>
              </div>
              <div className="flex flex-wrap gap-1">
                {(m.nice_classes ?? []).slice(0, 5).map((c) => (
                  <ClassChip key={c} n={c} matched={highlightClasses.has(c)} />
                ))}
                {m.nice_classes && m.nice_classes.length > 5 && (
                  <span className="text-[11px] text-mute">+{m.nice_classes.length - 5}</span>
                )}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
