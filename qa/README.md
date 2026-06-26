# Tradenet Search — Self-Running QA Suite (`tnqa`)

A **standalone, plug-in / plug-out** QA suite for the Tradenet trademark-search API.
It talks to the app **only over HTTP** (the public search endpoint) and to Postgres
**read-only** (for ground truth). It **never imports app code** and **never writes to
the app**. Delete the `qa/` directory and the app is byte-for-byte unchanged.

> Design + scope rationale: [`docs/qa/trademark-search-qa-plan-v2-tradenet.md`](../docs/qa/trademark-search-qa-plan-v2-tradenet.md).
> Text/data search only — **image search is out of scope**.

## Independence contract

- Own `pyproject.toml` + venv under `qa/`; imports only `tnqa.*` + third-party libs.
- Reads the app via `GET /api/v1/search/trademarks`; reads Postgres with a session
  pinned `default_transaction_read_only = on`.
- Writes **only** under `qa/results/run-<ts>/`. Touches no app file, runs no migration,
  trips no app CI (it lives outside `app/`).

## Setup

```bash
cd qa
python3 -m venv .venv && source .venv/bin/activate
pip install -e .                      # httpx, pyyaml, psycopg
cp .env.example .env                  # edit target URL / DB DSN / auth if needed
```

Point it at a target by editing `qa/.env`:
- `TNQA_BASE_URL` — the API base (local dev default `http://localhost:8000`).
- `TNQA_DB_DSN` — read-only Postgres DSN (dev default `…@localhost:5435/tm`).
- `TNQA_AUTH_TOKEN` — only if the search API requires auth in your env.

All thresholds, sampling params, the time budget, and the response schema mapping
live in [`config.yaml`](config.yaml) — not buried as magic numbers.

## Run model — two human gates, autonomous in between

```bash
python -m tnqa.run smoke     # GATE: 5-min self-check (connectivity, schema, gold-set,
                             #       write path, mode toggle, one real case/group)
python -m tnqa.run run       # autonomous: adaptive Wilson-CI sampling per group,
                             #   continuous checkpointing; finalizes report.md
python -m tnqa.run report    # (re)generate report.md from cases.jsonl any time
```

`run` re-runs the smoke gate first and **aborts if it's red** (never burns the budget
on a misconfigured target). Override the wall-clock budget with `--budget-s 600`.

## Adaptive sampling (no hard-coded n)

Each group's headline metric (recall / pass-rate) is treated as a binomial proportion
with a **Wilson** confidence interval. The sampler keeps drawing batches until the CI
half-width ≤ `sampling.margin` (default ±0.03 at 95%) **or** the per-group ceiling is
hit, with a floor so a group never stops too early. The RNG seed is fixed and recorded
in `state.json` for reproducibility. On a fast local API this **converges in minutes**,
not hours — the 4h budget is a *ceiling*, and the report flags converged vs capped.

## Continuous persistence & resume

Under `qa/results/run-<ts>/`:
- `cases.jsonl` — one JSON object per case, flushed + fsync'd immediately (zero loss).
- `state.json` — atomic (temp-file + rename) checkpoint after every batch.
- `evidence/<case-id>/<hash>.json` — raw response snapshots.
- `report.md` — regenerated as groups complete; final on exit.
- `progress.log` — per-batch heartbeat (group, n, CI, elapsed).

Resume an interrupted run: `python -m tnqa.run run --run-dir run-<ts>` — completed
case ids in `cases.jsonl` are skipped.

## Scope today vs extension

Groups **A–E** run against the unified free-text `q` box. The harness is data-driven:
each case is a small function over a sampled gold mark, so adding the remaining
Test-Plan cases is local. Wired headline cases per group:

- **A** exact-name recall (S1) + appno lookup + count integrity vs the DB.
- **B** phonetic/fuzzy recall on one-edit perturbations (the cardinal clearance metric).
- **C** diacritic-insensitive recall (phonetic).
- **D** injection-safety + idempotency/determinism.
- **E** exact-on-top ranking.

Severity follows the confirmed bar — Tradenet is a **professional clearance tool**, so a
**missed similar mark is S1**. Wildcard/Boolean are **exploratory** (S3 findings), not
S1, because `q` does not parse them today. Sidebar-facet coverage is a fast-follow
**group F** (not in the first run).
