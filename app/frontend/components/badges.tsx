"use client";

/** Visual tokens for record_type, status, Nice classes. Centralized so colors
 * stay consistent across the dashboard, search results, and detail page. */

export function RecordTypeBadge({ type }: { type: string }) {
  const styles: Record<string, string> = {
    A: "bg-sky-50 text-sky-700",
    B_domestic: "bg-violet-50 text-violet-700",
    B_madrid: "bg-rose-50 text-rose-700",
  };
  const labels: Record<string, string> = {
    A: "Application",
    B_domestic: "B Domestic",
    B_madrid: "B Madrid",
  };
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium ${styles[type] ?? "bg-slate-100 text-slate-700"}`}>
      {labels[type] ?? type}
    </span>
  );
}

export function GazetteTypeBadge({ type }: { type: "A" | "B" }) {
  return type === "A" ? (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-sky-50 text-sky-700">Applications (A)</span>
  ) : (
    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-violet-50 text-violet-700">Registrations (B)</span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const m: Record<string, { bg: string; fg: string; dot: string }> = {
    uploaded:   { bg: "bg-slate-50",   fg: "text-slate-700",   dot: "bg-slate-400" },
    processing: { bg: "bg-amber-50",   fg: "text-amber-700",   dot: "bg-amber-500 animate-pulse" },
    completed:  { bg: "bg-emerald-50", fg: "text-emerald-700", dot: "bg-emerald-500" },
    failed:     { bg: "bg-rose-50",    fg: "text-rose-700",    dot: "bg-rose-500" },
  };
  const s = m[status] ?? m.uploaded;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${s.bg} ${s.fg}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${s.dot}`} />
      {status[0].toUpperCase() + status.slice(1)}
    </span>
  );
}

export function NiceClassPill({ cls, label, primary }: { cls: string; label?: string; primary?: boolean }) {
  const padded = cls.padStart(2, "0");
  if (primary) {
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-amber-50 text-amber-800 border border-amber-100">
        <span className="font-mono">{padded}</span>
        {label && <span className="text-amber-900/80">{label}</span>}
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-xs font-mono ${cls === "0" ? "bg-slate-50 text-slate-400" : "bg-amber-50 text-amber-700"}`}>
      {padded}
    </span>
  );
}
