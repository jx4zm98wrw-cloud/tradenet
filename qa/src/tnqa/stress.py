"""Stress / load harness — closed-loop async load generator.

Replays a fixed, representative query mix (exact names, substrings, appno,
phonetic, one ultra-broad single char) at concurrency levels 10 -> 100 -> 1000,
each held for a steady-state window after a warmup. Per level it measures achieved
throughput (req/s), latency p50/p95/p99/max, and error rate by class
(timeout / 5xx / conn_reset / 429), and reports the **saturation point** — the
concurrency where p95 crosses the SLO or errors climb.

Two targets, clearly labelled:
  * UNTHROTTLED (the test instance, limiter lifted) — the real capacity ceiling.
  * THROTTLED   (the production-default instance) — an informational ramp that
    characterizes the 429 / Retry-After limiter under flood.

Caveat (always stated in the report): the unthrottled number is a capacity
ceiling, not what a production client sees behind the limiter.
"""

from __future__ import annotations

import asyncio
import json
import random
import time

from . import Config, GroundTruth, RunStore
from .asyncclient import AsyncSearchClient

_DEFAULTS = {
    "levels": [10, 100, 1000],
    "warmup_s": 3.0,
    "window_s": 12.0,
    "mix_per_kind": 12,        # real queries sampled per kind
    "throttled_concurrency": 50,
    "throttled_window_s": 8.0,
    "slo_p95_typical_s": 3.0,
    "slo_p95_broad_s": 5.0,
    "error_rate_saturation": 0.01,   # >1% errors => saturated
}


def _pct(sorted_vals: list[float], q: float) -> float:
    if not sorted_vals:
        return 0.0
    i = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return sorted_vals[i]


def _stress_cfg(cfg: Config) -> dict:
    c = dict(_DEFAULTS)
    c.update((cfg.raw.get("stress") or {}))
    return c


# --------------------------------------------------------------------------- #
# Query mix — sampled once from real data, fixed for the whole ramp
# --------------------------------------------------------------------------- #
def build_query_mix(cfg: Config, n: int) -> list[tuple[str, str, str]]:
    """Return a list of (kind, q, mode). Sampled from real marks so the load is
    representative of production traffic, plus one deliberate ultra-broad query."""
    gt = GroundTruth(cfg)
    rng = random.Random(cfg.sampling["rng_seed"])
    marks = gt.sample_gold(n * 3, rng)
    gt.close()
    mix: list[tuple[str, str, str]] = []
    named = [m for m in marks if (m.mark_name or m.mark_sample)]
    for m in named[:n]:
        disp = (m.mark_name or m.mark_sample or "").strip()
        if disp:
            mix.append(("exact", disp, "text"))
    for m in named[:n]:
        disp = (m.mark_name or m.mark_sample or "").strip()
        if len(disp) >= 6:
            mix.append(("substring", disp[1:5], "text"))
    for m in marks[:n]:
        if m.application_number:
            mix.append(("appno", m.application_number, "text"))
    for m in named[:n]:
        disp = (m.mark_name or m.mark_sample or "").strip()
        if len(disp) >= 4:
            i = len(disp) // 2
            mix.append(("phonetic", disp[:i] + disp[i:].replace(disp[i], "x", 1), "phonetic"))
    mix.append(("broad", "a", "text"))   # one ultra-broad single char
    return [t for t in mix if t[1]]


