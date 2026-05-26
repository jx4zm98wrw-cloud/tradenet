# claude_csvbuilder

Vietnamese trademark gazette workbench — parses NOIP (IP Vietnam) gazette PDFs
into structured CSV/database rows and serves them through a small web UI.

## What's in here

| Path | What it is |
|---|---|
| [`app/`](app/) | The web stack: FastAPI backend (`app/backend/`) + Next.js 15 frontend (`app/frontend/`) + dev `docker-compose.yml`. Start here for ongoing development. |
| [`app/backend/tm_extractor/`](app/backend/tm_extractor/) | The CSV parser, vendored as a Python package. Originally `TM_csv_builder.py`. |
| [`app/backend/image_extractor/`](app/backend/image_extractor/) | The logo / mark-specimen image extractor. Originally `Final_TRADEMARK_image_extractor_refine.py`. |
| [`TM_csv_builder.py`](TM_csv_builder.py) | Thin CLI shim that runs the parser without standing up the web stack — handy for "just give me CSVs." |
| `input/`, `csv/`, `image/`, `modified/`, `log/` | Runtime inputs and outputs (all gitignored; regenerable). |
| `cities_by_country.json`, `company_suffixes.json`, `cities_overrides.json`, `config_image_extractor.yaml` | Reference data + extractor config consumed at parse time. |

## Where to read next

- **Setting up the dev stack** — [`app/README.md`](app/README.md)
- **System architecture & design notes** — [`app/ARCHITECTURE.md`](app/ARCHITECTURE.md)
- **Contributing** — [`app/CONTRIBUTING.md`](app/CONTRIBUTING.md)
- **Deployment** — [`app/DEPLOYMENT.md`](app/DEPLOYMENT.md)
- **Security policy** — [`app/SECURITY.md`](app/SECURITY.md)
- **Guidance for Claude Code (and a denser walkthrough of the parser internals)** — [`CLAUDE.md`](CLAUDE.md)

## Quick start (CSV-only, no DB or UI)

```bash
pip install pdfplumber pandas numpy colorama tqdm
python3 TM_csv_builder.py
# 1 = process all PDFs in input/, 2 = comma-separated indices
```

## Quick start (full stack)

See [`app/README.md`](app/README.md) for the multi-step setup (docker compose + venv + editable install + alembic + uvicorn + pnpm). Short version:

```bash
docker compose -f app/docker-compose.yml up -d           # postgres :5435, redis :6380
python3 -m venv app/.venv && source app/.venv/bin/activate
pip install -r app/backend/requirements-dev.txt && pip install -e app/backend
cd app/backend && alembic upgrade head && uvicorn api.main:app --reload --port 8000
# in another terminal:
cd app/frontend && pnpm install && pnpm dev              # frontend on :3000
```
