"""Live progress + metrics for the background media scan.

A single process-wide tracker, written by the scan thread and the loader's
worker pool and read by ``GET /api/system/scan``. It lives in its own module
(rather than inside ``api.system``) so ``loader`` can import it without the
api<->loader import cycle that already forces ``api.system`` to import the
loader lazily.

The per-file open timings are the point on a network mount: an SMB/NFS share
that has gone flaky shows up as a climbing p95 and a handful of pathological
"slowest files" long before the scan actually fails.
"""
import heapq
import threading
from datetime import datetime
from typing import List, Optional, Tuple

# How many of the slowest files to surface — enough to spot a bad folder or a
# struggling mount without unbounded memory on a huge library.
_SLOWEST_N = 10


class ScanProgress:
    """Thread-safe snapshot of the in-flight (or most recent) scan."""

    def __init__(self):
        self._lock = threading.Lock()
        self._init_state()

    def _init_state(self):
        self.running = False
        self.media_type: Optional[str] = None
        self.phase: Optional[str] = None
        self.total = 0
        self.processed = 0
        self.reconciled = 0
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.last_result: Optional[dict] = None
        # Per-file processing time in ms, plus a bounded min-heap of the slowest.
        self._durations: List[float] = []
        self._slowest: List[Tuple[float, str]] = []

    # -- lifecycle ----------------------------------------------------------

    def start(self, media_type: str):
        """Mark a scan as started, clearing the previous run's live counters."""
        with self._lock:
            self.running = True
            self.media_type = media_type
            self.phase = None
            self.total = 0
            self.processed = 0
            self.reconciled = 0
            self.started_at = datetime.now()
            self.finished_at = None
            self._durations = []
            self._slowest = []

    def set_phase(self, phase: str, total: int):
        with self._lock:
            self.phase = phase
            self.total = total
            self.processed = 0

    def advance(self, path: str, ms: float):
        """Record one processed file and its open/parse time in milliseconds."""
        with self._lock:
            self.processed += 1
            self._durations.append(ms)
            if len(self._slowest) < _SLOWEST_N:
                heapq.heappush(self._slowest, (ms, path))
            elif ms > self._slowest[0][0]:
                heapq.heapreplace(self._slowest, (ms, path))

    def add_reconciled(self, n: int):
        with self._lock:
            self.reconciled += n

    def finish(self, result: dict):
        with self._lock:
            self.running = False
            self.phase = None
            self.finished_at = datetime.now()
            self.last_result = result

    def reset(self):
        """Drop all state — used between tests."""
        with self._lock:
            self._init_state()

    # -- read ---------------------------------------------------------------

    def snapshot(self) -> dict:
        with self._lock:
            durations = sorted(self._durations)
            count = len(durations)
            avg_ms = sum(durations) / count if count else 0.0
            # Nearest-rank p95; index clamped so a tiny sample doesn't overflow.
            p95_ms = durations[min(count - 1, int(count * 0.95))] if count else 0.0
            slowest = [
                {"path": p, "ms": round(ms, 1)}
                for ms, p in sorted(self._slowest, reverse=True)
            ]
            duration_seconds = None
            if self.started_at is not None:
                end = self.finished_at or datetime.now()
                duration_seconds = round((end - self.started_at).total_seconds(), 1)
            return {
                "running": self.running,
                "media_type": self.media_type,
                "phase": self.phase,
                "total": self.total,
                "processed": self.processed,
                "reconciled": self.reconciled,
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None,
                "duration_seconds": duration_seconds,
                "timing": {
                    "count": count,
                    "avg_ms": round(avg_ms, 1),
                    "p95_ms": round(p95_ms, 1),
                    "slowest": slowest,
                },
                "last_result": self.last_result,
            }


# Process-wide singleton.
progress = ScanProgress()
