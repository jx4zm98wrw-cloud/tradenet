"""`_queue_names` controls which RQ queues a worker drains (TM_WORKER_QUEUES).

Dedicated per-queue workers (one process per queue) are how Madrid and domestic
sweeps get isolated, parallel throughput; this helper is the per-process knob.
"""

import worker.run_worker as rw


def test_unset_falls_back_to_all_queues(monkeypatch):
    monkeypatch.delenv("TM_WORKER_QUEUES", raising=False)
    assert rw._queue_names() == ["ingest", "madrid", "domestic"]


def test_empty_falls_back_to_all_queues(monkeypatch):
    # os.environ.get returns "" (not the default) for an empty var — the helper
    # must still fall back so a blank env doesn't leave the worker idle.
    monkeypatch.setenv("TM_WORKER_QUEUES", "")
    assert rw._queue_names() == ["ingest", "madrid", "domestic"]


def test_single_dedicated_queue(monkeypatch):
    monkeypatch.setenv("TM_WORKER_QUEUES", "domestic")
    assert rw._queue_names() == ["domestic"]


def test_multiple_queues_with_whitespace(monkeypatch):
    monkeypatch.setenv("TM_WORKER_QUEUES", " madrid , domestic ")
    assert rw._queue_names() == ["madrid", "domestic"]


def test_blank_entries_dropped(monkeypatch):
    monkeypatch.setenv("TM_WORKER_QUEUES", "ingest,,domestic,")
    assert rw._queue_names() == ["ingest", "domestic"]


def test_resume_running_sweeps_invokes_handled_queue(monkeypatch):
    import worker.domestic_sweep as ds

    called = []
    monkeypatch.setattr(ds, "resume_if_running", lambda: called.append("domestic") or True)
    rw._resume_running_sweeps(["domestic"])
    assert called == ["domestic"]


def test_resume_running_sweeps_skips_unlisted_queue(monkeypatch):
    import worker.domestic_sweep as ds

    called = []
    monkeypatch.setattr(ds, "resume_if_running", lambda: called.append("domestic") or True)
    rw._resume_running_sweeps(["ingest"])  # this worker doesn't handle domestic
    assert called == []


def test_resume_running_sweeps_swallows_errors(monkeypatch):
    import worker.domestic_sweep as ds

    def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(ds, "resume_if_running", _boom)
    rw._resume_running_sweeps(["domestic"])  # best-effort: must not raise
