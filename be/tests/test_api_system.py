import asyncio
import datetime
from unittest.mock import patch


class TestHealth:
    def test_status_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_message_present(self, client):
        r = client.get("/api/health")
        assert "message" in r.json()


def wait_for_running(client, timeout=5.0):
    """POST returns before the worker picks the job up; wait for that."""
    import time
    deadline = time.time() + timeout
    while client.get("/api/system/jobs").json()["running"] is None:
        assert time.time() < deadline, "job never started"
        time.sleep(0.005)


class TestScan:
    def _reset(self):
        from core.scan_progress import progress
        progress.reset()

    def _wait(self, timeout=5.0):
        """Wait until the queued scan has run."""
        from core.jobs import jobs
        assert jobs.wait_idle(timeout)

    def test_starts_scan(self, client):
        self._reset()
        with patch("loader.ComicLoader.work"), patch("loader.VideoLoader.work"):
            r = client.post("/api/system/scan")
            self._wait()
        assert r.status_code == 200
        assert r.json()["status"] == "started"

    def test_default_media_type_is_all(self, client):
        self._reset()
        with patch("loader.ComicLoader.work") as mock_comic, \
             patch("loader.VideoLoader.work") as mock_video:
            client.post("/api/system/scan")
            self._wait()
            mock_comic.assert_called_once()
            mock_video.assert_called_once()

    def test_comics_only(self, client):
        self._reset()
        with patch("loader.ComicLoader.work") as mock_comic, \
             patch("loader.VideoLoader.work") as mock_video:
            client.post("/api/system/scan?media_type=comics")
            self._wait()
            mock_comic.assert_called_once()
            mock_video.assert_not_called()

    def test_videos_only(self, client):
        self._reset()
        with patch("loader.ComicLoader.work") as mock_comic, \
             patch("loader.VideoLoader.work") as mock_video:
            client.post("/api/system/scan?media_type=videos")
            self._wait()
            mock_comic.assert_not_called()
            mock_video.assert_called_once()

    def test_queues_behind_running_job_and_dedupes(self, client):
        import threading
        self._reset()
        release = threading.Event()
        with patch("loader.ComicLoader.work", side_effect=lambda: release.wait(5)), \
             patch("loader.VideoLoader.work"):
            assert client.post("/api/system/scan?media_type=comics").json()["status"] == "started"
            wait_for_running(client)
            # The running scan doesn't count for dedupe; a waiting one does.
            assert client.post("/api/system/scan?media_type=comics").json()["status"] == "queued"
            r = client.post("/api/system/scan?media_type=comics").json()
            assert r["status"] == "already_queued"
            assert r["message"] == "Scan (comics) is already waiting in the queue"
            release.set()
            self._wait()

    def test_status_idle(self, client):
        self._reset()
        r = client.get("/api/system/scan")
        assert r.status_code == 200
        assert r.json()["running"] is False
        assert r.json()["last_result"] is None

    def test_status_lists_skipped_files(self, client):
        from core.scan_progress import progress
        self._reset()
        progress.start("comics")
        progress.add_skipped("/data/comics/bad.zip", "File is not a zip file")
        body = client.get("/api/system/scan").json()
        assert body["skipped_count"] == 1
        assert body["skipped"] == [{"path": "/data/comics/bad.zip", "reason": "File is not a zip file"}]
        self._reset()

    def test_status_after_scan(self, client):
        self._reset()
        with patch("loader.ComicLoader.work"), patch("loader.VideoLoader.work"):
            client.post("/api/system/scan")
            self._wait()
        r = client.get("/api/system/scan")
        assert r.json()["running"] is False
        assert r.json()["last_result"]["status"] == "success"

    def test_status_records_error(self, client):
        self._reset()
        with patch("loader.ComicLoader.work", side_effect=RuntimeError("disk error")), \
             patch("loader.VideoLoader.work"):
            client.post("/api/system/scan")
            self._wait()
        r = client.get("/api/system/scan")
        assert r.json()["last_result"]["status"] == "error"
        assert "disk error" in r.json()["last_result"]["message"]

    def test_status_exposes_progress_shape(self, client):
        self._reset()
        r = client.get("/api/system/scan")
        body = r.json()
        # The enriched status always carries the progress/metrics shape, even
        # when idle, so the admin panel can render without null-guarding.
        assert body["processed"] == 0
        assert body["total"] == 0
        assert body["reconciled"] == 0
        assert body["timing"] == {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "slowest": []}

    def test_status_after_scan_has_timing_and_duration(self, client):
        self._reset()
        from core.scan_progress import progress

        def fake_work(self):
            progress.set_phase(self.phase, 1)
            progress.add_reconciled(2)
            progress.advance("/lib/slow.zip", 123.4)

        with patch("loader.ComicLoader.work", fake_work), \
             patch("loader.VideoLoader.work", lambda self: None):
            client.post("/api/system/scan")
            self._wait()
        body = client.get("/api/system/scan").json()
        assert body["running"] is False
        assert body["processed"] == 1
        assert body["reconciled"] == 2
        assert body["duration_seconds"] is not None
        assert body["timing"]["count"] == 1
        assert body["timing"]["slowest"][0]["path"] == "/lib/slow.zip"


