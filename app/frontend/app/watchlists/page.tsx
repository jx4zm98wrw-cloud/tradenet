"use client";

/** /watchlists — grid of saved-query cards.
 * Each card shows newCount, query summary, recent findings, totalCount + lastRun.
 * "+ New watchlist" placeholder opens a creation modal. */

import Link from "next/link";
import * as React from "react";
import { useRouter } from "next/navigation";
import { Card, Button, LinkButton, Pill, SimilarityRing, ClassChip } from "@/components/ui";
import { MarkSpecimen } from "@/components/specimen";
import { markDisplay } from "@/lib/mark-display";
import { Icon } from "@/components/icons";
import { api, type Trademark, type Watchlist, type WatchQuery } from "@/lib/api";
import { formatNumber, relativeTime } from "@/lib/format";

export default function WatchlistsPage() {
  const router = useRouter();
  const [items, setItems] = React.useState<Watchlist[] | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [creating, setCreating] = React.useState(false);
  const [findings, setFindings] = React.useState<Record<string, Trademark[]>>({});

  const refresh = React.useCallback(async () => {
    try {
      const list = await api.watchlists();
      setItems(list);
      // Eagerly fetch top findings per list — small N so this is fine.
      const map: Record<string, Trademark[]> = {};
      await Promise.all(list.map(async (w) => {
        try {
          map[w.id] = await api.watchlistFindings(w.id, 3);
        } catch { map[w.id] = []; }
      }));
      setFindings(map);
    } catch (e: any) {
      setError(e.message ?? String(e));
    }
  }, []);

  React.useEffect(() => { refresh(); }, [refresh]);

  async function onDelete(w: Watchlist) {
    if (!confirm(`Delete watchlist "${w.name}"?`)) return;
    await api.deleteWatchlist(w.id);
    refresh();
  }

  if (error) {
    return <div className="max-w-container mx-auto px-6 py-12"><p className="text-rose-600">{error}</p></div>;
  }

  return (
    <div className="max-w-container mx-auto px-6 py-6 space-y-5">
      <div className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <h1 className="head-serif text-[26px] font-semibold tracking-tight">Watchlists</h1>
          <p className="text-sm text-mute mt-1 max-w-prose">
            Standing queries re-run automatically against every new gazette issue. Findings surface on your dashboard.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost">Import from CSV</Button>
          <Button variant="primary" onClick={() => setCreating(true)}>+ New watchlist</Button>
        </div>
      </div>

      {items === null ? (
        <SkeletonGrid />
      ) : (
        <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))" }}>
          {items.map((w) => (
            <WatchCard key={w.id} w={w} findings={findings[w.id] ?? []} onDelete={() => onDelete(w)} />
          ))}
          <AddCard onClick={() => setCreating(true)} />
        </div>
      )}

      {creating && (
        <CreateModal
          onClose={() => setCreating(false)}
          onCreated={(w) => {
            setCreating(false);
            setItems((prev) => prev ? [w, ...prev] : [w]);
            api.watchlistFindings(w.id, 3).then((f) => setFindings((m) => ({ ...m, [w.id]: f }))).catch(() => {});
          }}
        />
      )}
    </div>
  );
}

/* =========================================================================== */

