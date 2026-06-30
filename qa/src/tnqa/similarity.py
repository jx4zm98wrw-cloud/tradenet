"""Similarity suite hardening — curated confusable-pair oracle + precision/recall/F1.

A clearance tool that floods results scores high recall and is useless, so this
suite measures BOTH:

  * RECALL    — for each confusable pair, does a search for one mark surface its
                mate (the variant query surfaces the pair-mate)?
  * PRECISION — of the top-N actually returned for that query, how many are
                genuinely relevant (string-similar to the query)?

and reports **F1**, broken down by `curated` (hand-picked distinct real marks an
examiner would call confusable — the trustworthy, non-circular oracle) vs
`synthetic` (engine-style perturbations, which test the engine against its own
transform and are inherently circular).

The pairs live in ``qa/data/confusable-pairs.yaml`` (mined from real DB trigram
neighbours, then hand-curated). Relevance for precision uses an INDEPENDENT string
metric (stdlib ``difflib`` ratio + containment), NOT the API's own score, to avoid
grading the engine with its own ruler. Phonetic-but-not-spelled-alike matches are
therefore counted conservatively (precision is a lower bound) — noted in the report.
"""

from __future__ import annotations

import difflib
import json
import pathlib

try:
    import yaml
except Exception:  # pragma: no cover
    yaml = None

from . import Config, RunStore, SearchClient

_DATA = pathlib.Path(__file__).resolve().parents[2] / "data" / "confusable-pairs.yaml"

_DEFAULTS = {
    "recall_window": 50,        # mate must appear within this many ranked hits
    "precision_top_n": 10,      # sample this many top results for precision
    "precision_rel_threshold": 0.50,   # difflib ratio >= this => relevant
    "mode": "phonetic",         # the clearance matcher
}


def _sim_cfg(cfg: Config) -> dict:
    c = dict(_DEFAULTS)
    c.update((cfg.raw.get("similarity") or {}))
    return c


def load_pairs() -> list[dict]:
    if yaml is None:
        raise RuntimeError("PyYAML required")
    if not _DATA.exists():
        return []
    doc = yaml.safe_load(_DATA.read_text()) or {}
    return doc.get("pairs", [])


def _relevant(q: str, name: str | None, threshold: float) -> bool:
    """Independent relevance heuristic: strings are 'relevant' if reasonably similar
    by difflib ratio, or one contains the other (truncation/addition variants)."""
    if not name:
        return False
    a, b = q.lower().strip(), name.lower().strip()
    if not b:
        return False
    if a in b or b in a:
        return True
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _probe_direction(client: SearchClient, query: str, target_appno: str, sc: dict) -> dict:
    """Run one clearance query and measure recall (mate present?) + precision (top-N)."""
    r = client.search(query, mode=sc["mode"], ranked=True, threshold=0.0, limit=sc["recall_window"])
    appnos = client.appnos(r.items)
    found = target_appno in appnos
    rank = appnos.index(target_appno) if found else -1
    top = r.items[: sc["precision_top_n"]]
    rel = sum(1 for it in top if _relevant(query, client._dig(it, client.s["mark_name"])
                                           or client._dig(it, client.s["mark_sample"]),
                                           sc["precision_rel_threshold"]))
    precision = rel / len(top) if top else 0.0
    return {"query": query, "target": target_appno, "found": found, "rank": rank,
            "returned": len(r.items), "precision": precision, "rel": rel,
            "n_top": len(top), "error": r.error}


