import { NICE_LABELS } from "@/lib/api";

/** Nice classification chip. Goods (1–34) shown amber, services (35–45) shown blue.
 * `matched` (oxblood) is used in Compare and Detail when the class belongs to the
 * anchor mark, signaling overlap. */
const SERVICES = new Set([35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45]);

type ChipProps = { n: number | string; matched?: boolean; dim?: boolean };

export function ClassChip({ n, matched = false, dim = false }: ChipProps) {
  const num = typeof n === "string" ? parseInt(n, 10) : n;
  const padded = String(num).padStart(2, "0");
  let cls: string;
  if (dim) cls = "bg-transparent text-fade border-line";
  else if (matched) cls = "bg-stamp-2 text-stamp border-stamp-line";
  else if (SERVICES.has(num))
    cls = "bg-[oklch(0.96_0.025_220)] text-[oklch(0.42_0.10_220)] border-[oklch(0.88_0.04_220)]";
  else
    cls = "bg-[oklch(0.97_0.02_95)] text-[oklch(0.45_0.09_80)] border-[oklch(0.88_0.04_90)]";
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-[1px] border rounded font-mono text-[11px] font-medium tabular leading-tight whitespace-nowrap ${cls}`}
    >
      <span className="font-bold">{padded}</span>
    </span>
  );
}

export function ClassChipFull({ n, matched = false }: ChipProps) {
  const num = typeof n === "string" ? parseInt(n, 10) : n;
  const padded = String(num).padStart(2, "0");
  const label = NICE_LABELS[padded] ?? "";
  const wrap = matched
    ? "bg-stamp-2 text-stamp border-stamp-line"
    : "bg-paper-2 text-ink-2 border-line";
  const inner = matched ? "text-stamp" : "text-ink-2";
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-1 border rounded text-xs ${wrap}`}>
      <span className="font-mono font-bold text-[11px] tabular">{padded}</span>
      <span className={inner}>{label}</span>
    </span>
  );
}
