"""Ordered orchestrator for the post-ingest backfills (audit D1).

The derivation layer is maintained by ~10 backfills that the ingest worker does
NOT run (they read enrichment / other backfilled columns), so after a fresh
ingest or an enrichment sweep an operator must re-run them — IN THE RIGHT ORDER.
Running them by hand is the D1 risk: one missed or mis-ordered run silently
degrades facets / overview / similarity / search with no alarm. This script is
the single ordered entrypoint.

Dependency edges enforced by the order below:
  * applicant_note  ->  entity_clean     (entity_clean reads the note-stripped
                                          applicant_name)
  * mark_name       ->  mark_embedding   (the embedding encodes mark_name)
  * vn_grant        ->  is_representative (vn_grant_date is a rep tiebreaker)
  * is_representative runs LAST — it is the dedup flag every read path consumes,
    so it must see the final certificate_number / vn_grant_date of every row.

Each stage is a separate module run as a subprocess (``python -m scripts.<name>``)
so it keeps its own engine / session / serializer (some are asyncpg, some
psycopg2) and its own stats output. The environment is inherited, so the same
``TM_DATABASE_URL`` / ``TM_DATABASE_URL_SYNC`` the individual scripts expect must
be exported before running this. Every stage is idempotent
(recompute-and-compare), so a re-run — or a resume after fixing a failure — is
safe.

Fail-fast: a non-zero exit from any stage stops the run and returns non-zero,
naming the failed stage. Stages run over the WHOLE corpus (idempotent); per-new-
gazette scoping is a future optimisation (the scripts already accept ``ids=`` at
the function level).

    python -m scripts.post_ingest_backfills            # run all, in order
    python -m scripts.post_ingest_backfills --list     # print the plan, run nothing
    python -m scripts.post_ingest_backfills --skip backfill_mark_embedding
    python -m scripts.post_ingest_backfills --only repair_nice_classes,backfill_is_representative
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stage:
    name: str  # module under scripts/ (also the CLI selector)
    why: str  # one-line ordering rationale
    args: list[str] = field(default_factory=list)  # extra CLI args (e.g. --apply)


# ORDER IS SIGNIFICANT — see module docstring for the dependency edges.
STAGES: list[Stage] = [
    Stage("repair_nice_classes", "independent; recompute nice_classes from nice_group_number"),
    Stage(
        "fill_registration_date_from_enrichment",
        "independent; fill missing B-file (151) from enrichment",
        ["--apply"],
    ),
    Stage("backfill_applicant_note", "strip registry notes; MUST precede entity_clean", ["--apply"]),
    Stage("backfill_entity_clean", "derive applicant/representative clean+norm from stripped names"),
    Stage("backfill_vn_grant", "resolve vn_grant_date; MUST precede is_representative"),
    Stage("backfill_mark_name", "resolve mark_name; MUST precede mark_embedding"),
    Stage("backfill_mark_embedding", "encode mark_name -> LaBSE embedding (heavy: torch)"),
    Stage("backfill_logo_phash", "independent; compute logo perceptual hash"),
    Stage("backfill_logo_kind", "independent; classify figurative vs wordmark"),
    Stage("backfill_is_representative", "LAST; the dedup flag every read path consumes"),
]


def _select(skip: set[str], only: set[str]) -> list[Stage]:
    stages = STAGES
    if only:
        stages = [s for s in stages if s.name in only]
    if skip:
        stages = [s for s in stages if s.name not in skip]
    return stages


def _print_plan(stages: list[Stage]) -> None:
    print("Post-ingest backfill plan (in order):")
    for i, s in enumerate(stages, 1):
        extra = f" {' '.join(s.args)}" if s.args else ""
        print(f"  {i:2d}. scripts.{s.name}{extra}  # {s.why}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the post-ingest backfills in dependency order.")
    ap.add_argument("--list", action="store_true", help="print the ordered plan and exit")
    ap.add_argument("--skip", default="", help="comma-separated stage names to skip")
    ap.add_argument("--only", default="", help="comma-separated stage names to run (subset)")
    args = ap.parse_args(argv)

    skip = {n.strip() for n in args.skip.split(",") if n.strip()}
    only = {n.strip() for n in args.only.split(",") if n.strip()}
    known = {s.name for s in STAGES}
    unknown = (skip | only) - known
    if unknown:
        print(f"ERROR: unknown stage name(s): {', '.join(sorted(unknown))}", file=sys.stderr)
        print(f"Known stages: {', '.join(s.name for s in STAGES)}", file=sys.stderr)
        return 2

    stages = _select(skip, only)
    _print_plan(stages)
    if args.list:
        return 0

    done: list[str] = []
    for i, s in enumerate(stages, 1):
        cmd = [sys.executable, "-m", f"scripts.{s.name}", *s.args]
        print(f"\n=== [{i}/{len(stages)}] {s.name} ===\n$ {' '.join(cmd)}", flush=True)
        result = subprocess.run(cmd, check=False)  # inherit env + stdio
        if result.returncode != 0:
            print(
                f"\nFAILED at stage {i}/{len(stages)}: {s.name} (exit {result.returncode}).",
                file=sys.stderr,
            )
            print(f"Completed before failure: {', '.join(done) or '(none)'}", file=sys.stderr)
            print("Fix the cause and re-run — all stages are idempotent.", file=sys.stderr)
            return 1
        done.append(s.name)

    print(f"\nDONE: ran {len(done)} stage(s) in order: {', '.join(done)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