# --------------------------------------------------------------------------- #
# One concurrency level — closed loop for warmup + window seconds
# --------------------------------------------------------------------------- #
async def run_level(
    client: AsyncSearchClient, mix: list[tuple[str, str, str]], concurrency: int,
    warmup_s: float, window_s: float,
) -> dict:
    samples: list[tuple[float, float, int, str | None]] = []  # (start_rel, latency, status, err_class)
    t0 = time.perf_counter()
    stop_at = t0 + warmup_s + window_s

    async def worker(wid: int):
        rng = random.Random(1000 + wid)
        while time.perf_counter() < stop_at:
            kind, q, mode = mix[rng.randrange(len(mix))]
            start_rel = time.perf_counter() - t0
            r = await client.search(q, mode=mode, ranked=True, threshold=0.0, limit=20)
            samples.append((start_rel, r.latency_s, r.status, r.error_class))

    await asyncio.gather(*(worker(i) for i in range(concurrency)))

    # Steady-state = samples whose request STARTED after warmup.
    steady = [s for s in samples if s[0] >= warmup_s]
    if not steady:
        steady = samples
    lats = sorted(s[1] for s in steady)
    n = len(steady)
    errors = [s for s in steady if s[3] is not None]
    err_by_class: dict[str, int] = {}
    for s in errors:
        err_by_class[s[3]] = err_by_class.get(s[3], 0) + 1
    ok = n - len(errors)
    return {
        "concurrency": concurrency,
        "requests": n,
        "ok": ok,
        "throughput_rps": round(n / window_s, 1),
        "ok_throughput_rps": round(ok / window_s, 1),
        "p50_s": round(_pct(lats, 0.50), 3),
        "p95_s": round(_pct(lats, 0.95), 3),
        "p99_s": round(_pct(lats, 0.99), 3),
        "max_s": round(lats[-1], 3) if lats else 0.0,
        "error_rate": round(len(errors) / n, 4) if n else 0.0,
        "errors_by_class": err_by_class,
    }


