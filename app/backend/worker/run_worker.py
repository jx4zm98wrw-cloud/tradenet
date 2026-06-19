"""RQ worker entry point.

By default a single worker drains all queues (`ingest`, `madrid`, `domestic`) —
convenient for dev, but the queues share one consumer, so jobs run serially in
queue-priority order. Set `TM_WORKER_QUEUES` (comma-separated) to dedicate a
worker to a subset, e.g. `TM_WORKER_QUEUES=domestic`. Running one worker per
queue (see the docker-compose `worker-*` services) gives each sweep its own
isolated, parallel throughput — a heavy Madrid run can no longer starve the
domestic sweep, and vice versa.
"""

from __future__ import annotations

import logging
import os
import sys

from redis import Redis
from rq import Queue, Worker

from api.settings import get_settings

_DEFAULT_QUEUES = "ingest,madrid,domestic"


def _queue_names() -> list[str]:
    """Queues this worker drains, from `TM_WORKER_QUEUES` (comma-separated).

    Unset OR empty falls back to all queues, so the default single-worker setup
    is unchanged. Whitespace around names is trimmed; blank entries are dropped.
    """
    raw = os.environ.get("TM_WORKER_QUEUES") or _DEFAULT_QUEUES
    return [n.strip() for n in raw.split(",") if n.strip()]


def main() -> None:
    # macOS fork-after-Objective-C-init guard. pdfplumber pulls in libs that
    # touch the Objective-C runtime; once that happens the parent can't safely
    # fork a child without this flag, and RQ's work-horse model crashes with
    # SIGABRT during job pickup.
    if sys.platform == "darwin":
        os.environ.setdefault("OBJC_DISABLE_INITIALIZE_FORK_SAFETY", "YES")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    redis = Redis.from_url(settings.redis_url)
    names = _queue_names()
    logging.getLogger("worker").info("listening on queues: %s", ", ".join(names))
    queues = [Queue(n, connection=redis) for n in names]
    worker = Worker(queues, connection=redis)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
