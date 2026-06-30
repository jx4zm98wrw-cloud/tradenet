"""Census runner — exercise EVERY mark (~238,149), not a sample.

Streams the gold set straight from Postgres in ``application_number`` order via a
stable **keyset** cursor (resumable; the checkpoint is the last ``(appno, id)``
seen), and for each mark runs the four §2 checks:

  C1 self-recall   q=mark_name (or mark_sample), text, threshold=0 -> appno present   (S1)
  C2 appno lookup  q=application_number (+ madrid_number if present) -> mark present   (S1)
  C3 count integ.  total == min(DB_count(q), cap); bounded page-walk: no dup/gap        (S1)
  C4 top-N rank    sort=similarity -> exact mark in top-N (default 5)                   (S2)

Every case is flushed to JSONL immediately; on any failure the full raw response is
persisted under ``evidence/<appno>.json``. Honest oracles: a mark with no display
name is ``blocked`` (not failed); page-walk depth is bounded and the bound is
recorded (never silently truncated). Reports TRUE POPULATION RATES over the corpus.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from dataclasses import dataclass, field

from . import Config, RunStore
from .asyncclient import AsyncResponse, AsyncSearchClient

_CAP = 1000  # TEXT_RECALL_CAP: text `total` and scored window cap (mirrors the API).

# Per-mark tuning (overridable via config.census.*).
_DEFAULTS = {
    "concurrency": 48,          # in-flight marks
    "chunk_size": 2000,         # rows fetched per keyset page
    "page_limit": 100,          # hits per search page
    "top_n": 5,                 # C4 rank window
    "pagewalk_cap": 300,        # C3 walks pages fully only up to this many hits
    "db_pool": 48,              # read-only connections for C3 DB counts
}


@dataclass
class CensusMark:
    db_id: int
    application_number: str
    mark_name: str | None
    mark_sample: str | None
    madrid_number: str | None
    mark_category: str | None

    @property
    def display(self) -> str:
        return (self.mark_name or self.mark_sample or "").strip()

    @property
    def source(self) -> str:
        return "madrid" if (self.mark_category or "").startswith("madrid") else "domestic"


# --------------------------------------------------------------------------- #
# Read-only DB: keyset streaming + a tiny connection pool for C3 counts
# --------------------------------------------------------------------------- #
class CensusDB:
    """READ-ONLY Postgres access for the census: a keyset stream over the corpus
    and a small pool of pinned read-only connections for concurrent C3 counts."""

    def __init__(self, cfg: Config, pool_size: int):
        self.cfg = cfg
        self._driver = self._import_driver()
        self.stream_conn = self._connect()
        self._pool: asyncio.Queue = asyncio.Queue()
        self._pool_conns = [self._connect() for _ in range(pool_size)]
        for c in self._pool_conns:
            self._pool.put_nowait(c)

    def _import_driver(self):
        try:
            import psycopg

            return ("psycopg", psycopg)
        except ModuleNotFoundError:
            import psycopg2

            return ("psycopg2", psycopg2)

    def _connect(self):
        name, mod = self._driver
        if name == "psycopg":
            conn = mod.connect(self.cfg.db_dsn, autocommit=True)
        else:
            conn = mod.connect(self.cfg.db_dsn)
            conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SET default_transaction_read_only = on")
        cur.close()
        return conn

    def total_marks(self) -> int:
        cur = self.stream_conn.cursor()
        cur.execute("SELECT count(*) FROM trademarks")
        n = int(cur.fetchone()[0])
        cur.close()
        return n

    def stream_chunk(self, after_appno: str | None, after_id: int | None, limit: int) -> list[CensusMark]:
        """Next keyset page after ``(after_appno, after_id)`` in (appno, id) order."""
        cur = self.stream_conn.cursor()
        if after_appno is None:
            cur.execute(
                """
                SELECT id, application_number, mark_name, mark_sample, madrid_number, mark_category
                FROM trademarks
                ORDER BY application_number, id
                LIMIT %s
                """,
                (limit,),
            )
        else:
            cur.execute(
                """
                SELECT id, application_number, mark_name, mark_sample, madrid_number, mark_category
                FROM trademarks
                WHERE (application_number, id) > (%s, %s)
                ORDER BY application_number, id
                LIMIT %s
                """,
                (after_appno, after_id, limit),
            )
        rows = cur.fetchall()
        cur.close()
        return [CensusMark(*r) for r in rows]

    @staticmethod
    def _count_substring(conn, q: str) -> int:
        like = f"%{q.lower()}%"
        cur = conn.cursor()
        cur.execute(
            """
            SELECT count(*) FROM trademarks WHERE
                lower(mark_sample) LIKE %(l)s OR lower(mark_name) LIKE %(l)s
                OR application_number ILIKE %(l)s OR certificate_number ILIKE %(l)s
                OR madrid_number ILIKE %(l)s
            """,
            {"l": like},
        )
        n = int(cur.fetchone()[0])
        cur.close()
        return n

    async def count_substring(self, q: str) -> int:
        conn = await self._pool.get()
        try:
            return await asyncio.to_thread(self._count_substring, conn, q)
        finally:
            self._pool.put_nowait(conn)

    def close(self) -> None:
        for c in [self.stream_conn, *self._pool_conns]:
            try:
                c.close()
            except Exception:
                pass


# --------------------------------------------------------------------------- #
# Per-mark check logic
# --------------------------------------------------------------------------- #
@dataclass
class CaseRow:
    case_id: str
    check: str            # C1 | C2 | C3 | C4
    application_number: str
    status: str           # pass | fail | blocked | error
    severity: str | None
    query: str
    expected: str
    observed: str
    latency_s: float
    source: str
    evidence: str | None = None
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


async def _present_with_pagewalk(
    client: AsyncSearchClient, q: str, target: str, mode: str, page_limit: int, cap: int
) -> tuple[bool, AsyncResponse, int]:
    """Is ``target`` appno in the result set for ``q``? Checks page 1; on a miss
    with more pages available, walks remaining pages (bounded by ``cap``) before
    concluding absence. Returns (found, first_response, hits_scanned)."""
    r = await client.search(q, mode=mode, ranked=True, threshold=0.0, page=0, limit=page_limit)
    if r.error:
        return (False, r, 0)
    if target in client.appnos(r.items):
        return (True, r, len(r.items))
    scanned = len(r.items)
    reachable = min(r.total, cap)
    page = 1
    while scanned < reachable:
        rp = await client.search(q, mode=mode, ranked=True, threshold=0.0, page=page, limit=page_limit)
        if rp.error or not rp.items:
            break
        if target in client.appnos(rp.items):
            return (True, r, scanned + len(rp.items))
        scanned += len(rp.items)
        page += 1
    return (False, r, scanned)


async def _resume_pagewalk(client, q, r0, target, page_limit, cap) -> tuple[bool, int]:
    """C1 miss-confirmation, reusing ``r0`` as page 0 (no duplicate fetch)."""
    if target in client.appnos(r0.items):
        return (True, len(r0.items))
    scanned = len(r0.items)
    reachable = min(r0.total, cap)
    page = 1
    while scanned < reachable:
        rp = await client.search(q, mode="text", ranked=True, threshold=0.0, page=page, limit=page_limit)
        if rp.error or not rp.items:
            break
        if target in client.appnos(rp.items):
            return (True, scanned + len(rp.items))
        scanned += len(rp.items)
        page += 1
    return (False, scanned)


async def _c1_from(client, store, m: CensusMark, q: str, r0: AsyncResponse) -> CaseRow:
    """C1 self-recall derived from the shared ``r0`` (q=mark_name) response."""
    cid = f"C1:{m.application_number}"
    if r0.error:
        return CaseRow(cid, "C1", m.application_number, "error", None, q, "appno in results",
                       f"err={r0.error}", r0.latency_s, m.source)
    found, scanned = await _resume_pagewalk(client, q, r0, m.application_number, 100, _CAP)
    # Honest-oracle cap guard: a generic name (e.g. "R", "THE") matches > the
    # TEXT_RECALL_CAP; the mark legitimately sits beyond the scored top-1000 window.
    if not found and r0.total >= _CAP:
        return CaseRow(cid, "C1", m.application_number, "blocked", None, q, "appno in results",
                       f"name too generic: matches>={_CAP} (TEXT_RECALL_CAP), beyond window; "
                       f"total={r0.total}", r0.latency_s, m.source)
    status = "pass" if found else "fail"
    ev = await _evidence(client, store, cid, q, "text") if status == "fail" else None
    return CaseRow(cid, "C1", m.application_number, status, None if found else "S1",
                   q, "appno in results", f"found={found} total={r0.total} scanned={scanned}",
                   r0.latency_s, m.source, ev)


async def check_c2(client, store, m: CensusMark) -> list[CaseRow]:
    rows: list[CaseRow] = []
    cid = f"C2:{m.application_number}"
    found, r, scanned = await _present_with_pagewalk(
        client, m.application_number, m.application_number, "text", 100, 1000)
    if not found and not r.error and r.total >= _CAP:
        rows.append(CaseRow(cid, "C2", m.application_number, "blocked", None,
                            m.application_number, "mark in results",
                            f"appno substring too broad: matches>={_CAP}; total={r.total}",
                            r.latency_s, m.source))
        return rows
    status = "error" if r.error else ("pass" if found else "fail")
    ev = await _evidence(client, store, cid, m.application_number, "text") if status == "fail" else None
    rows.append(CaseRow(cid, "C2", m.application_number, status,
                        None if found else ("S1" if status == "fail" else None),
                        m.application_number, "mark in results",
                        f"found={found} total={r.total} scanned={scanned}"
                        + (f" err={r.error}" if r.error else ""), r.latency_s, m.source, ev))
    if m.madrid_number:
        cidm = f"C2m:{m.application_number}"
        qf, rm, sc = await _present_with_pagewalk(
            client, str(m.madrid_number), m.application_number, "text", 100, 1000)
        st = "error" if rm.error else ("pass" if qf else "fail")
        evm = await _evidence(client, store, cidm, str(m.madrid_number), "text") if st == "fail" else None
        rows.append(CaseRow(cidm, "C2", m.application_number, st,
                            None if qf else ("S1" if st == "fail" else None),
                            f"madrid:{m.madrid_number}", "mark in results",
                            f"found={qf} total={rm.total} scanned={sc}"
                            + (f" err={rm.error}" if rm.error else ""), rm.latency_s, m.source, evm))
    return rows


async def _c3_from(client, db, store, m: CensusMark, q: str, r0: AsyncResponse,
                   cap: int, pagewalk_cap: int) -> CaseRow:
    """C3 count-integrity derived from the shared ``r0`` + a DB count oracle."""
    cid = f"C3:{m.application_number}"
    db_count = await db.count_substring(q)
    expected = min(db_count, cap)
    if r0.error:
        ev = await _evidence(client, store, cid, q, "text")
        return CaseRow(cid, "C3", m.application_number, "error", None, q,
                       f"total==min(db {db_count},cap {cap})={expected}",
                       f"err={r0.error}", r0.latency_s, m.source, ev)
    total_ok = r0.total == expected
    walk_note, dup_gap_ok = "no-walk", True
    reachable = min(r0.total, cap)
    if reachable <= pagewalk_cap:
        # Dedup/gap on the record id (always present; Madrid rows can have NULL
        # application_number, which would otherwise look like a phantom gap).
        seen: list[str] = list(client.ids(r0.items))
        page = 1
        while len(seen) < reachable:
            rp = await client.search(q, mode="text", ranked=True, threshold=0.0, page=page, limit=100)
            if rp.error or not rp.items:
                break
            seen.extend(client.ids(rp.items))
            page += 1
        dups = [a for a, c in Counter(seen).items() if c > 1]
        unique = len(set(seen))
        dup_gap_ok = (not dups) and unique == reachable
        walk_note = f"full-walk unique={unique}/{reachable} dups={len(dups)}"
    else:
        walk_note = f"bounded(>{pagewalk_cap} hits, total-only)"
    ok = total_ok and dup_gap_ok
    status = "pass" if ok else "fail"
    ev = await _evidence(client, store, cid, q, "text") if status == "fail" else None
    return CaseRow(cid, "C3", m.application_number, status, None if ok else "S1", q,
                   f"total==min(db {db_count},cap {cap})={expected}; no dup/gap",
                   f"api_total={r0.total} db={db_count} total_ok={total_ok} {walk_note}",
                   r0.latency_s, m.source, ev)


async def _c4_from(client, store, m: CensusMark, q: str, r0: AsyncResponse, top_n: int) -> CaseRow:
    """C4 top-N rank derived from the shared ``r0`` (q=mark_name, sort=similarity)."""
    cid = f"C4:{m.application_number}"
    if r0.error:
        return CaseRow(cid, "C4", m.application_number, "error", None, q,
                       f"rank< {top_n}", f"err={r0.error}", r0.latency_s, m.source)
    appnos = client.appnos(r0.items)
    rank = appnos.index(m.application_number) if m.application_number in appnos else -1
    # Cap guard: absent because the name matches > the cap window is a recall-cap
    # concern (C1), not a ranking defect -> blocked here.
    if rank < 0 and r0.total >= _CAP:
        return CaseRow(cid, "C4", m.application_number, "blocked", None, q, f"rank< {top_n}",
                       f"name too generic: matches>={_CAP}, beyond window; total={r0.total}",
                       r0.latency_s, m.source)
    ok = 0 <= rank < top_n
    status = "pass" if ok else "fail"
    ev = await _evidence(client, store, cid, q, "text") if status == "fail" else None
    return CaseRow(cid, "C4", m.application_number, status, None if ok else "S2", q,
                   f"rank < {top_n}", f"rank={rank} total={r0.total}", r0.latency_s, m.source, ev)


async def _evidence(client: AsyncSearchClient, store: RunStore, cid: str, q: str, mode: str) -> str | None:
    """Re-fetch with raw body and persist it (only called on a failure — cheap)."""
    try:
        r = await client.search(q, mode=mode, ranked=True, threshold=0.0, page=0, limit=100, keep_raw=True)
        return store.evidence(cid, q, r.raw)
    except Exception:
        return None


def _blocked_named(m: CensusMark, check: str, expected: str) -> CaseRow:
    return CaseRow(f"{check}:{m.application_number}", check, m.application_number, "blocked",
                   None, "", expected, "no display name (figurative)", 0.0, m.source)


async def process_mark(client, db, store, m: CensusMark, cfg_c: dict) -> list[CaseRow]:
    """One mark -> C1..C4. C1/C3/C4 share a SINGLE ranked q=mark_name fetch (they
    are the identical query) — halving per-mark request volume vs one call each."""
    rows: list[CaseRow] = []
    q = m.display
    if not q:
        rows += [_blocked_named(m, "C1", "appno in results"),
                 _blocked_named(m, "C3", "count integrity"),
                 _blocked_named(m, "C4", f"rank< {cfg_c['top_n']}")]
    else:
        r0 = await client.search(q, mode="text", ranked=True, threshold=0.0, page=0, limit=100)
        rows.append(await _c1_from(client, store, m, q, r0))
        rows.append(await _c3_from(client, db, store, m, q, r0, _CAP, cfg_c["pagewalk_cap"]))
        rows.append(await _c4_from(client, store, m, q, r0, cfg_c["top_n"]))
    rows.extend(await check_c2(client, store, m))
    return rows


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def _census_cfg(cfg: Config) -> dict:
    c = dict(_DEFAULTS)
    c.update((cfg.raw.get("census") or {}))
    return c


async def run_census(cfg: Config, store: RunStore, base_url: str, max_marks: int | None = None) -> dict:
    cc = _census_cfg(cfg)
    db = CensusDB(cfg, pool_size=cc["db_pool"])
    total = db.total_marks()
    target = min(total, max_marks) if max_marks else total
    sem = asyncio.Semaphore(cc["concurrency"])

    st = store.load_state() or {}
    after_appno = st.get("last_appno")
    after_id = st.get("last_id")
    processed = int(st.get("processed", 0))
    tallies = Counter(st.get("tallies", {}))
    t_start = time.time()

    async with AsyncSearchClient(cfg, base_url, max_connections=cc["concurrency"] * 2 + 50) as client:
        async def one(m: CensusMark):
            async with sem:
                rows = await process_mark(client, db, store, m, cc)
            for row in rows:
                if not store.already_done(row.case_id):
                    store.append_case(vars(row))
                    if row.status in ("pass", "fail", "blocked", "error"):
                        tallies[f"{row.check}:{row.status}"] += 1
            return m

        while processed < target:
            chunk = db.stream_chunk(after_appno, after_id, cc["chunk_size"])
            if not chunk:
                break
            if max_marks:
                chunk = chunk[: max(0, target - processed)]
            await asyncio.gather(*(one(m) for m in chunk))
            processed += len(chunk)
            after_appno, after_id = chunk[-1].application_number, chunk[-1].db_id
            elapsed = time.time() - t_start
            rps = processed / elapsed if elapsed else 0
            store.write_state({
                "phase": "census", "last_appno": after_appno, "last_id": after_id,
                "processed": processed, "target": target, "corpus_total": total,
                "tallies": dict(tallies), "elapsed_s": int(elapsed),
            })
            store.heartbeat(
                f"[census] {processed}/{target} marks ({100 * processed / target:.1f}%) "
                f"~{rps:.0f} marks/s | C1 fails={tallies['C1:fail']} C2 fails={tallies['C2:fail']} "
                f"C3 fails={tallies['C3:fail']} C4 fails={tallies['C4:fail']}"
            )

    db.close()
    summary = {
        "phase": "census", "processed": processed, "target": target, "corpus_total": total,
        "tallies": dict(tallies), "elapsed_s": int(time.time() - t_start),
    }
    (store.dir / "census_summary.json").write_text(json.dumps(summary, indent=2))
    return summary


# --------------------------------------------------------------------------- #
# Census report
# --------------------------------------------------------------------------- #
_CHECK_META = {
    "C1": ("self-recall (q=mark_name)", "S1"),
    "C2": ("appno/madrid lookup", "S1"),
    "C3": ("count integrity + page-walk", "S1"),
    "C4": ("top-N rank (sort=similarity)", "S2"),
}


def build_census_report(store: RunStore, summary: dict | None = None) -> str:
    cases = store.cases()
    by_check: dict[str, Counter] = {k: Counter() for k in _CHECK_META}
    fails: dict[str, list[str]] = {k: [] for k in _CHECK_META}
    for c in cases:
        chk = c.get("check")
        if chk not in by_check:
            continue
        by_check[chk][c["status"]] += 1
        if c["status"] == "fail":
            fails[chk].append(c["application_number"])

    corpus = (summary or {}).get("corpus_total", "?")
    processed = (summary or {}).get("processed", "?")
    elapsed = (summary or {}).get("elapsed_s", "?")
    lines = [
        "# Tradenet Search — Census Report",
        "",
        f"- Corpus total: **{corpus}**  ·  marks processed: **{processed}**  ·  elapsed: **{elapsed}s**",
        "",
        "## Population rates (true census, no CI)",
        "| Check | what | sev | eligible | pass | fail | blocked | error | pass-rate |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for chk, (desc, sev) in _CHECK_META.items():
        cnt = by_check[chk]
        npass, nfail = cnt["pass"], cnt["fail"]
        nblock, nerr = cnt["blocked"], cnt["error"]
        eligible = npass + nfail
        rate = f"{npass / eligible:.4%}" if eligible else "n/a"
        lines.append(f"| {chk} | {desc} | {sev} | {eligible} | {npass} | {nfail} | "
                     f"{nblock} | {nerr} | {rate} |")
    lines += ["", "## Failing application_numbers (per check)"]
    for chk in _CHECK_META:
        fl = fails[chk]
        if not fl:
            lines.append(f"- **{chk}**: none")
            continue
        path = store.dir / f"census_failing_{chk}.txt"
        path.write_text("\n".join(fl))
        shown = ", ".join(fl[:50])
        more = f" … (+{len(fl) - 50} more in {path.name})" if len(fl) > 50 else ""
        lines.append(f"- **{chk}** ({len(fl)} fails): {shown}{more}")
    lines += ["", "_Honest-oracle notes: nameless figurative marks are `blocked` (no display "
              "name to self-recall), not failed. C3 page-walk is full up to the configured cap "
              "and `bounded` (total-equality only) above it — bounding is recorded, never silent._", ""]
    return "\n".join(lines)