class TestTasksStatus:
    def test_reports_next_scan_and_no_backups(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = client.get("/api/system/tasks")
        assert r.status_code == 200
        body = r.json()
        assert body["daily_scan"]["scan_hour"] == 2
        assert body["daily_scan"]["next_run"]  # ISO timestamp present
        assert body["backup"]["backup_count"] == 0
        assert body["backup"]["last_backup"] is None

    def test_reports_existing_backups(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()
        (backup_dir / "prod_20260101_000000.sqlite").write_bytes(b"a")
        (backup_dir / "prod_20260102_000000.sqlite").write_bytes(b"b")
        r = client.get("/api/system/tasks")
        body = r.json()
        assert body["backup"]["backup_count"] == 2
        assert body["backup"]["last_backup"] is not None


class TestSecondsUntil:
    def test_later_today(self):
        from tasks.scan import _seconds_until
        now = datetime.datetime(2026, 6, 15, 1, 0, 0)  # 01:00, target 02:00
        assert _seconds_until(2, now) == 3600

    def test_wraps_to_tomorrow(self):
        from tasks.scan import _seconds_until
        now = datetime.datetime(2026, 6, 15, 3, 0, 0)  # past 02:00 → next day
        assert _seconds_until(2, now) == 23 * 3600

    def test_exactly_on_hour_wraps(self):
        from tasks.scan import _seconds_until
        now = datetime.datetime(2026, 6, 15, 2, 0, 0)  # exactly 02:00 → next day
        assert _seconds_until(2, now) == 24 * 3600

    def test_defaults_to_now(self):
        from tasks.scan import _seconds_until
        assert 0 < _seconds_until(2) <= 24 * 3600


class TestDailyScanLoop:
    def _reset(self):
        from core.scan_progress import progress
        progress.reset()

    def test_triggers_scan_then_cancels(self):
        self._reset()
        from tasks import scan

        started = []
        with patch("api.system.start_scan", side_effect=lambda mt: started.append(mt) or "started"), \
             patch("tasks.scan._seconds_until", return_value=0):
            async def run():
                task = asyncio.create_task(scan.daily_scan_loop())
                await asyncio.sleep(0.05)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            asyncio.run(run())

        assert started and started[0] == "all"

    def test_already_queued(self):
        self._reset()
        from tasks import scan

        with patch("api.system.start_scan", return_value="already_queued") as mock_start, \
             patch("tasks.scan._seconds_until", return_value=0):
            async def run():
                task = asyncio.create_task(scan.daily_scan_loop())
                await asyncio.sleep(0.05)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            asyncio.run(run())

        assert mock_start.called


class TestBackupNow:
    def test_backup_now_success(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "prod.sqlite").write_bytes(b"fake database")
        r = client.post("/api/debug/backup-now")
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_backup_now_no_db(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        r = client.post("/api/debug/backup-now")
        assert r.status_code == 200
        assert r.json()["status"] == "success"

    def test_backup_now_error_path(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        with patch("api.system.backup_database", side_effect=RuntimeError("disk full")):
            r = client.post("/api/debug/backup-now")
        assert r.json()["status"] == "error"


class TestJobs:
    def test_empty(self, client):
        assert client.get("/api/system/jobs").json() == {"running": None, "queued": [], "history": []}

    def test_cancel_unknown_job(self, client):
        assert client.delete("/api/system/jobs/999").status_code == 404

    def test_running_scan_cannot_be_cancelled_but_queued_one_can(self, client):
        import threading
        from core.jobs import jobs
        release = threading.Event()
        with patch("loader.ComicLoader.work", side_effect=lambda: release.wait(5)), \
             patch("loader.VideoLoader.work"):
            client.post("/api/system/scan?media_type=comics")
            wait_for_running(client)
            client.post("/api/system/covers?mode=missing")
            body = client.get("/api/system/jobs").json()
            running, [queued] = body["running"], body["queued"]
            assert (running["kind"], running["params"], running["cancellable"]) == (
                "scan", {"media_type": "comics"}, False,
            )
            assert (queued["kind"], queued["params"], queued["state"], queued["cancellable"]) == (
                "covers", {"mode": "missing"}, "queued", True,
            )
            assert client.delete(f"/api/system/jobs/{running['id']}").status_code == 400
            assert client.delete(f"/api/system/jobs/{queued['id']}").json() == {"status": "cancelled"}
            release.set()
            assert jobs.wait_idle(5)
        history = client.get("/api/system/jobs").json()["history"]
        assert [(j["kind"], j["state"]) for j in history] == [("scan", "succeeded"), ("covers", "cancelled")]

    def test_failed_scan_marks_job_failed(self, client):
        from core.jobs import jobs
        with patch("loader.ComicLoader.work", side_effect=RuntimeError("disk error")), \
             patch("loader.VideoLoader.work"):
            client.post("/api/system/scan?media_type=comics")
            assert jobs.wait_idle(5)
        [job] = client.get("/api/system/jobs").json()["history"]
        assert (job["state"], job["error"]) == ("failed", "disk error")
