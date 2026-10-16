"""core.jobs: the single-lane heavy-job queue."""
import threading

import pytest

import core.jobs as jobs_mod
from core.jobs import JobQueue


@pytest.fixture
def queue():
    q = JobQueue()
    yield q
    assert q.wait_idle(5)


def wait_running(job, timeout=5.0):
    """submit() returns before the worker picks the job up; wait for that."""
    import time
    deadline = time.time() + timeout
    while job.state != "running":
        assert time.time() < deadline, "job never started"
        time.sleep(0.001)


def blocking_kind(q, kind="slow", cancel=None):
    """Register a kind whose jobs block until released; returns (release, ran)."""
    release = threading.Event()
    ran = []

    def run(job):
        ran.append(job.params)
        assert release.wait(5)

    q.register(kind, run, cancel)
    return release, ran


def test_runs_jobs_one_at_a_time_in_order(queue):
    release, ran = blocking_kind(queue)
    first, status = queue.submit("slow", {"n": "1"})
    assert status == "started"
    wait_running(first)
    assert queue.submit("slow", {"n": "2"})[1] == "queued"
    assert queue.submit("slow", {"n": "3"})[1] == "queued"
    snap = queue.snapshot()
    assert [j.params["n"] for j in snap["queued"]] == ["2", "3"]
    release.set()
    assert queue.wait_idle(5)
    assert ran == [{"n": "1"}, {"n": "2"}, {"n": "3"}]
    assert [j.state for j in queue.snapshot()["history"]] == ["succeeded"] * 3


def test_dedupes_only_waiting_jobs(queue):
    release, ran = blocking_kind(queue)
    first, status = queue.submit("slow", {"n": "1"})
    assert status == "started"
    wait_running(first)
    # The same job while it runs is queued: new work may have appeared.
    second, status = queue.submit("slow", {"n": "1"})
    assert status == "queued"
    again, status = queue.submit("slow", {"n": "1"})
    assert (again, status) == (second, "already_queued")
    release.set()
    assert queue.wait_idle(5)
    assert len(ran) == 2


def test_failed_job_records_error_and_queue_continues(queue):
    queue.register("boom", lambda job: (_ for _ in ()).throw(RuntimeError("disk gone")))
    queue.register("ok", lambda job: None)
    queue.submit("boom")
    queue.submit("ok")
    assert queue.wait_idle(5)
    history = queue.snapshot()["history"]
    assert [(j.kind, j.state, j.error) for j in history] == [
        ("ok", "succeeded", None),
        ("boom", "failed", "disk gone"),
    ]


def test_cancel_queued_job(queue):
    release, ran = blocking_kind(queue)
    wait_running(queue.submit("slow", {"n": "1"})[0])
    waiting, _ = queue.submit("slow", {"n": "2"})
    assert queue.cancellable(waiting)
    assert queue.cancel(waiting.id) == "cancelled"
    release.set()
    assert queue.wait_idle(5)
    assert ran == [{"n": "1"}]
    assert waiting.state == "cancelled"


def test_running_job_without_cancel_is_not_cancellable(queue):
    release, _ = blocking_kind(queue)
    job, _ = queue.submit("slow")
    wait_running(job)
    assert not queue.cancellable(job)
    assert queue.cancel(job.id) == "not_cancellable"
    release.set()


def test_cancel_running_job_with_callback(queue):
    stop = threading.Event()
    queue.register("stoppable", lambda job: stop.wait(5), cancel=stop.set)
    job, _ = queue.submit("stoppable")
    wait_running(job)
    assert queue.cancellable(job)
    assert queue.cancel(job.id) == "cancelling"
    assert not queue.cancellable(job)
    assert queue.wait_idle(5)
    assert job.state == "cancelled"


def test_cancel_unknown_job(queue):
    assert queue.cancel(42) is None


def test_unknown_kind_rejected(queue):
    with pytest.raises(ValueError):
        queue.submit("nope")


def test_history_is_capped(queue, monkeypatch):
    monkeypatch.setattr(jobs_mod, "HISTORY_SIZE", 3)
    q = JobQueue()
    q.register("ok", lambda job: None)
    for i in range(5):
        q.submit("ok", {"n": str(i)})
        assert q.wait_idle(5)
    assert [j.params["n"] for j in q.snapshot()["history"]] == ["4", "3", "2"]
