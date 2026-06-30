"""Tradenet Search — standalone self-running QA suite.

Plug-in/plug-out: talks to the app ONLY over HTTP (the public search API) and to
Postgres READ-ONLY for ground truth. It never imports api/worker/app code. Delete
the qa/ tree and the app is byte-for-byte unchanged.

Run model: `python -m tnqa smoke` (5-min self-check) → `python -m tnqa run`
(autonomous, adaptive-sampled, continuously checkpointed) → `python -m tnqa report`.
`run` auto-resumes from results/run-<ts>/state.json. See qa/README.md.
"""

from __future__ import annotations

import json
import math
import os
import pathlib
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone

try:  # PyYAML is a declared dep.
    import yaml
except Exception:  # pragma: no cover
    yaml = None

__version__ = "0.1.0"

QA_ROOT = pathlib.Path(__file__).resolve().parents[2]  # .../qa


# --------------------------------------------------------------------------- #
# Config + env
# --------------------------------------------------------------------------- #
def _load_dotenv(path: pathlib.Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@dataclass
class Config:
    raw: dict
    base_url: str
    auth_token: str
    db_dsn: str
    max_rps: float
    max_concurrency: int

    @property
    def schema(self) -> dict:
        return self.raw["schema"]

    @property
    def sampling(self) -> dict:
        return self.raw["sampling"]

    @property
    def thresholds(self) -> dict:
        return self.raw["thresholds"]

    @property
    def budget(self) -> dict:
        return self.raw["budget"]

    @property
    def claims(self) -> dict:
        return self.raw["claims"]


def load_config(config_path: pathlib.Path | None = None) -> Config:
    _load_dotenv(QA_ROOT / ".env")
    cfg_path = config_path or (QA_ROOT / "config.yaml")
    if yaml is None:
        raise RuntimeError("PyYAML is required: pip install -e qa/")
    raw = yaml.safe_load(cfg_path.read_text())
    return Config(
        raw=raw,
        base_url=os.environ.get("TNQA_BASE_URL", "http://localhost:8000").rstrip("/"),
        auth_token=os.environ.get("TNQA_AUTH_TOKEN", ""),
        db_dsn=os.environ.get("TNQA_DB_DSN", "postgresql://tm:tm@localhost:5435/tm"),
        max_rps=float(os.environ.get("TNQA_MAX_RPS", "5")),
        max_concurrency=int(os.environ.get("TNQA_MAX_CONCURRENCY", "8")),
    )


# --------------------------------------------------------------------------- #
# Search client — the single abstraction every case runs through
# --------------------------------------------------------------------------- #
@dataclass
class SearchResponse:
    status: int
    total: int
    items: list[dict]
    scores: list
    latency_s: float
    raw: dict | None
    error: str | None = None


class SearchClient:
    """GET /api/v1/search/trademarks via stdlib urllib (zero extra deps for the
    smoke path; swap in httpx for higher concurrency in a long run)."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.s = cfg.schema
        # The app rate-limits (HTTP 429). Honor it: retry with backoff (and the
        # server's Retry-After) rather than counting a throttle as a case failure.
        self.max_retries = int(os.environ.get("TNQA_MAX_RETRIES", "8"))

    def search(
        self,
        q: str | None,
        *,
        mode: str = "text",
        ranked: bool = True,
        threshold: float = 0.0,
        page: int = 0,
        limit: int = 50,
        extra: dict | None = None,
    ) -> SearchResponse:
        params = {
            self.s["mode_param"]: mode,
            self.s["sort_param"]: self.s["ranked_sort"] if ranked else self.s["plain_sort"],
            self.s["threshold_param"]: threshold,
            "limit": limit,
            "offset": page * limit,
        }
        if q is not None:
            params["q"] = q
        if extra:
            params.update(extra)
        url = f"{self.cfg.base_url}{self.s['search_path']}?{urllib.parse.urlencode(params)}"
        backoff = 0.5
        t0 = time.perf_counter()
        for attempt in range(self.max_retries):
            req = urllib.request.Request(url, headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = json.loads(resp.read().decode())
                    items = body.get(self.s["items"], [])
                    return SearchResponse(
                        status=resp.status,
                        total=int(body.get(self.s["total"], len(items))),
                        items=items,
                        scores=[it.get(self.s["score"]) for it in items],
                        latency_s=time.perf_counter() - t0,
                        raw=body,
                    )
            except urllib.error.HTTPError as e:
                # 429 (throttle) / 503 (transient) → wait per Retry-After or
                # exponential backoff, then retry. Other 4xx/5xx are real.
                if e.code in (429, 503) and attempt < self.max_retries - 1:
                    try:
                        wait = float(e.headers.get("Retry-After", "") or backoff)
                    except (TypeError, ValueError):
                        wait = backoff
                    time.sleep(min(wait, 30))
                    backoff *= 2
                    continue
                return SearchResponse(e.code, 0, [], [], time.perf_counter() - t0, None, f"HTTP {e.code}")
            except Exception as e:
                return SearchResponse(0, 0, [], [], time.perf_counter() - t0, None, repr(e))
        return SearchResponse(429, 0, [], [], time.perf_counter() - t0, None, "HTTP 429 (retries exhausted)")

    def _headers(self) -> dict:
        h = {"Accept": "application/json"}
        if self.cfg.auth_token:
            h["Authorization"] = f"Bearer {self.cfg.auth_token}"
        return h

    @staticmethod
    def _dig(item: dict, dotted: str):
        cur = item
        for part in dotted.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
        return cur

    def appno_of(self, item: dict) -> str | None:
        return self._dig(item, self.cfg.schema["application_number"])

    def appnos(self, items: list[dict]) -> list[str]:
        return [a for a in (self.appno_of(it) for it in items) if a]


# --------------------------------------------------------------------------- #
# Ground truth — READ-ONLY SQL against the same Postgres the API serves
# --------------------------------------------------------------------------- #
@dataclass
class GoldMark:
    application_number: str
    mark_name: str | None
    mark_sample: str | None
    madrid_number: str | None
    mark_category: str | None
    source: str          # domestic | madrid
    script: str          # latin | vn_diacritic | cjk | cyrillic
    length: str          # short | medium | long


_VN_DIACRITICS = set("ăâđêôơưĂÂĐÊÔƠƯàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ")


def _script_of(text: str | None) -> str:
    if not text:
        return "latin"
    if any("一" <= c <= "鿿" or "぀" <= c <= "ヿ" for c in text):
        return "cjk"
    if any("Ѐ" <= c <= "ӿ" for c in text):
        return "cyrillic"
    if any(c in _VN_DIACRITICS for c in text):
        return "vn_diacritic"
    return "latin"


def _length_of(text: str | None) -> str:
    n = len(text or "")
    return "short" if n <= 4 else "medium" if n <= 12 else "long"


class GroundTruth:
    """Builds the gold set and answers oracle questions from the DB directly.
    Never invents records: a missing answer ⇒ the case is marked blocked upstream."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        # Driver-agnostic: prefer psycopg (v3, the declared dep); fall back to
        # psycopg2 if that's what the host venv has. Both speak %s/%(name)s params.
        try:
            import psycopg

            self.conn = psycopg.connect(cfg.db_dsn, autocommit=True)
        except ModuleNotFoundError:
            import psycopg2

            self.conn = psycopg2.connect(cfg.db_dsn)
            self.conn.autocommit = True
        # Pin READ-ONLY so a bug here can never mutate the app's data.
        self._exec("SET default_transaction_read_only = on")

    def _exec(self, sql: str, params=None) -> list:
        """Run via a cursor (works for both psycopg v3 and psycopg2)."""
        cur = self.conn.cursor()
        cur.execute(sql, params or ())
        try:
            rows = cur.fetchall()
        except Exception:  # statements with no result set (e.g. SET)
            rows = []
        cur.close()
        return rows

    def sample_gold(self, n: int, rng: random.Random) -> list[GoldMark]:
        """Draw n real marks with a usable display name. Reproducible random order
        via a seeded md5 sort (fixed seed ⇒ same draw)."""
        seed = str(rng.random())
        rows = self._exec(
            """
            SELECT application_number, mark_name, mark_sample, madrid_number, mark_category
            FROM trademarks
            WHERE application_number IS NOT NULL
              AND coalesce(mark_name, mark_sample) IS NOT NULL
            ORDER BY md5(application_number || %s)
            LIMIT %s
            """,
            (seed, n),
        )
        out: list[GoldMark] = []
        for appno, name, sample, madrid, cat in rows:
            disp = name or sample
            out.append(
                GoldMark(
                    application_number=appno,
                    mark_name=name,
                    mark_sample=sample,
                    madrid_number=madrid,
                    mark_category=cat,
                    source="madrid" if (cat or "").startswith("madrid") else "domestic",
                    script=_script_of(disp),
                    length=_length_of(disp),
                )
            )
        return out

    def count_substring(self, q: str) -> int:
        """Oracle for A-07: rows whose mark name/sample/IDs contain q — mirrors
        build_trademark_where's q OR-group (mark-only + ID fields)."""
        like = f"%{q.lower()}%"
        rows = self._exec(
            """
            SELECT count(*) FROM trademarks WHERE
                lower(mark_sample) LIKE %(l)s OR lower(mark_name) LIKE %(l)s
                OR application_number ILIKE %(l)s OR certificate_number ILIKE %(l)s
                OR madrid_number ILIKE %(l)s
            """,
            {"l": like},
        )
        return int(rows[0][0])

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Statistics — Wilson score interval (binomial proportion)
# --------------------------------------------------------------------------- #
def wilson_half_width(passes: int, n: int, z: float) -> float:
    if n == 0:
        return 1.0
    p = passes / n
    denom = 1 + z * z / n
    margin = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return margin


def wilson_interval(passes: int, n: int, z: float) -> tuple[float, float, float]:
    if n == 0:
        return (0.0, 0.0, 1.0)
    p = passes / n
    hw = wilson_half_width(passes, n, z)
    return (p, max(0.0, p - hw), min(1.0, p + hw))


# --------------------------------------------------------------------------- #
# Persistence — append-only JSONL + atomic resumable state + evidence
# --------------------------------------------------------------------------- #
class RunStore:
    def __init__(self, run_dir: pathlib.Path):
        self.dir = run_dir
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "evidence").mkdir(exist_ok=True)
        self.cases_path = self.dir / "cases.jsonl"
        self.state_path = self.dir / "state.json"
        self.progress_path = self.dir / "progress.log"
        self._done_ids = self._load_done_ids()

    def _load_done_ids(self) -> set[str]:
        if not self.cases_path.exists():
            return set()
        ids = set()
        for line in self.cases_path.read_text().splitlines():
            try:
                ids.add(json.loads(line)["case_id"])
            except Exception:
                continue
        return ids

    def already_done(self, case_id: str) -> bool:
        return case_id in self._done_ids

    def append_case(self, result: dict) -> None:
        # Immediate flush + fsync — a kill loses zero cases.
        with self.cases_path.open("a") as f:
            f.write(json.dumps(result, default=str) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._done_ids.add(result["case_id"])

    def write_state(self, state: dict) -> None:
        tmp = self.state_path.with_suffix(".json.tmp")
        with tmp.open("w") as f:
            json.dump(state, f, indent=2, default=str)
            f.flush()
            os.fsync(f.fileno())
        tmp.replace(self.state_path)  # atomic rename

    def load_state(self) -> dict | None:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return None

    def evidence(self, case_id: str, query: str, raw: dict | None) -> str:
        h = str(abs(hash(query)) % (10**10))
        d = self.dir / "evidence" / case_id
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{h}.json"
        p.write_text(json.dumps(raw, default=str, indent=2) if raw is not None else "null")
        return str(p.relative_to(self.dir))

    def heartbeat(self, line: str) -> None:
        with self.progress_path.open("a") as f:
            f.write(line + "\n")
        print(line)

    def cases(self) -> list[dict]:
        if not self.cases_path.exists():
            return []
        return [json.loads(x) for x in self.cases_path.read_text().splitlines() if x.strip()]


# --------------------------------------------------------------------------- #
# Case result record
# --------------------------------------------------------------------------- #
@dataclass
class CaseResult:
    case_id: str
    group: str
    name: str
    status: str           # pass | fail | blocked | error
    severity: str | None  # S1..S4 when fail
    query: str
    expected: str
    observed: str
    latency_s: float
    stratum: dict
    evidence: str | None
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Group runners, orchestrator, report, smoke gate, and CLI live in tnqa/run.py to
# keep this file focused on reusable harness primitives.
from .run import main  # noqa: E402  re-export the CLI entry point

__all__ = [
    "Config", "load_config", "SearchClient", "SearchResponse", "GroundTruth",
    "GoldMark", "RunStore", "CaseResult", "wilson_interval", "wilson_half_width",
    "main", "QA_ROOT", "__version__",
]
