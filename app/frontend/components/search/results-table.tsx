"use client";

import * as React from "react";
import Link from "next/link";
import { Icon } from "@/components/icons";
import { Pill, Flag, ClassChip, SimilarityRing } from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { markDisplay } from "@/lib/mark-display";
import { type ScoredMark } from "@/lib/api";
import { formatDate } from "@/lib/format";

type Props = {
  results: ScoredMark[];
  selected: Set<string>;
  onToggle: (id: string) => void;
  highlightClasses?: Set<string>;
};

export function ResultsTable({ results, selected, onToggle, highlightClasses = new Set() }: Props) {
  return (
    <div className="bg-surface border border-line rounded-lg overflow-hidden">
      <table className="w-full">
        <thead className="bg-paper-2 border-b border-line sticky top-14 z-20">
          <tr className="text-left text-[10.5px] font-semibold tracking-[0.08em] uppercase text-mute font-mono">
            <th className="px-3 py-2 w-8"></th>
            <th className="px-3 py-2 w-14">Sim</th>
            <th className="px-3 py-2 w-[110px]">Mark</th>
            <th className="px-3 py-2">Name / Applicant</th>
            <th className="px-3 py-2 w-16">Type</th>
            <th className="px-3 py-2 w-44">Classes</th>
            <th className="px-3 py-2 w-24">Country</th>
            <th className="px-3 py-2 w-28">Published</th>
            <th className="px-3 py-2 w-44">Agent</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line text-sm">
          {results.map(({ mark: m, score }) => {
            const isSel = selected.has(m.id);
            const md = markDisplay(m);
            return (
              <tr key={m.id} className={`${isSel ? "bg-stamp-2" : "hover:bg-paper-2"} cursor-pointer`}>
                <td className="px-3 py-2" onClick={(e) => { e.stopPropagation(); onToggle(m.id); }}>
                  <span
                    className={`w-4 h-4 rounded grid place-items-center border ${
                      isSel ? "bg-stamp text-white border-stamp-deep" : "bg-surface border-line"
                    }`}
                  >
                    {isSel && <Icon.Check className="w-2.5 h-2.5" />}
                  </span>
                </td>
                <td className="px-3 py-2">
                  <SimilarityRing score={score} size={28} />
                </td>
                <td className="px-3 py-2">
                  <Link href={`/marks/${m.id}`} className="block w-[90px]">
                    <MarkSpecimen
                      info={{ style: "wordmark-sans-bold", color: "ink", text: md.text, imageUrl: md.imageUrl }}
                      fallbackKey={m.id}
                      size="sm"
                      frame={false}
                      placeholder={md.isPlaceholder}
                    />
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <Link href={`/marks/${m.id}`} className="block">
                    <div className="font-medium text-[13px] truncate">{md.text}</div>
                    <div className="text-[11.5px] text-mute truncate">{m.applicant_name}</div>
                  </Link>
                </td>
                <td className="px-3 py-2">
                  <Pill tone={m.record_type === "A" ? "A" : "B"} size="sm">
                    {m.record_type === "A" ? "A" : "B"}
                  </Pill>
                </td>
                <td className="px-3 py-2">
                  <div className="flex flex-wrap gap-1">
                    {(m.nice_classes ?? []).slice(0, 6).map((c) => (
                      <ClassChip key={c} n={c} matched={highlightClasses.has(c)} />
                    ))}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1.5">
                    <Flag code={m.applicant_country_code ?? undefined} />
                    <span className="text-[11.5px] text-mute font-mono">{m.applicant_country_code ?? "—"}</span>
                  </div>
                </td>
                <td className="px-3 py-2 font-mono text-[11.5px] text-mute tabular">
                  {formatDate(m.publication_date_441 ?? m.publication_date_450)}
                </td>
                <td className="px-3 py-2 text-[11.5px] text-mute truncate max-w-[200px]" title={m.ip_agency ?? ""}>
                  {m.ip_agency ?? "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
