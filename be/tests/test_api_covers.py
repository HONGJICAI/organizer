"""POST/GET /api/system/covers: background cover regeneration."""
import io
import os
import threading
import zipfile
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from PIL import Image

import covers
import global_data
from conftest import insert_comic, make_zip_comic
from test_api_system import wait_for_running
from core.jobs import jobs
from core.scan_progress import progress
from loader import ComicLoader
from model import ComicEntity


@pytest.fixture(autouse=True)
def reset_regen(client):
    progress.reset()
    covers.regen.reset()
    yield
    covers.regen.reset()


def cover_path(id: int) -> str:
    return os.path.join(global_data.Config.nginx_comic_path, f"{id}_0.jpg")


def write_stale_cover(id: int) -> None:
    Image.new("RGB", (5, 5), (255, 0, 0)).save(cover_path(id), "JPEG")


def colored_zip(path, colors) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for i, color in enumerate(colors):
            buf = io.BytesIO()
            Image.new("RGB", (10, 10), color).save(buf, "PNG")
            zf.writestr(f"{i:03d}.png", buf.getvalue())


def cover_color(id: int):
    return Image.open(cover_path(id)).convert("RGB").getpixel((0, 0))


def close(a, b, tol=12):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def regenerate(client, mode=None):
    """Queue a cover run, wait for the job queue to finish it, return both responses."""
    r = client.post("/api/system/covers" + (f"?mode={mode}" if mode else ""))
    assert r.status_code == 200
    assert jobs.wait_idle(10)
    return r.json(), client.get("/api/system/covers").json()


