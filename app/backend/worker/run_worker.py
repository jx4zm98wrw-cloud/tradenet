"""RQ worker entry point — listens on the `ingest` and `madrid` queues."""

from __future__ import annotations

import logging
import os
import sys

from redis import Redis
from rq import Queue, Worker

from api.settings import get_settings


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
    queues = [Queue("ingest", connection=redis), Queue("madrid", connection=redis)]
    worker = Worker(queues, connection=redis)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
