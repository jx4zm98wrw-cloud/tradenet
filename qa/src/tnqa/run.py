"""Orchestrator, group case-runners, smoke gate, report, and CLI.

Run model (two human gates, autonomous in between):
  python -m tnqa.run smoke    # 5-min self-check; green ⇒ safe to run
  python -m tnqa.run run      # autonomous adaptive-sampled run; auto-resumes
  python -m tnqa.run report   # (re)generate report.md from cases.jsonl

A "group" drives one headline binomial metric (recall/pass-rate) to a target
Wilson-CI half-width via sequential batched sampling, persisting every case.
"""

from __future__ import annotations

import argparse
import pathlib
import random
import sys
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone

from . import (
    CaseResult,
    Config,
    GoldMark,
    GroundTruth,
    QA_ROOT,
    RunStore,
    SearchClient,
    load_config,
    wilson_interval,
)

QA_GROUPS = ["A", "B", "C", "D", "E"]
_START = time.time()


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _perturb(s: str, rng: random.Random) -> str:
    """One-edit sound-alike for fuzzy/phonetic probes (swap an interior char)."""
    if len(s) < 4:
        return s + s[-1]
    i = rng.randrange(1, len(s) - 1)
    repl = rng.choice("aeiou" if s[i].lower() not in "aeiou" else "bcdfg")
    return s[:i] + repl + s[i + 1:]


def _stratum(gm: GoldMark, matcher: str) -> dict:
    return {"source": gm.source, "script": gm.script, "length": gm.length, "matcher": matcher}


def _blocked(cid: str, group: str, name: str, gm: GoldMark, why: str) -> CaseResult:
    return CaseResult(cid, group, name, "blocked", None, "", "", why, 0.0, _stratum(gm, "n/a"), None)


# --------------------------------------------------------------------------- #
# Case templates — each returns a CaseResult for one gold mark.
# Severity follows the confirmed claim bar: a missed similar mark (recall) is S1.
# --------------------------------------------------------------------------- #
def case_exact_name(client: SearchClient, gm: GoldMark, store: RunStore) -> CaseResult:
    cid = f"A-01:{gm.application_number}"
    q = (gm.mark_name or gm.mark_sample or "").strip()
    if not q:
        return _blocked(cid, "A", "A-01 exact name", gm, "no display name")
    r = client.search(q, mode="text", threshold=0.0, limit=100)
    found = gm.application_number in client.appnos(r.items)
    return CaseResult(
        cid, "A", "A-01 exact name recall",
        "pass" if found else ("error" if r.error else "fail"), None if found else "S1",
        q, f"contains {gm.application_number}",
        f"{len(r.items)} hits, found={found}" + (f", err={r.error}" if r.error else ""),
        r.latency_s, _stratum(gm, "text"), store.evidence(cid, q, r.raw),
    )


def case_appno(client: SearchClient, gm: GoldMark, store: RunStore) -> CaseResult:
    cid = f"A-05:{gm.application_number}"
    q = gm.application_number
    r = client.search(q, mode="text", threshold=0.0, limit=50)
    ok = gm.application_number in client.appnos(r.items)
    return CaseResult(
        cid, "A", "A-05/06 application-number lookup",
        "pass" if ok else ("error" if r.error else "fail"), None if ok else "S1",
        q, f"contains {gm.application_number}", f"{len(r.items)} hits",
        r.latency_s, _stratum(gm, "text"), store.evidence(cid, q, r.raw),
    )


def case_count_integrity(client: SearchClient, gt: GroundTruth, gm: GoldMark, store: RunStore) -> CaseResult:
    cid = f"A-07:{gm.application_number}"
    disp = gm.mark_name or gm.mark_sample or ""
    q = (disp[:4].strip() or disp.strip()).lower()
    if not q:
        return _blocked(cid, "A", "A-07 count integrity", gm, "no probe substring")
    db = gt.count_substring(q)
    r = client.search(q, mode="text", threshold=0.0, limit=50)
    # The API caps a text total at TEXT_RECALL_CAP; a broad substring matching more
    # than the cap correctly reports the cap, not the raw DB count. Expect min().
    cap = int(client.cfg.schema.get("text_recall_cap", 1000))
    expected = min(db, cap)
    ok = r.total == expected
    return CaseResult(
        cid, "A", "A-07 count integrity",
        "pass" if ok else ("error" if r.error else "fail"), None if ok else "S1",
        q, f"total == min(DB({db}), cap {cap}) = {expected}", f"api_total={r.total}, db={db}",
        r.latency_s, _stratum(gm, "text"), store.evidence(cid, q, r.raw),
    )