function WatchCard({ w, findings, onDelete }: { w: Watchlist; findings: Trademark[]; onDelete: () => void }) {
  return (
    <Card className="flex flex-col">
      <header className="px-5 py-4 flex items-start justify-between gap-3 border-b border-line">
        <div className="min-w-0">
          <h3 className="head-serif text-[16px] font-semibold tracking-tight truncate">{w.name}</h3>
          <p className="text-[12.5px] text-mute mt-0.5 truncate">
            {w.client ?? <span className="italic">No client</span>}
            <span className="text-fade mx-1">·</span>
            <span className="font-mono">{w.matter ?? "—"}</span>
          </p>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[24px] font-bold leading-none tabular ${w.newCount > 0 ? "text-stamp" : "text-mute"}`}>
            {w.newCount > 0 ? `+${formatNumber(w.newCount)}` : "0"}
          </div>
          <div className="text-[10.5px] font-mono uppercase tracking-wider text-mute mt-1">new this period</div>
        </div>
      </header>

      <div className="px-5 py-3 border-b border-line">
        <p className="text-[10.5px] font-mono uppercase tracking-wider text-mute">Query</p>
        <p className="font-mono text-[12.5px] text-ink-2 mt-1 break-words">{w.queryDesc || queryToText(w.query)}</p>
      </div>

      <div className="flex-1 min-h-[60px]">
        {findings.length === 0 ? (
          <p className="text-[12.5px] text-mute text-center py-6 px-4">No findings yet.</p>
        ) : (
          <ul className="divide-y divide-line">
            {findings.map((t) => {
              const md = markDisplay(t);
              return (
                <li key={t.id}>
                  <Link href={`/marks/${t.id}`} className="flex items-center gap-3 px-5 py-2.5 hover:bg-paper-2">
                    <div className="w-14 shrink-0">
                      <MarkSpecimen
                        info={{ style: "wordmark-sans-bold", color: "ink", text: md.text, imageUrl: md.imageUrl }}
                        fallbackKey={t.id}
                        size="sm"
                        placeholder={md.isPlaceholder}
                      />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-semibold truncate">{md.text}</div>
                      <div className="text-[11px] text-mute truncate">{t.applicant_name}</div>
                    </div>
                    <div className="flex flex-wrap gap-1 shrink-0">
                      {(t.nice_classes ?? []).slice(0, 3).map((c) => <ClassChip key={c} n={c} />)}
                    </div>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <footer className="px-5 py-2.5 border-t border-line flex items-center justify-between bg-paper-2 text-[11.5px]">
        <span className="text-mute">
          {formatNumber(w.totalCount)} total{w.lastRunAt ? ` · last run ${relativeTime(w.lastRunAt)}` : ""}
        </span>
        <div className="flex items-center gap-3">
          <button onClick={onDelete} className="text-mute hover:text-rose-600">Delete</button>
          <LinkButton href={`/search?q=${encodeURIComponent(w.query.q ?? "")}`}>Edit query</LinkButton>
        </div>
      </footer>
    </Card>
  );
}

function AddCard({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="border-2 border-dashed border-line rounded-lg p-6 flex flex-col items-center justify-center gap-2 text-mute hover:border-stamp-line hover:bg-stamp-2 hover:text-stamp transition min-h-[260px]"
    >
      <Icon.Plus className="w-6 h-6" />
      <span className="text-sm font-semibold">New watchlist</span>
      <span className="text-[11.5px] max-w-[24ch] text-center">
        From a saved search, an uploaded image, or an existing mark
      </span>
    </button>
  );
}

/* =========================================================================== */

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: (w: Watchlist) => void }) {
  const [name, setName] = React.useState("");
  const [client, setClient] = React.useState("");
  const [matter, setMatter] = React.useState("");
  const [q, setQ] = React.useState("");
  const [country, setCountry] = React.useState("");
  const [classes, setClasses] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return setErr("Name is required");
    setBusy(true);
    setErr(null);
    try {
      const query: WatchQuery = {
        q: q.trim() || undefined,
        country: country.trim().toUpperCase() || undefined,
        nice_class: classes
          ? classes.split(/[\s,]+/).map((c) => c.padStart(2, "0")).filter(Boolean)
          : undefined,
        nice_class_mode: "any",
      };
      const created = await api.createWatchlist({
        name: name.trim(),
        client: client.trim() || undefined,
        matter: matter.trim() || undefined,
        query,
      });
      onCreated(created);
    } catch (e: any) {
      setErr(e.message ?? String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 bg-ink/40 backdrop-blur-sm grid"
      style={{ alignItems: "flex-start", justifyItems: "center", paddingTop: "10vh" }}
    >
      <form
        onSubmit={submit}
        onClick={(e) => e.stopPropagation()}
        className="bg-surface border border-line rounded-lg shadow-md w-[520px] max-w-[92vw] overflow-hidden"
      >
        <header className="px-5 py-4 border-b border-line flex items-center justify-between">
          <h2 className="head-serif text-[16px] font-semibold tracking-tight">New watchlist</h2>
          <button type="button" onClick={onClose} className="w-7 h-7 grid place-items-center rounded hover:bg-paper-2">
            <Icon.X className="w-4 h-4 text-mute" />
          </button>
        </header>
        <div className="px-5 py-4 space-y-3">
          <Field label="Name" required>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
              required
              maxLength={256}
              className="w-full text-sm px-2.5 h-9 border border-line rounded bg-surface"
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Client"><input value={client} onChange={(e) => setClient(e.target.value)} className="w-full text-sm px-2.5 h-9 border border-line rounded bg-surface" /></Field>
            <Field label="Matter ID"><input value={matter} onChange={(e) => setMatter(e.target.value)} placeholder="CR-2024-118" className="w-full text-sm px-2.5 h-9 border border-line rounded bg-surface font-mono" /></Field>
          </div>
          <hr className="border-line" />
          <p className="text-[11.5px] text-mute">
            <strong className="text-ink-2">Saved query</strong> · the watchlist re-runs this against every new gazette.
          </p>
          <Field label="Text to match (optional)">
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder='e.g. "neur" or "vex*"' className="w-full text-sm px-2.5 h-9 border border-line rounded bg-surface" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Country (ISO-2)">
              <input value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())} maxLength={2} placeholder="VN" className="w-full text-sm px-2.5 h-9 border border-line rounded bg-surface uppercase" />
            </Field>
            <Field label="Nice classes (comma-sep)">
              <input value={classes} onChange={(e) => setClasses(e.target.value)} placeholder="05, 10, 35" className="w-full text-sm px-2.5 h-9 border border-line rounded bg-surface" />
            </Field>
          </div>
          {err && <p className="text-rose-600 text-xs">{err}</p>}
        </div>
        <footer className="px-5 py-3 border-t border-line flex items-center justify-end gap-2 bg-paper-2">
          <Button variant="ghost" type="button" onClick={onClose}>Cancel</Button>
          <Button variant="primary" type="submit" disabled={busy}>
            {busy ? "Saving…" : "Create watchlist"}
          </Button>
        </footer>
      </form>
    </div>
  );
}

function Field({ label, required, children }: { label: string; required?: boolean; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="text-[10.5px] font-mono uppercase tracking-[0.06em] text-mute">
        {label}{required && " *"}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

function queryToText(q: WatchQuery): string {
  const parts: string[] = [];
  if (q.q) parts.push(`"${q.q}"`);
  if (q.country) parts.push(`Country ${q.country}`);
  if (q.nice_class?.length) parts.push(`Classes ${q.nice_class.join(",")} (${q.nice_class_mode ?? "any"})`);
  if (q.applicant_type) parts.push(q.applicant_type);
  if (q.record_type) parts.push(q.record_type);
  return parts.join(" · ") || "All marks";
}

function SkeletonGrid() {
  return (
    <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(360px, 1fr))" }}>
      {[...Array(4)].map((_, i) => (
        <div key={i} className="h-64 bg-paper-2 rounded-lg animate-pulse" />
      ))}
    </div>
  );
}
