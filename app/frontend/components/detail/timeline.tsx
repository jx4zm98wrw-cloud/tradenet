"use client";

import * as React from "react";
import { Icon } from "@/components/icons";
import { type TimelineEvent } from "@/lib/api";

const fmt = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });

export function Timeline({ events }: { events: TimelineEvent[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-mute px-5 py-4">No procedural dates available for this mark.</p>;
  }
  return (
    <ol className="px-5 py-3 space-y-3">
      {events.map((e, i) => {
        const last = i === events.length - 1;
        const dotClasses = e.done
          ? "bg-ok text-white"
          : e.current
          ? "bg-stamp text-white"
          : "bg-paper-2 text-mute border border-line";
        return (
          <li key={i} className="grid gap-3" style={{ gridTemplateColumns: "20px 1fr" }}>
            <div className="relative flex flex-col items-center">
              <div className={`w-5 h-5 rounded-full grid place-items-center text-[10px] font-bold shrink-0 ${dotClasses}`}>
                {e.done ? <Icon.Check className="w-2.5 h-2.5" /> : e.current ? "!" : ""}
              </div>
              {!last && <div className="absolute top-5 bottom-[-12px] w-px bg-line" />}
            </div>
            <div className="pb-2">
              <div className="flex items-baseline justify-between gap-3">
                <span className={`text-[13.5px] font-semibold ${e.current ? "text-stamp" : "text-ink"}`}>{e.label}</span>
                <span className="text-[12px] text-mute font-mono tabular shrink-0">{fmt(e.date)}</span>
              </div>
              <p className="text-xs text-mute mt-0.5">{e.body}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
