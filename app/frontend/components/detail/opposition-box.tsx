"use client";

import { Button } from "@/components/ui";
import { type MarkDetail } from "@/lib/api";

const fmtShort = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) : "—";

export function OppositionBox({ detail }: { detail: MarkDetail }) {
  const opp = detail.oppositionDaysLeft;
  if (opp == null || !detail.oppositionOpen) return null;
  const urgent = opp <= 14;
  const elapsedPct = Math.max(2, Math.min(100, ((150 - opp) / 150) * 100));

  return (
    <div className={`mt-4 rounded-lg border p-4 ${urgent ? "bg-stamp-2 border-stamp-line" : "bg-paper-2 border-line"}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[10.5px] font-semibold tracking-[0.08em] uppercase text-mute font-mono">
            Opposition window — open
          </p>
          <p className="mt-1.5 flex items-baseline gap-2">
            <span className={`text-[32px] leading-none font-bold tabular ${urgent ? "text-stamp" : "text-ink"}`}>
              {opp}
            </span>
            <span className="text-sm text-mute">days remaining</span>
          </p>
        </div>
        <Button variant="primary" size="sm">File opposition</Button>
      </div>
      <div className="relative mt-4 h-1.5 bg-line rounded overflow-hidden">
        <div
          className={`absolute inset-y-0 left-0 ${urgent ? "bg-stamp" : "bg-ok"}`}
          style={{ width: `${elapsedPct}%` }}
        />
      </div>
      <div className="mt-1.5 flex items-start justify-between text-[10.5px] font-mono text-mute">
        <span>Published<br />{fmtShort(detail.mark.publication_date_441 ?? detail.mark.publication_date_450)}</span>
        <span className="text-right">Window closes<br />{fmtShort(detail.oppositionEnds)}</span>
      </div>
      <p className="mt-3 text-[11px] text-mute leading-relaxed">
        Under Vietnam Article 112: opposition window = 5 months from publication date. After this date, only invalidation proceedings remain.
      </p>
    </div>
  );
}
