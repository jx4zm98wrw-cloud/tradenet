"use client";

/** /admin/domestic — Domestic (IP VIETNAM) enrichment progress.
 *
 * Read-only ops view: how many unique domestic application numbers the system
 * holds, how many have been validated against the IP VIETNAM endpoint, and how many
 * remain. Every number is derived from the DB at request time (no stored
 * counter), so it cannot drift. Admin-gated like /admin/gazettes: client-side
 * redirect for non-admins + backend require_admin on the endpoint (defense in
 * depth). */

import * as React from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Pill } from "@/components/ui";
import { api, type DomesticEnrichmentStats, type DomesticSweepControl } from "@/lib/api";
import { errorMessage, formatNumber } from "@/lib/format";

export default function AdminDomesticPage() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = React.useState<boolean | null>(null);
  const [stats, setStats] = React.useState<DomesticEnrichmentStats | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [rechecking, setRechecking] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);

  // Gate: redirect non-admins to Today.
  React.useEffect(() => {
    api.adminCheck()
      .then((c) => { if (!c.isAdmin) router.replace("/today"); else setIsAdmin(true); })
      .catch(() => setError("Admin check failed"));
  }, [router]);

  const refresh = React.useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      setStats(await api.adminDomesticStats());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  React.useEffect(() => { if (isAdmin) refresh(); }, [isAdmin, refresh]);

  // Light auto-poll while the sweep still has application numbers to fetch.
  React.useEffect(() => {
    if (!stats || stats.remaining <= 0) return;
    const id = setInterval(() => refresh(true), 5000);
    return () => clearInterval(id);
  }, [stats, refresh]);

  if (error && !stats) {
    return <div className="max-w-container mx-auto px-6 py-12"><p className="text-rose-600">{error}</p></div>;
  }
  if (isAdmin === null || !stats) {
    return <div className="max-w-container mx-auto px-6 py-12 text-mute text-sm">Loading…</div>;
  }

  const pct = Math.round(stats.pct_complete * 1000) / 10; // one decimal place

  return (
    <div className="max-w-container mx-auto px-6 py-6 space-y-5">
      <div className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="head-serif text-[26px] font-semibold tracking-tight">Domestic enrichment</h1>
            <Pill tone="mute" size="sm">Admin</Pill>
          </div>
          <p className="text-sm text-mute mt-1 max-w-prose">
            IP VIETNAM validation coverage across all domestic trademark applications and registrations.
            Derived live from the database.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            disabled={rechecking || stats.pending_publication === 0}
            onClick={async () => {
              if (!confirm(`Re-check ${formatNumber(stats.pending_publication)} pending mark(s) against IP VIETNAM now?`)) return;
              setRechecking(true);
              setError(null);
              setNotice(null);
              try {
                const { reset } = await api.domesticSweepRecheckPending();
                setNotice(`Re-queued ${formatNumber(reset)} mark(s) for re-check.`);
                await refresh();
              } catch (e) {
                setError(errorMessage(e));
              } finally {
                setRechecking(false);
              }
            }}
          >
            {rechecking ? "Re-checking…" : `Re-check pending (${formatNumber(stats.pending_publication)})`}
          </Button>
          <Button variant="ghost" onClick={() => refresh()} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
        </div>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}
      {notice && <p className="text-sm text-mute">{notice}</p>}

      <SweepControlCard />

      {/* Progress bar */}
      <Card>
        <div className="px-4 py-4">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-sm font-semibold">
              {formatNumber(stats.validated)} of {formatNumber(stats.unique_appnos)} validated
            </span>
            <span className="text-sm font-mono text-mute">{pct}%</span>
          </div>
          <div className="h-2 bg-line rounded overflow-hidden">
            <div className="h-full bg-stamp transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-[11.5px] text-mute mt-2">
            {formatNumber(stats.remaining)} remaining
            {stats.remaining > 0 ? (
              <>
                {" "}· <span className="text-ink">{formatNumber(stats.unresolved)}</span> still to fetch
                {" "}· <span className="text-ink">{formatNumber(stats.pending_publication)}</span> awaiting IP VIETNAM publication
              </>
            ) : " · complete"}
          </p>
        </div>
      </Card>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat label="Unique app nos" value={stats.unique_appnos} />
        <Stat label="Validated" value={stats.validated} />
        <Stat label="Unresolved" value={stats.unresolved} />
        <Stat label="Malformed" value={stats.malformed} />
        <Stat label="Pending publication" value={stats.pending_publication} />
        <Stat label="Granted" value={stats.granted} />
        <Stat label="Registrations" value={stats.by_category["domestic_registration"] ?? 0} />
        <Stat label="Applications" value={stats.by_category["domestic_application"] ?? 0} />
      </div>

      {stats.malformed_appnos.length > 0 && (
        <Card>
          <div className="px-4 py-4">
            <div className="text-sm font-semibold">Malformed application numbers — needs review</div>
            <p className="text-[11.5px] text-mute mt-1 mb-3 max-w-prose">
              These can’t be mapped to an IP VIETNAM id (e.g. a truncated number), so the sweep skips them. Fix{" "}
              <span className="font-mono text-ink">trademarks.application_number</span>, then they enrich automatically.
            </p>
            <ul className="space-y-1 text-[13px]">
              {stats.malformed_appnos.map((m) => (
                <li key={m.application_number} className="flex gap-3 min-w-0">
                  <span className="font-mono text-ink shrink-0">{m.application_number}</span>
                  <span className="text-mute truncate">{m.applicant_name ?? "—"}</span>
                  <span className="text-mute font-mono truncate">{m.gazette ?? "—"}</span>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <div className="px-4 py-3">
        <div className="text-[11px] uppercase tracking-[0.08em] text-mute font-mono">{label}</div>
        <div className="text-2xl font-semibold tabular mt-1">{formatNumber(value)}</div>
      </div>
    </Card>
  );
}

function SweepControlCard() {
  const [s, setS] = React.useState<DomesticSweepControl | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [rps, setRps] = React.useState<number | null>(null);
  const sample = React.useRef<{ processed: number; t: number } | null>(null);
  const [form, setForm] = React.useState<{ cap: string; delay: string; jitter: string; chunk_size: string }>({
    cap: "", delay: "", jitter: "", chunk_size: "",
  });

  const load = React.useCallback(async (silent = false) => {
    try {
      const next = await api.domesticSweepStatus();
      setS(next);
      const t = Date.now();
      if (sample.current && next.processed >= sample.current.processed) {
        const dp = next.processed - sample.current.processed;
        const dt = (t - sample.current.t) / 1000;
        if (dt > 0) setRps(dp / dt);
      } else {
        setRps(null); // counter reset (new run) — drop the stale rate
      }
      sample.current = { processed: next.processed, t };
      setErr(null);
      if (!silent) {
        setForm({
          cap: next.cap?.toString() ?? "",
          delay: next.delay.toString(),
          jitter: next.jitter.toString(),
          chunk_size: next.chunk_size.toString(),
        });
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load sweep status");
    }
  }, []);

  React.useEffect(() => { load(); }, [load]);
  React.useEffect(() => {
    const id = setInterval(() => load(true), 3000);
    return () => clearInterval(id);
  }, [load]);

  async function act(fn: () => Promise<DomesticSweepControl>) {
    setBusy(true);
    setErr(null);
    try {
      setS(await fn());
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  }

  const cadence = () => ({
    cap: form.cap.trim() === "" ? null : Number(form.cap),
    delay: Number(form.delay),
    jitter: Number(form.jitter),
    chunk_size: Number(form.chunk_size),
  });

  if (!s) return null;
  const tone = s.status === "running" ? "ok" : s.status === "paused" ? "warn" : "mute";
  const can = (st: string[]) => st.includes(s.status) && !busy;

  return (
    <Card>
      <div className="px-4 py-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold">Sweep control</span>
            <Pill tone={tone as "ok" | "warn" | "mute"} size="sm">{s.status}</Pill>
            {s.mode === "dead" ? <Pill tone="warn" size="sm">Dead mode</Pill> : null}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="primary" disabled={!can(["idle"])} onClick={() => act(() => api.domesticSweepStart(cadence()))}>Start</Button>
            <Button variant="ghost" disabled={!can(["running"])} onClick={() => act(api.domesticSweepPause)}>Pause</Button>
            <Button variant="ghost" disabled={!can(["paused"])} onClick={() => act(api.domesticSweepResume)}>Resume</Button>
            <Button variant="ghost" disabled={!can(["running", "paused"])} onClick={() => act(api.domesticSweepStop)}>Stop</Button>
          </div>
        </div>

        <div className="flex items-end gap-2 flex-wrap">
          {(["cap", "delay", "jitter", "chunk_size"] as const).map((k) => (
            <label key={k} className="text-[11px] text-mute font-mono">
              <div className="uppercase tracking-[0.08em]">{k}</div>
              <input
                className="mt-1 w-20 rounded border border-line bg-paper px-2 py-1 text-[13px] text-ink"
                value={form[k]}
                onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))}
              />
            </label>
          ))}
          <Button variant="ghost" disabled={busy} onClick={() => act(() => api.domesticSweepConfig(cadence()))}>Apply</Button>
        </div>

        <div className="flex items-center justify-between gap-2 flex-wrap border-t border-line pt-3">
          <div className="text-[11px] text-mute max-w-prose">
            <span className="font-semibold text-ink">Dead mode</span> — max-throughput adaptive concurrency on
            the single clean IP; auto-throttles and auto-reverts to normal + pauses on sustained IP VIETNAM blocks.
          </div>
          <Button
            variant={s.mode === "dead" ? "primary" : "ghost"}
            disabled={busy}
            onClick={() => act(() => api.domesticSweepConfig({ mode: s.mode === "dead" ? "normal" : "dead" }))}
          >
            {s.mode === "dead" ? "Disable dead mode" : "Enable dead mode"}
          </Button>
        </div>

        <div className="text-[12px] text-mute">
          rate: <span className="font-mono text-ink">{s.processed > 0 ? `${Math.round((s.ok / s.processed) * 100)}%` : "—"}</span>
          {s.mode === "dead" ? <> · concurrency <span className="font-mono text-ink">{s.concurrency}</span></> : null}
          {rps !== null ? <> · <span className="font-mono text-ink">{rps.toFixed(1)}</span> req/s</> : null}
        </div>

        <div className="text-[12px] text-mute">
          this run: <span className="font-mono text-ink">{formatNumber(s.processed)}</span> processed ·{" "}
          <span className="font-mono text-ok">{formatNumber(s.ok)}</span> ok ·{" "}
          <span className="font-mono text-ink">{formatNumber(s.not_found)}</span> not&nbsp;found ·{" "}
          <span className="font-mono text-rose-600">{formatNumber(s.failed)}</span> failed
          {s.current_appno ? <> · current <span className="font-mono text-ink">{s.current_appno}</span></> : null}
          {s.next_appno ? <> · next <span className="font-mono text-ink">{s.next_appno}</span></> : null}
        </div>
        {s.last_error ? <div className="text-[12px] text-rose-600 truncate" title={s.last_error}>last error: {s.last_error}</div> : null}
        {err ? <div className="text-[12px] text-rose-600">{err}</div> : null}
      </div>
    </Card>
  );
}