def case_phonetic_recall(client: SearchClient, gm: GoldMark, store: RunStore, rng: random.Random) -> CaseResult:
    cid = f"B-06:{gm.application_number}"
    base = (gm.mark_name or gm.mark_sample or "").strip()
    if len(base) < 4:
        return _blocked(cid, "B", "B-06/07 phonetic recall", gm, "name too short to perturb")
    q = _perturb(base, rng)
    r = client.search(q, mode="phonetic", threshold=0.0, limit=100)
    found = gm.application_number in client.appnos(r.items)
    return CaseResult(
        cid, "B", "B-06/07 phonetic/fuzzy recall",
        "pass" if found else ("error" if r.error else "fail"), None if found else "S1",
        f"{q} (~{base})", f"contains {gm.application_number}",
        f"{len(r.items)} hits, found={found}", r.latency_s,
        _stratum(gm, "phonetic"), store.evidence(cid, q, r.raw),
    )


def case_diacritic(client: SearchClient, gm: GoldMark, store: RunStore) -> CaseResult:
    cid = f"C-01:{gm.application_number}"
    base = (gm.mark_name or gm.mark_sample or "").strip()
    stripped = _strip_diacritics(base)
    if stripped == base:
        return _blocked(cid, "C", "C-01 diacritic-insensitive", gm, "no diacritics")
    r = client.search(stripped, mode="phonetic", threshold=0.0, limit=100)
    found = gm.application_number in client.appnos(r.items)
    return CaseResult(
        cid, "C", "C-01 diacritic-insensitive (phonetic)",
        "pass" if found else ("error" if r.error else "fail"), None if found else "S1",
        f"{stripped} (~{base})", f"contains {gm.application_number}",
        f"{len(r.items)} hits, found={found}", r.latency_s,
        _stratum(gm, "phonetic"), store.evidence(cid, stripped, r.raw),
    )


def case_injection(client: SearchClient, gm: GoldMark, store: RunStore) -> CaseResult:
    cid = f"D-04:{gm.application_number}"
    q = "a' OR '1'='1; DROP TABLE trademarks;-- <script>"
    r = client.search(q, mode="text", threshold=0.0, limit=10)
    safe = r.status in (200, 422) and r.error is None
    return CaseResult(
        cid, "D", "D-04 injection-safe", "pass" if safe else "fail", None if safe else "S1",
        q, "no 5xx / no leak", f"status={r.status} err={r.error}",
        r.latency_s, _stratum(gm, "text"), store.evidence(cid, q, r.raw),
    )


def case_idempotent(client: SearchClient, gm: GoldMark, store: RunStore) -> CaseResult:
    cid = f"D-10:{gm.application_number}"
    q = (gm.mark_name or gm.mark_sample or "")[:6].strip()
    if not q:
        return _blocked(cid, "D", "D-10 idempotency", gm, "no probe")
    a = client.search(q, mode="text", threshold=0.0, limit=50)
    b = client.search(q, mode="text", threshold=0.0, limit=50)
    same = client.appnos(a.items) == client.appnos(b.items) and a.scores == b.scores
    return CaseResult(
        cid, "D", "D-10 idempotency/determinism", "pass" if same else "fail", None if same else "S2",
        q, "identical ordered results", f"identical={same}",
        a.latency_s, _stratum(gm, "text"), store.evidence(cid, q, a.raw),
    )


def case_exact_on_top(client: SearchClient, gm: GoldMark, store: RunStore) -> CaseResult:
    cid = f"E-01:{gm.application_number}"
    q = (gm.mark_name or gm.mark_sample or "").strip()
    if not q:
        return _blocked(cid, "E", "E-01 exact on top", gm, "no name")
    r = client.search(q, mode="text", ranked=True, threshold=0.0, limit=20)
    appnos = client.appnos(r.items)
    rank = appnos.index(gm.application_number) if gm.application_number in appnos else -1
    ok = 0 <= rank <= 4
    return CaseResult(
        cid, "E", "E-01 exact ranks on top",
        "pass" if ok else ("error" if r.error else "fail"), None if ok else "S2",
        q, "rank ≤ top-5", f"rank={rank}", r.latency_s,
        _stratum(gm, "text"), store.evidence(cid, q, r.raw),
    )


def _group_cases(group, client, gt, store, rng):
    """Return (make_cases(gm) -> [CaseResult], headline_index)."""
    if group == "A":
        return (lambda gm: [case_exact_name(client, gm, store), case_appno(client, gm, store),
                            case_count_integrity(client, gt, gm, store)], 0)
    if group == "B":
        return (lambda gm: [case_phonetic_recall(client, gm, store, rng)], 0)
    if group == "C":
        return (lambda gm: [case_diacritic(client, gm, store)], 0)
    if group == "D":
        return (lambda gm: [case_injection(client, gm, store), case_idempotent(client, gm, store)], 0)
    if group == "E":
        return (lambda gm: [case_exact_on_top(client, gm, store)], 0)
    raise ValueError(group)


