import asyncio
import datetime
import time
from unittest.mock import patch


class TestHealth:
    def test_status_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_message_present(self, client):
        r = client.get("/api/health")
        assert "message" in r.json()


class TestScan:
    def _reset(self):
        import api.system as m
        m._scan_status["running"] = False
        m._scan_status["last_result"] = None

    def _wait(self, timeout=5.0):
        """Poll until the background scan finishes."""
        import api.system as m
        deadline = time.time() + timeout
        while m._scan_status["running"] and time.time() < deadline:
            time.sleep(0.01)

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

    def test_rejects_concurrent_scan(self, client):
        self._reset()
        import api.system as m
        m._scan_status["running"] = True
        r = client.post("/api/system/scan")
        assert r.json()["status"] == "already_running"
        m._scan_status["running"] = False

    def test_status_idle(self, client):
        self._reset()
        r = client.get("/api/system/scan")
        assert r.status_code == 200
        assert r.json()["running"] is False
        assert r.json()["last_result"] is None

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
        import api.system as m
        m._scan_status["running"] = False
        m._scan_status["last_result"] = None

    def test_triggers_scan_then_cancels(self):
        self._reset()
        from tasks import scan

        started = []
        with patch("api.system.start_scan", side_effect=lambda mt: started.append(mt) or True), \
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

    def test_skips_when_already_running(self):
        self._reset()
        from tasks import scan

        with patch("api.system.start_scan", return_value=False) as mock_start, \
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
