"""Single-lane queue for heavy background jobs (media scans, cover runs).

Both read every comic file and hammer the same disk; running them at once
only slows both down. Jobs run one at a time in submission order on a worker
thread. A job identical to one still waiting (same kind and parameters) isn't
added twice, so e.g. the daily scan can't pile up behind a long cover run.
The job that is running doesn't count: a scan requested mid-scan may see new
files and gets queued.

State is in memory only: the queue and the recent history are lost on
restart (the startup scan queues itself again anyway).

Queued jobs can be cancelled. A running one only if its kind registered a
cancel callback (cover runs stop between comics; scans can't stop midway).
"""
import itertools
import threading
from collections import deque
from datetime import datetime
from typing import Callable, Deque, Dict, Literal, Optional

State = Literal["queued", "running", "succeeded", "failed", "cancelled"]
HISTORY_SIZE = 20


class Job:
    def __init__(self, id: int, kind: str, params: Dict[str, str]):
        self.id = id
        self.kind = kind
        self.params = params
        self.state: State = "queued"
        self.created_at = datetime.now()
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.error: Optional[str] = None
        self.cancel_requested = False


class _Kind:
    def __init__(self, run: Callable[[Job], None], cancel: Optional[Callable[[], None]]):
        self.run = run
        self.cancel = cancel


class JobQueue:
    def __init__(self):
        self._lock = threading.Lock()
        self._kinds: Dict[str, _Kind] = {}
        self.reset()

    def reset(self):
        """Forget all jobs (tests). Doesn't stop a job that is running."""
        with self._lock:
            self._queue: Deque[Job] = deque()
            self._running: Optional[Job] = None
            self._history: Deque[Job] = deque(maxlen=HISTORY_SIZE)
            self._ids = itertools.count(1)
            self._worker_alive = False
            self._idle = threading.Event()
            self._idle.set()

    def register(self, kind: str, run: Callable[[Job], None], cancel: Optional[Callable[[], None]] = None):
        """``run(job)`` does the work and raises on failure; ``cancel()`` asks a running job to stop."""
        self._kinds[kind] = _Kind(run, cancel)

    def submit(self, kind: str, params: Optional[Dict[str, str]] = None) -> tuple[Job, str]:
        """Queue a job. Returns ``(job, "started" | "queued" | "already_queued")``."""
        params = params or {}
        if kind not in self._kinds:
            raise ValueError(f"Unknown job kind: {kind}")
        with self._lock:
            for waiting in self._queue:
                if waiting.kind == kind and waiting.params == params:
                    return waiting, "already_queued"
            job = Job(next(self._ids), kind, params)
            self._queue.append(job)
            starts_now = self._running is None and len(self._queue) == 1
            self._idle.clear()
            if not self._worker_alive:
                self._worker_alive = True
                _spawn(self._work)
        return job, "started" if starts_now else "queued"

    def cancel(self, id: int) -> Optional[str]:
        """Cancel a job: ``"cancelled"`` (was queued), ``"cancelling"`` (running,
        asked to stop), ``"not_cancellable"``, or None when there's no such job
        waiting or running."""
        with self._lock:
            for job in self._queue:
                if job.id == id:
                    self._queue.remove(job)
                    job.state = "cancelled"
                    job.finished_at = datetime.now()
                    self._history.appendleft(job)
                    return "cancelled"
            job = self._running
            if job is None or job.id != id:
                return None
            kind = self._kinds[job.kind]
            if kind.cancel is None:
                return "not_cancellable"
            job.cancel_requested = True
        kind.cancel()
        return "cancelling"

    def cancellable(self, job: Job) -> bool:
        return job.state == "queued" or (
            job.state == "running" and self._kinds[job.kind].cancel is not None and not job.cancel_requested
        )

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self._running,
                "queued": list(self._queue),
                "history": list(self._history),
            }

    def wait_idle(self, timeout: Optional[float] = None) -> bool:
        """Block until no job is running or queued (tests)."""
        return self._idle.wait(timeout)

    def _work(self):
        while True:
            with self._lock:
                if not self._queue:
                    self._running = None
                    self._worker_alive = False
                    self._idle.set()
                    return
                job = self._queue.popleft()
                job.state = "running"
                job.started_at = datetime.now()
                self._running = job
            try:
                self._kinds[job.kind].run(job)
                state: State = "cancelled" if job.cancel_requested else "succeeded"
            except Exception as e:
                job.error = str(e) or type(e).__name__
                state = "failed"
                print(f"[Jobs] {job.kind} {job.params} failed: {job.error}", flush=True)
            with self._lock:
                job.state = state
                job.finished_at = datetime.now()
                self._running = None
                self._history.appendleft(job)


def _spawn(target) -> None:
    threading.Thread(target=target, daemon=True).start()


# Process-wide singleton.
jobs = JobQueue()