# --------------------------------------------------------------------------- #
# Orchestrator — sequential Wilson-CI sampling, pacing, breaker, heartbeat,
# budget, continuous checkpointing.
# --------------------------------------------------------------------------- #
def _checkpoint(store, cfg, group, n, passes, errors):
    store.write_state({
        "ts": _now_ts(), "group": group, "n": n, "passes": passes, "errors": errors,
        "rng_seed": cfg.sampling["rng_seed"], "elapsed_s": int(time.time() - _START),
    })


def run_group(group, cfg: Config, client, gt, store: RunStore, rng, deadline: float) -> dict:
    s = cfg.sampling
    z, margin = s["confidence_z"], s["margin"]
    floor_n, ceil_n, batch = s["floor_n"], s["ceiling_n"], s["batch_size"]
    make_cases, head_idx = _group_cases(group, client, gt, store, rng)
    rate_gap = 1.0 / cfg.max_rps if cfg.max_rps > 0 else 0.0

    n = passes = errors = 0
    converged = capped = breaker = False
    while True:
        if time.time() > deadline:
            capped = True
            break
        batch_err = 0
        for gm in gt.sample_gold(batch, rng):
            results = make_cases(gm)
            for res in results:
                if not store.already_done(res.case_id):
                    store.append_case(vars(res))
            head = results[head_idx]
            if head.status in ("pass", "fail"):
                n += 1
                passes += 1 if head.status == "pass" else 0
            elif head.status == "error":
                errors += 1
                batch_err += 1
            time.sleep(rate_gap)
        p, lo, hi = wilson_interval(passes, n, z)
        hw = (hi - lo) / 2
        store.heartbeat(f"[{_now_ts()}] grp={group} n={n} metric={p:.3f} CI=±{hw:.3f} "
                        f"err={errors} elapsed={int(time.time() - _START)}s")
        _checkpoint(store, cfg, group, n, passes, errors)
        if batch and batch_err / batch > 0.5:
            breaker = True
            store.heartbeat(f"[{_now_ts()}] grp={group} CIRCUIT-BREAKER (errors) — skip")
            break
        if n >= floor_n and hw <= margin:
            converged = True
            break
        if n >= ceil_n:
            capped = True
            break
    p, lo, hi = wilson_interval(passes, n, z)
    return {"group": group, "n": n, "metric": round(p, 4), "ci_lo": round(lo, 4),
            "ci_hi": round(hi, 4), "converged": converged, "capped": capped,
            "breaker": breaker, "errors": errors}


# --------------------------------------------------------------------------- #
# Smoke gate — 5-min end-to-end self-check
# --------------------------------------------------------------------------- #
def _results_root() -> pathlib.Path:
    return QA_ROOT / "results"


def smoke(cfg: Config) -> bool:
    print("== SMOKE GATE ==")
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok = ok and bool(cond)
        print(f"  [{'OK' if cond else 'XX'}] {label} {detail}")

    client = SearchClient(cfg)
    r = client.search("a", mode="text", threshold=0.0, limit=1)
    check("connectivity + schema", r.status == 200 and isinstance(r.total, int),
          f"(status={r.status} total={r.total} err={r.error})")
    gold, gt = [], None
    try:
        gt = GroundTruth(cfg)
        gold = gt.sample_gold(3, random.Random(cfg.sampling["rng_seed"]))
        check("gold-set readable (DB read-only)", len(gold) >= 1, f"({len(gold)} sampled)")
    except Exception as e:
        check("gold-set readable (DB read-only)", False, f"({e!r})")
    rp = client.search("a", mode="phonetic", threshold=0.0, limit=1)
    check("mode toggle (phonetic)", rp.error is None, f"(status={rp.status})")
    try:
        probe = RunStore(_results_root() / "smoke")
        probe.append_case({"case_id": "smoke", "ok": True})
        probe.write_state({"smoke": True})
        check("write/checkpoint path", probe.state_path.exists())
    except Exception as e:
        check("write/checkpoint path", False, f"({e!r})")
    if gold and gt:
        store = RunStore(_results_root() / "smoke")
        res = case_exact_name(client, gold[0], store)
        check("one real case end-to-end", res.status in ("pass", "fail"),
              f"({res.case_id} -> {res.status})")
        gt.close()
    print("== SMOKE:", "GREEN — safe to run ==" if ok else "RED — fix before running ==")
    return ok


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
SEV_ORDER = {"S1": 0, "S2": 1, "S3": 2, "S4": 3, None: 9, "": 9}