def run_similarity(cfg: Config, store: RunStore, base_url: str) -> dict:
    sc = _sim_cfg(cfg)
    cfg.base_url = base_url  # point the (HTTP-only) client at the chosen target
    client = SearchClient(cfg)
    pairs = load_pairs()
    if not pairs:
        return {"error": f"no pairs found at {_DATA}", "n_pairs": 0,
                "recall": 0.0, "precision": 0.0, "f1": 0.0}

    rows: list[dict] = []
    for p in pairs:
        a, b = p["a"], p["b"]
        a_appno, b_appno = str(p["a_appno"]), str(p["b_appno"])
        label, axis = p.get("label", "curated"), p.get("axis", "")
        # Variant query: explicit `query`/`query_b` override the mark's own name.
        qa = str(p.get("query", a))
        qb = str(p.get("query_b", b))
        d_ab = _probe_direction(client, qa, b_appno, sc)   # search A -> find B
        d_ba = _probe_direction(client, qb, a_appno, sc)   # search B -> find A
        for direction, d in (("a->b", d_ab), ("b->a", d_ba)):
            rec = {
                "case_id": f"SIM:{label}:{a_appno}|{b_appno}:{direction}",
                "group": "SIM", "label": label, "axis": axis, "direction": direction,
                "pair": f"{a!r}<->{b!r}", "query": d["query"], "target": d["target"],
                "status": "pass" if d["found"] else "fail",
                "severity": None if d["found"] else "S1",
                "found": d["found"], "rank": d["rank"], "returned": d["returned"],
                "precision": round(d["precision"], 3), "rel": d["rel"], "n_top": d["n_top"],
                "observed": f"found={d['found']} rank={d['rank']} prec={d['precision']:.2f}"
                + (f" err={d['error']}" if d["error"] else ""),
                "evidence": None,
            }
            store.append_case(rec)
            rows.append(rec)

    def agg(subset: list[dict]) -> dict:
        n = len(subset)
        if not n:
            return {"n": 0, "recall": 0.0, "precision": 0.0, "f1": 0.0}
        recall = sum(1 for r in subset if r["found"]) / n
        # precision averaged over directions that returned anything
        precs = [r["precision"] for r in subset if r["n_top"] > 0]
        precision = sum(precs) / len(precs) if precs else 0.0
        f1 = (2 * recall * precision / (recall + precision)) if (recall + precision) else 0.0
        return {"n": n, "recall": round(recall, 4), "precision": round(precision, 4),
                "f1": round(f1, 4)}

    overall = agg(rows)
    by_label = {lbl: agg([r for r in rows if r["label"] == lbl])
                for lbl in sorted(set(r["label"] for r in rows))}
    by_axis = {ax: agg([r for r in rows if r["axis"] == ax])
               for ax in sorted(set(r["axis"] for r in rows if r["axis"]))}
    report = {
        "base_url": base_url, "n_pairs": len(pairs), "n_directions": len(rows),
        "mode": sc["mode"], "recall_window": sc["recall_window"],
        "precision_top_n": sc["precision_top_n"],
        "recall": overall["recall"], "precision": overall["precision"], "f1": overall["f1"],
        "by_label": by_label, "by_axis": by_axis,
        "misses": [{"pair": r["pair"], "query": r["query"], "direction": r["direction"]}
                   for r in rows if not r["found"]],
    }
    (store.dir / "similarity_summary.json").write_text(json.dumps(report, indent=2, default=str))
    return report


def build_similarity_report(report: dict) -> str:
    if report.get("error"):
        return f"# Similarity suite — ERROR\n\n- {report['error']}\n"
    lines = [
        "# Tradenet Search — Confusable-Similarity Report (Precision / Recall / F1)",
        "",
        f"- Target: `{report['base_url']}`  ·  matcher: `{report['mode']}`  ·  "
        f"recall window: top-{report['recall_window']}  ·  precision: top-{report['precision_top_n']}",
        f"- Pairs: **{report['n_pairs']}** ({report['n_directions']} directional probes)",
        "",
        "## Headline (both directions per pair)",
        f"- **Recall = {report['recall']:.2%}**  ·  **Precision = {report['precision']:.2%}**  "
        f"·  **F1 = {report['f1']:.2%}**",
        "",
        "## By label (curated = trustworthy non-circular oracle)",
        "| label | n probes | recall | precision | F1 |",
        "|---|---|---|---|---|",
    ]
    for lbl, a in report["by_label"].items():
        lines.append(f"| {lbl} | {a['n']} | {a['recall']:.2%} | {a['precision']:.2%} | {a['f1']:.2%} |")
    if report["by_axis"]:
        lines += ["", "## By confusion axis", "| axis | n probes | recall | precision | F1 |",
                  "|---|---|---|---|---|"]
        for ax, a in report["by_axis"].items():
            lines.append(f"| {ax} | {a['n']} | {a['recall']:.2%} | {a['precision']:.2%} | {a['f1']:.2%} |")
    lines += ["", "## Recall misses (mate not surfaced)"]
    if report["misses"]:
        for m in report["misses"][:60]:
            lines.append(f"- {m['pair']} ({m['direction']}) — q=`{m['query']}`")
    else:
        lines.append("- none")
    lines += ["",
              "_Precision uses an INDEPENDENT string metric (difflib ratio + containment), not "
              "the API's own score, so phonetic-but-not-spelled-alike hits are counted "
              "conservatively — reported precision is a lower bound._", ""]
    return "\n".join(lines)
