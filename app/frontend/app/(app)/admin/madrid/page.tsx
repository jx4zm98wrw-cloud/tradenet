"use client";

/** /admin/madrid — Madrid (WIPO) enrichment progress.
 *
 * Read-only ops view: how many unique Madrid IRNs the system holds, how many
 * have been validated against the WIPO endpoint, and how many remain. Every
 * number is derived from the DB at request time (no stored counter), so it
 * cannot drift. Admin-gated like /admin/gazettes: client-side redirect for
 * non-admins + backend require_admin on the endpoint (defense in depth). */

import * as React from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Pill } from "@/components/ui";
import { api, type MadridEnrichmentStats, type MadridSweepControl } from "@/lib/api";
import { errorMessage, formatNumber } from "@/lib/format";

export default function AdminMadridPage() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = React.useState<boolean | null>(null);
  const [stats, setStats] = React.useState<MadridEnrichmentStats | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Gate: redirect non-admins to Today.
  React.useEffect(() => {
    api.adminCheck()
      .then((c) => { if (!c.isAdmin) router.replace("/today"); else setIsAdmin(true); })
      .catch(() => setError("Admin check failed"));
  }, [router]);

  const refresh = React.useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      setStats(await api.adminMadridStats());
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  React.useEffect(() => { if (isAdmin) refresh(); }, [isAdmin, refresh]);

  // Light auto-poll while the sweep still has IRNs to fetch.
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
            <h1 className="head-serif text-[26px] font-semibold tracking-tight">Madrid enrichment</h1>
            <Pill tone="mute" size="sm">Admin</Pill>
          </div>
          <p className="text-sm text-mute mt-1 max-w-prose">
            WIPO validation coverage across all Madrid international registrations.
            Derived live from the database.
          </p>
        </div>
        <Button variant="ghost" onClick={() => refresh()} disabled={refreshing}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      <SweepControlCard />

      {/* Progress bar */}
      <Card>
        <div className="px-4 py-4">
          <div className="flex items-baseline justify-between mb-2">
            <span className="text-sm font-semibold">
              {formatNumber(stats.validated)} of {formatNumber(stats.unique_irns)} validated
            </span>
            <span className="text-sm font-mono text-mute">{pct}%</span>
          </div>
          <div className="h-2 bg-line rounded overflow-hidden">
            <div className="h-full bg-stamp transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="text-[11.5px] text-mute mt-2">
            {formatNumber(stats.remaining)} remaining{stats.remaining > 0 ? " · sweep in progress" : " · complete"}
          </p>
        </div>
      </Card>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
        <Stat label="Unique IRNs" value={stats.unique_irns} />
        <Stat label="Validated" value={stats.validated} />
        <Stat label="Remaining" value={stats.remaining} />
        <Stat label="VN granted" value={stats.vn_granted} />
        <Stat label="Registrations" value={stats.by_category["madrid_registration"] ?? 0} />
        <Stat label="Renewals" value={stats.by_category["madrid_renewal"] ?? 0} />
      </div>
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
  const [s, setS] = React.useState<MadridSweepControl | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<{ cap: string; delay: string; jitter: string; chunk_size: string }>({
    cap: "", delay: "", jitter: "", chunk_size: "",
  });

  const load = React.useCallback(async (silent = false) => {
    try {
      const next = await api.madridSweepStatus();
      setS(next);
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

  async function act(fn: () => Promise<MadridSweepControl>) {
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
          </div>
          <div className="flex items-center gap-2">
            <Button variant="primary" disabled={!can(["idle"])} onClick={() => act(() => api.madridSweepStart(cadence()))}>Start</Button>
            <Button variant="ghost" disabled={!can(["running"])} onClick={() => act(api.madridSweepPause)}>Pause</Button>
            <Button variant="ghost" disabled={!can(["paused"])} onClick={() => act(api.madridSweepResume)}>Resume</Button>
            <Button variant="ghost" disabled={!can(["running", "paused"])} onClick={() => act(api.madridSweepStop)}>Stop</Button>
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
          <Button variant="ghost" disabled={busy} onClick={() => act(() => api.madridSweepConfig(cadence()))}>Apply</Button>
        </div>

        <div className="text-[12px] text-mute">
          this run: <span className="font-mono text-ink">{formatNumber(s.processed)}</span> processed ·{" "}
          <span className="font-mono text-ok">{formatNumber(s.ok)}</span> ok ·{" "}
          <span className="font-mono text-rose-600">{formatNumber(s.failed)}</span> failed
          {s.current_irn ? <> · current <span className="font-mono text-ink">{s.current_irn}</span></> : null}
        </div>
        {s.last_error ? <div className="text-[12px] text-rose-600 truncate" title={s.last_error}>last error: {s.last_error}</div> : null}
        {err ? <div className="text-[12px] text-rose-600">{err}</div> : null}
      </div>
    </Card>
  );
}
