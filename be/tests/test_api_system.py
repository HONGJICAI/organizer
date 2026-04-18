import time
from unittest.mock import patch

from tasks.cache import comic_access_cache


class TestHealth:
    def test_status_ok(self, client):
        r = client.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_cache_size_empty(self, client):
        r = client.get("/api/health")
        assert r.json()["cache_size"] == 0

    def test_cache_size_with_entries(self, client):
        from datetime import datetime
        comic_access_cache[1] = (datetime.now(), 5)
        comic_access_cache[2] = (datetime.now(), 3)
        r = client.get("/api/health")
        assert r.json()["cache_size"] == 2

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