class TestRegenerate:
    def test_status_before_any_run(self, client):
        body = client.get("/api/system/covers").json()
        assert body == {
            "running": False, "cancelled": False, "mode": None, "total": 0, "processed": 0, "failed": 0,
            "failures": [], "started_at": None, "finished_at": None,
        }

    def test_rewrites_cover_and_bumps_version(self, client, session, tmp_path):
        f = tmp_path / "a.zip"
        colored_zip(f, [(0, 0, 255), (0, 255, 0)])
        old = datetime.now() - timedelta(days=1)
        insert_comic(session, id=1, path=str(f), page=2, entityUpdateTime=old)
        write_stale_cover(1)

        started, status = regenerate(client)
        assert started == {"status": "started", "message": "Cover regeneration started"}
        assert status["running"] is False
        assert status["mode"] == "all"
        assert (status["total"], status["processed"], status["failed"]) == (1, 1, 0)
        assert status["started_at"] and status["finished_at"]
        assert close(cover_color(1), (0, 0, 255))
        session.expire_all()
        assert session.get(ComicEntity, 1).entityUpdateTime > old

    def test_uses_custom_cover_page(self, client, session, tmp_path):
        f = tmp_path / "a.zip"
        colored_zip(f, [(0, 0, 255), (0, 255, 0)])
        insert_comic(session, id=1, path=str(f), page=2, coverPosition=2)
        regenerate(client)
        assert close(cover_color(1), (0, 255, 0))

    def test_custom_page_out_of_range_falls_back_to_first(self, client, session, tmp_path):
        f = tmp_path / "a.zip"
        colored_zip(f, [(0, 0, 255)])
        insert_comic(session, id=1, path=str(f), page=1, coverPosition=5)
        _, status = regenerate(client)
        assert status["failed"] == 0
        assert close(cover_color(1), (0, 0, 255))

    def test_missing_file_removes_stale_cover(self, client, session):
        old = datetime.now() - timedelta(days=1)
        insert_comic(session, id=1, name="gone.zip", path="/nonexistent/gone.zip", entityUpdateTime=old)
        write_stale_cover(1)
        _, status = regenerate(client)
        assert status["failed"] == 1
        assert status["failures"] == [
            {"id": 1, "name": "gone.zip", "reason": "Comic file not found or unsupported"}
        ]
        assert not os.path.exists(cover_path(1))
        session.expire_all()
        # Bumped on failure too, so browsers stop showing their cached stale cover.
        assert session.get(ComicEntity, 1).entityUpdateTime > old

    def test_unrenderable_pages_remove_stale_cover(self, client, session, tmp_path):
        f = tmp_path / "bad.zip"
        with zipfile.ZipFile(f, "w") as zf:
            zf.writestr("001.jpg", b"not an image")
        insert_comic(session, id=1, path=str(f), page=1)
        write_stale_cover(1)
        _, status = regenerate(client)
        assert status["failures"][0]["reason"] == "No page could be rendered as a cover"
        assert not os.path.exists(cover_path(1))

    def test_error_reason_reported(self, client, session, tmp_path):
        f = tmp_path / "a.zip"
        make_zip_comic(str(f))
        insert_comic(session, id=1, path=str(f))
        with patch.object(ComicLoader, "gen_comic_cover", side_effect=RuntimeError("boom")):
            _, status = regenerate(client)
        assert status["failures"][0]["reason"] == "boom"

    def test_failure_without_cover_file(self, client, session):
        insert_comic(session, id=1, path="/nonexistent/x.zip")
        _, status = regenerate(client)
        assert status["failed"] == 1

    def test_skips_archived_and_missing(self, client, session):
        insert_comic(session, id=1, path="/nonexistent/a.zip", archived=True)
        insert_comic(session, id=2, path="/nonexistent/b.zip", missing=True)
        write_stale_cover(1)
        _, status = regenerate(client)
        assert status["total"] == 0
        assert os.path.exists(cover_path(1))

    def test_failures_list_is_capped(self, client, session, monkeypatch):
        monkeypatch.setattr(covers, "MAX_FAILURES", 1)
        monkeypatch.setattr(covers, "_COMMIT_EVERY", 1)
        insert_comic(session, id=1, path="/nonexistent/a.zip")
        insert_comic(session, id=2, path="/nonexistent/b.zip")
        _, status = regenerate(client)
        assert status["failed"] == 2
        assert len(status["failures"]) == 1

    def test_queues_behind_a_scan(self, client, session, tmp_path):
        f = tmp_path / "a.zip"
        colored_zip(f, [(0, 0, 255)])
        insert_comic(session, id=1, path=str(f), page=1)
        release = threading.Event()
        order = []
        with patch("loader.ComicLoader.work", side_effect=lambda: order.append("scan") or release.wait(5)), \
                patch("loader.VideoLoader.work"):
            assert client.post("/api/system/scan?media_type=comics").json()["status"] == "started"
            wait_for_running(client)
            r = client.post("/api/system/covers").json()
            assert r == {"status": "queued", "message": "Cover regeneration queued behind the running job"}
            assert client.post("/api/system/covers").json()["status"] == "already_queued"
            # A full run waiting covers the missing-only one too.
            assert client.post("/api/system/covers?mode=missing").json()["status"] == "already_queued"
            # Nothing has touched covers while the scan holds the queue.
            assert covers.regen.started_at is None
            release.set()
            assert jobs.wait_idle(10)
        status = client.get("/api/system/covers").json()
        assert (status["processed"], status["failed"]) == (1, 0)
        kinds = [(j["kind"], j["state"]) for j in client.get("/api/system/jobs").json()["history"]]
        assert kinds == [("covers", "succeeded"), ("scan", "succeeded")]

    def test_cancel_running_run(self, client, session, tmp_path, monkeypatch):
        for id in range(1, 6):
            f = tmp_path / f"{id}.zip"
            colored_zip(f, [(0, 0, 255)])
            insert_comic(session, id=id, path=str(f), page=1)
        started = threading.Event()
        proceed = threading.Event()
        real = covers._regenerate

        def slow(comic):
            started.set()
            proceed.wait(5)
            return real(comic)

        monkeypatch.setattr(covers, "_regenerate", slow)
        job = client.post("/api/system/covers").json()
        assert job["status"] == "started"
        assert started.wait(5)
        [running] = [client.get("/api/system/jobs").json()["running"]]
        assert running["kind"] == "covers" and running["cancellable"] is True
        assert client.delete(f"/api/system/jobs/{running['id']}").json() == {"status": "cancelling"}
        proceed.set()
        assert jobs.wait_idle(10)
        status = client.get("/api/system/covers").json()
        assert status["cancelled"] is True
        assert status["processed"] < 5
        [last] = client.get("/api/system/jobs").json()["history"]
        assert last["state"] == "cancelled"

    def test_missing_mode_only_generates_absent_covers(self, client, session, tmp_path):
        for id in (1, 2):
            f = tmp_path / f"{id}.zip"
            colored_zip(f, [(0, 0, 255)])
            insert_comic(session, id=id, path=str(f), page=1)
        write_stale_cover(1)
        started, status = regenerate(client, "missing")
        assert started["message"] == "Missing cover generation started"
        assert (status["mode"], status["total"], status["failed"]) == ("missing", 1, 0)
        # The existing cover is left alone; only the absent one is generated.
        assert close(cover_color(1), (255, 0, 0))
        assert close(cover_color(2), (0, 0, 255))

    def test_refreshes_page_count(self, client, session, tmp_path):
        f = tmp_path / "a.zip"
        colored_zip(f, [(0, 0, 255), (0, 255, 0)])
        insert_comic(session, id=1, path=str(f), page=7)
        regenerate(client)
        session.expire_all()
        assert session.get(ComicEntity, 1).page == 2

    def test_page_count_kept_when_file_unreadable(self, client, session):
        insert_comic(session, id=1, path="/nonexistent/a.zip", page=7)
        regenerate(client)
        session.expire_all()
        assert session.get(ComicEntity, 1).page == 7

    def test_invalid_mode(self, client):
        assert client.post("/api/system/covers?mode=some").status_code == 400