# --------------------------------------------------------------------------- #
# Throttled limiter characterization (informational)
# --------------------------------------------------------------------------- #
async def characterize_limiter(cfg: Config, base_url: str, concurrency: int, window_s: float,
                               mix: list[tuple[str, str, str]]) -> dict:
    """Flood the production-default instance and record 429 behavior + Retry-After.
    Retries are OFF so we observe the raw limiter response, not our backoff. The
    query mix is pre-built and passed in (no DB connect mid-flood, which would fail
    if Postgres connections are saturated from the unthrottled ramp)."""
    statuses: dict[int, int] = {}
    retry_afters: list[float] = []
    t0 = time.perf_counter()
    stop_at = t0 + window_s

    async with AsyncSearchClient(cfg, base_url, max_connections=concurrency + 20,
                                 retry_429=False, max_retries=1) as client:
        async def worker(wid: int):
            rng = random.Random(wid)
            while time.perf_counter() < stop_at:
                _, q, mode = mix[rng.randrange(len(mix))]
                try:
                    resp = await client._client.get(
                        f"{client.base_url}{client.s['search_path']}",
                        params=client._params(q, mode, True, 0.0, 0, 20, None),
                    )
                    statuses[resp.status_code] = statuses.get(resp.status_code, 0) + 1
                    if resp.status_code == 429:
                        ra = resp.headers.get("Retry-After")
                        if ra:
                            try:
                                retry_afters.append(float(ra))
                            except ValueError:
                                pass
                except Exception:
                    statuses[0] = statuses.get(0, 0) + 1

        await asyncio.gather(*(worker(i) for i in range(concurrency)))
    total = sum(statuses.values())
    return {
        "base_url": base_url,
        "concurrency": concurrency,
        "window_s": window_s,
        "total_requests": total,
        "status_counts": statuses,
        "http_200": statuses.get(200, 0),
        "http_429": statuses.get(429, 0),
        "throttle_rate": round(statuses.get(429, 0) / total, 4) if total else 0.0,
        "served_rps": round(statuses.get(200, 0) / window_s, 1),
        "retry_after_samples": retry_afters[:20],
    }


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
async def run_stress(
    cfg: Config, store: RunStore, test_url: str, throttled_url: str,
    levels: list[int] | None = None,
) -> dict:
    sc = _stress_cfg(cfg)
    levels = levels or sc["levels"]
    mix = build_query_mix(cfg, sc["mix_per_kind"])
    store.heartbeat(f"[stress] query mix: {len(mix)} queries "
                    f"({sorted(set(k for k, _, _ in mix))}); levels={levels}")

    unthrottled: list[dict] = []
    saturation = None
    async with AsyncSearchClient(cfg, test_url, max_connections=max(levels) + 100) as client:
        await client.search("warmup", mode="text", limit=1)
        for c in levels:
            store.heartbeat(f"[stress] UNTHROTTLED concurrency={c} "
                            f"(warmup {sc['warmup_s']}s + window {sc['window_s']}s)…")
            m = await run_level(client, mix, c, sc["warmup_s"], sc["window_s"])
            unthrottled.append(m)
            store.heartbeat(f"[stress]   -> {m['throughput_rps']} rps, "
                            f"p50={m['p50_s']}s p95={m['p95_s']}s p99={m['p99_s']}s "
                            f"err={m['error_rate']:.2%} {m['errors_by_class']}")
            if saturation is None and (
                m["p95_s"] > sc["slo_p95_typical_s"] or m["error_rate"] > sc["error_rate_saturation"]
            ):
                saturation = {"concurrency": c, "p95_s": m["p95_s"], "error_rate": m["error_rate"]}

    store.heartbeat(f"[stress] THROTTLED limiter characterization on {throttled_url} "
                    f"(concurrency={sc['throttled_concurrency']})…")
    throttled = await characterize_limiter(
        cfg, throttled_url, sc["throttled_concurrency"], sc["throttled_window_s"], mix)
    store.heartbeat(f"[stress]   -> {throttled['http_200']}x200 {throttled['http_429']}x429 "
                    f"throttle_rate={throttled['throttle_rate']:.2%} "
                    f"served~{throttled['served_rps']} rps")

    report = {
        "test_url": test_url, "throttled_url": throttled_url, "levels": levels,
        "config": {k: sc[k] for k in ("warmup_s", "window_s", "slo_p95_typical_s",
                                      "slo_p95_broad_s", "error_rate_saturation")},
        "mix_size": len(mix), "mix_kinds": sorted(set(k for k, _, _ in mix)),
        "unthrottled": unthrottled,
        "saturation_point": saturation,
        "throttled": throttled,
    }
    (store.dir / "stress_summary.json").write_text(json.dumps(report, indent=2, default=str))
    return report


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #
def build_stress_report(report: dict) -> str:
    lines = [
        "# Tradenet Search — Stress / Load Report",
        "",
        f"- Unthrottled target (capacity ceiling): `{report['test_url']}`",
        f"- Throttled target (production limiter): `{report['throttled_url']}`",
        f"- Query mix: {report['mix_size']} queries across {report['mix_kinds']}",
        f"- SLO: p95 < {report['config']['slo_p95_typical_s']}s typical "
        f"(< {report['config']['slo_p95_broad_s']}s broad); "
        f"saturation also when error-rate > {report['config']['error_rate_saturation']:.0%}",
        "",
        "## Unthrottled ramp (real capacity ceiling)",
        "| concurrency | throughput rps | ok rps | p50 s | p95 s | p99 s | max s | error rate | errors by class |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for m in report["unthrottled"]:
        lines.append(
            f"| {m['concurrency']} | {m['throughput_rps']} | {m['ok_throughput_rps']} | "
            f"{m['p50_s']} | {m['p95_s']} | {m['p99_s']} | {m['max_s']} | "
            f"{m['error_rate']:.2%} | {m['errors_by_class'] or '—'} |")
    sat = report.get("saturation_point")
    lines += ["", "## Saturation point"]
    if sat:
        lines.append(f"- **Saturated at concurrency {sat['concurrency']}** "
                     f"(p95={sat['p95_s']}s, error-rate={sat['error_rate']:.2%}) — "
                     f"first level to cross the SLO / error threshold.")
    else:
        lines.append("- No saturation observed across the tested levels "
                     "(p95 stayed within SLO and errors stayed low).")
    t = report["throttled"]
    lines += [
        "", "## Throttled limiter characterization (informational)",
        f"- Flooded `{t['base_url']}` at concurrency {t['concurrency']} for {t['window_s']}s "
        f"with retries OFF (raw limiter behavior).",
        f"- {t['http_200']}×200, {t['http_429']}×429 → throttle-rate **{t['throttle_rate']:.2%}**, "
        f"served ≈ **{t['served_rps']} rps** (the production-client ceiling).",
        f"- Retry-After samples (s): {t['retry_after_samples'] or 'none returned'}",
        f"- Full status histogram: {t['status_counts']}",
        "",
        "## Caveat",
        "- The **unthrottled** numbers are a *capacity ceiling* of the backend itself "
        "(multi-worker test instance), NOT what a production client experiences. Production "
        "traffic is capped by the limiter characterized above — both are reported, clearly labelled.",
        "",
    ]
    return "\n".join(lines)
