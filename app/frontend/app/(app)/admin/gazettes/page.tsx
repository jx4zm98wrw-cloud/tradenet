"use client";

/** /admin/gazettes — admin-only pipeline view.
 *
 * Daily users live on Today. This view is for monitoring ingest health: per-issue
 * status, OCR confidence, flagged rows needing manual review, and the
 * upload-new-gazette dropzone. Client-side gate: /api/admin/check returns
 * isAdmin=false for non-admin roles → we redirect to "/". Backend defense-
 * in-depth: GET /api/v1/gazettes itself is `require_admin`, so a viewer
 * who bypasses the redirect still gets 403s. */

import * as React from "react";
import { useRouter } from "next/navigation";
import { Card, Button, Pill } from "@/components/ui";
import { Icon } from "@/components/icons";
import { GazettesDashboard } from "@/components/admin/gazettes-dashboard";
import { GazettesByYear } from "@/components/admin/gazettes-by-year";
import { api, type Gazette } from "@/lib/api";
import { errorMessage, formatNumber } from "@/lib/format";

export default function AdminGazettesPage() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = React.useState<boolean | null>(null);
  const [items, setItems] = React.useState<Gazette[] | null>(null);
  const [refreshing, setRefreshing] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [uploading, setUploading] = React.useState<{ name: string; progress: number }[]>([]);
  // Bumped after an upload so <GazettesByYear> reloads its accordion headers
  // (and any expanded year) to surface the freshly-ingested issue.
  const [refreshKey, setRefreshKey] = React.useState(0);
  const fileRef = React.useRef<HTMLInputElement>(null);

  // Gate: redirect non-admins to Today.
  React.useEffect(() => {
    api.adminCheck()
      .then((c) => {
        // `/` is the public marketing landing; in-app home moved to `/today`.
        if (!c.isAdmin) router.replace("/today");
        else setIsAdmin(true);
      })
      .catch(() => setError("Admin check failed"));
  }, [router]);

  const refresh = React.useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const r = await api.listGazettes();
      setItems(r.items);
      setError(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      if (!silent) setRefreshing(false);
    }
  }, []);

  const reloadAll = React.useCallback(async () => {
    await refresh();
    setRefreshKey((k) => k + 1);
  }, [refresh]);

  React.useEffect(() => { if (isAdmin) refresh(); }, [isAdmin, refresh]);

  // Light polling — only when there's a non-terminal row to watch.
  React.useEffect(() => {
    if (!items?.some((g) => g.status === "uploaded" || g.status === "processing")) return;
    const id = setInterval(() => refresh(true), 5000);
    return () => clearInterval(id);
  }, [items, refresh]);

  async function uploadFiles(files: FileList | File[]) {
    const list = Array.from(files);
    setUploading(list.map((f) => ({ name: f.name, progress: 0 })));
    for (const file of list) {
      try {
        await api.uploadGazette(file);
        setUploading((prev) => prev.map((u) => (u.name === file.name ? { ...u, progress: 100 } : u)));
      } catch (e) {
        setError(`${file.name}: ${errorMessage(e)}`);
      }
    }
    await reloadAll();
    setUploading([]);
  }

  function onDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const pdfs = Array.from(e.dataTransfer.files).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (pdfs.length > 0) uploadFiles(pdfs);
  }

  if (error && !items) {
    return <div className="max-w-container mx-auto px-6 py-12"><p className="text-rose-600">{error}</p></div>;
  }
  if (isAdmin === null) {
    return <div className="max-w-container mx-auto px-6 py-12 text-mute text-sm">Checking access…</div>;
  }

  const totalRows = items?.reduce((s, g) => s + g.row_count, 0) ?? 0;
  const inFlight = items?.filter((g) => g.status === "uploaded" || g.status === "processing").length ?? 0;
  const flagged = items?.filter((g) => g.needs_review).length ?? 0;

  return (
    <div className="max-w-container mx-auto px-6 py-6 space-y-5">
      <div className="flex items-baseline justify-between flex-wrap gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="head-serif text-[26px] font-semibold tracking-tight">Gazettes</h1>
            <Pill tone="mute" size="sm">Admin</Pill>
          </div>
          <p className="text-sm text-mute mt-1 max-w-prose">
            {items
              ? `${items.length} issue${items.length === 1 ? "" : "s"} · ${formatNumber(totalRows)} trademarks total ${
                  inFlight
                    ? `· ${inFlight} processing`
                    : flagged > 0
                    ? `· ${flagged} need review`
                    : "· pipeline healthy"
                }. Daily users live on Today.`
              : "Loading…"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => reloadAll()} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh"}
          </Button>
          <Button variant="primary" onClick={() => fileRef.current?.click()}>
            <Icon.Upload className="w-4 h-4" />
            Upload gazette
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            className="hidden"
            onChange={(e) => e.target.files && uploadFiles(e.target.files)}
          />
        </div>
      </div>

      {error && <p className="text-sm text-rose-600">{error}</p>}

      {/* Drop zone */}
      <div
        onDragOver={(e) => e.preventDefault()}
        onDrop={onDrop}
        onClick={() => fileRef.current?.click()}
        className="border-2 border-dashed border-line rounded-lg p-6 bg-paper text-center hover:border-stamp-line hover:bg-stamp-2/40 transition cursor-pointer"
      >
        <Icon.Upload className="w-7 h-7 text-mute mx-auto" />
        <p className="text-sm font-medium mt-2">
          Drop PDFs here, or <span className="text-stamp">click to browse</span>
        </p>
        <p className="text-[11.5px] text-mute mt-1">
          Multiple files OK · A_T*_YYYY.pdf or B_T*_YYYY.pdf · max 500MB each
        </p>
      </div>

      {uploading.length > 0 && (
        <Card>
          <div className="px-4 py-3">
            <p className="text-sm font-semibold mb-2">Uploading {uploading.length} file{uploading.length === 1 ? "" : "s"}…</p>
            <ul className="space-y-2 text-sm">
              {uploading.map((u) => (
                <li key={u.name} className="flex items-center gap-3">
                  <span className="flex-1 truncate font-mono text-[12.5px]">{u.name}</span>
                  <span className="text-[11px] text-mute">{u.progress < 100 ? "uploading…" : "queued for ingest"}</span>
                  <div className="w-32 h-1.5 bg-line rounded overflow-hidden">
                    <div
                      className={`h-full transition-all ${u.progress === 100 ? "bg-ok" : "bg-stamp"}`}
                      style={{ width: `${u.progress}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </Card>
      )}

      {/* Overview dashboard (PR 2) — sits between the upload area and the
          group-by-year list. */}
      <GazettesDashboard />

      {/* Group-by-year list (PR 3) — collapsible year accordion with lazy
          per-year fetch + filter bar, replacing the old flat 50-row table. */}
      <GazettesByYear refreshKey={refreshKey} />
    </div>
  );
}
