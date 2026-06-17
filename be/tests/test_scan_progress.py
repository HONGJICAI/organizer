from core.scan_progress import ScanProgress, _SLOWEST_N


def test_idle_snapshot_defaults():
    p = ScanProgress()
    snap = p.snapshot()
    assert snap["running"] is False
    assert snap["started_at"] is None
    assert snap["duration_seconds"] is None
    assert snap["timing"] == {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "slowest": []}


def test_start_sets_running_and_clears_counters():
    p = ScanProgress()
    p.advance("/old.zip", 10)  # stale data from a prior run
    p.start("comics")
    snap = p.snapshot()
    assert snap["running"] is True
    assert snap["media_type"] == "comics"
    assert snap["processed"] == 0
    assert snap["timing"]["count"] == 0
    # A running scan reports elapsed time even before it finishes.
    assert snap["duration_seconds"] is not None


def test_advance_tracks_avg_and_p95():
    p = ScanProgress()
    p.start("comics")
    p.set_phase("comics", 100)
    for ms in range(1, 101):  # 1..100 ms
        p.advance(f"/f{ms}.zip", float(ms))
    snap = p.snapshot()
    assert snap["processed"] == 100
    assert snap["timing"]["count"] == 100
    assert snap["timing"]["avg_ms"] == 50.5
    # Nearest-rank p95 of 1..100 -> index int(100*0.95)=95 -> value 96.
    assert snap["timing"]["p95_ms"] == 96.0


def test_slowest_is_bounded_and_sorted():
    p = ScanProgress()
    p.start("comics")
    for ms in range(1, 51):
        p.advance(f"/f{ms}.zip", float(ms))
    slowest = p.snapshot()["timing"]["slowest"]
    assert len(slowest) == _SLOWEST_N
    # Descending by ms, capturing only the worst offenders.
    assert slowest[0] == {"path": "/f50.zip", "ms": 50.0}
    assert [s["ms"] for s in slowest] == sorted(
        (s["ms"] for s in slowest), reverse=True
    )


def test_finish_freezes_result_and_duration():
    p = ScanProgress()
    p.start("all")
    p.advance("/a.zip", 5)
    p.finish({"status": "success", "comics": "done"})
    snap = p.snapshot()
    assert snap["running"] is False
    assert snap["phase"] is None
    assert snap["finished_at"] is not None
    assert snap["last_result"] == {"status": "success", "comics": "done"}
    # Duration is frozen at finish time, not recomputed against now().
    first = snap["duration_seconds"]
    assert first == p.snapshot()["duration_seconds"]


def test_add_reconciled_accumulates():
    p = ScanProgress()
    p.start("comics")
    p.add_reconciled(3)
    p.add_reconciled(2)
    assert p.snapshot()["reconciled"] == 5


def test_reset_clears_everything():
    p = ScanProgress()
    p.start("comics")
    p.advance("/a.zip", 9)
    p.finish({"status": "success"})
    p.reset()
    snap = p.snapshot()
    assert snap["last_result"] is None
    assert snap["timing"]["count"] == 0
    assert snap["started_at"] is None