def build_report(store: RunStore, summaries: list[dict] | None = None) -> str:
    cases = store.cases()
    by_group: dict[str, list] = defaultdict(list)
    for c in cases:
        by_group[c.get("group", "?")].append(c)
    fails = [c for c in cases if c.get("status") == "fail"]
    s1 = [c for c in fails if c.get("severity") == "S1"]
    verdict = "NOT CLEARED — open S1" if s1 else ("CLEARED (no open S1)" if cases else "NO DATA")
    lines = [f"# Tradenet Search QA — Report ({_now_ts()})", "",
             "## 1. Executive summary", f"- Cases executed: **{len(cases)}**",
             f"- Failures: **{len(fails)}** (S1: **{len(s1)}**)",
             f"- Readiness verdict: **{verdict}**", "",
             "## 2. Metrics dashboard (per group)",
             "| Group | n | metric | 95% CI | status | errors |", "|---|---|---|---|---|---|"]
    for sm in (summaries or []):
        st = "converged" if sm["converged"] else ("breaker" if sm.get("breaker")
              else "capped" if sm["capped"] else "—")
        lines.append(f"| {sm['group']} | {sm['n']} | {sm['metric']:.3f} | "
                     f"[{sm['ci_lo']:.3f}, {sm['ci_hi']:.3f}] | {st} | {sm['errors']} |")
    lines += ["", "## 3. Per-group results"]
    for g in sorted(by_group):
        gc = by_group[g]
        npf = sum(1 for c in gc if c["status"] in ("pass", "fail"))
        pr = sum(1 for c in gc if c["status"] == "pass")
        rate = f"{pr / npf:.3f}" if npf else "n/a"
        lines.append(f"- **{g}**: {len(gc)} cases · pass-rate {rate} (n={npf})")
    lines += ["", "## 4. Defects (severity-sorted)"]
    for c in sorted(fails, key=lambda c: SEV_ORDER.get(c.get("severity"), 9))[:200]:
        lines.append(f"- **{c.get('severity')}** `{c['case_id']}` {c['name']} — q=`{c['query']}` "
                     f"expected={c['expected']} observed={c['observed']} "
                     f"[evidence: {c.get('evidence')}]")
    if not fails:
        lines.append("- none")
    lines += ["", "## 5. Recommended Final Approach",
              "- Confirm the marketed operator surface (wildcard/Boolean are exploratory, not parsed).",
              "- Clarify Name-vs-Mark semantics in the unified `q` box (A-03 is a findings report).",
              "- Fast-follow group F over the sidebar facets (applicant/class/agent/Nice/Vienna/status).", ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tnqa", description="Tradenet Search QA suite")
    ap.add_argument("command", choices=["smoke", "run", "report"])
    ap.add_argument("--run-dir", default=None, help="existing results/run-<ts> to resume/report")
    ap.add_argument("--budget-s", type=int, default=None, help="override wall-clock budget (s)")
    args = ap.parse_args(argv)
    cfg = load_config()

    if args.command == "smoke":
        return 0 if smoke(cfg) else 1

    root = _results_root()
    if args.run_dir:
        p = pathlib.Path(args.run_dir)
        run_dir = p if p.is_absolute() else root / args.run_dir
    else:
        run_dir = root / f"run-{_now_ts()}"
    store = RunStore(run_dir)

    if args.command == "report":
        (run_dir / "report.md").write_text(build_report(store))
        print(f"report → {run_dir / 'report.md'}")
        return 0

    # command == run
    if not smoke(cfg):
        print("Smoke gate RED — aborting run.")
        return 1
    rng = random.Random(cfg.sampling["rng_seed"])
    gt = GroundTruth(cfg)
    client = SearchClient(cfg)
    budget = min(args.budget_s or cfg.budget["wall_clock_default_s"], cfg.budget["wall_clock_cap_s"])
    deadline = _START + budget
    summaries: list[dict] = []
    per_group = (deadline - time.time()) / len(QA_GROUPS)
    for g in QA_GROUPS:
        gd = min(deadline, time.time() + per_group)
        summaries.append(run_group(g, cfg, client, gt, store, rng, gd))
        (run_dir / "report.md").write_text(build_report(store, summaries))
    gt.close()
    (run_dir / "report.md").write_text(build_report(store, summaries))
    print(f"\nDONE. Report → {run_dir / 'report.md'}")
    for sm in summaries:
        print(" ", sm)
    return 0


if __name__ == "__main__":
    sys.exit(main())
