from unittest.mock import patch

from conftest import insert_video
from model import VideoEntity


# ---------------------------------------------------------------------------
# GET /api/videos
# ---------------------------------------------------------------------------

class TestGetAll:
    def test_empty(self, client):
        r = client.get("/api/videos")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_all(self, client, session):
        insert_video(session, 1, "a.mp4")
        insert_video(session, 2, "b.mp4")
        r = client.get("/api/videos")
        assert len(r.json()) == 2

    def test_top_limit(self, client, session):
        for i in range(5):
            insert_video(session, i + 1, f"{i}.mp4")
        r = client.get("/api/videos?top=3")
        assert len(r.json()) == 3


# ---------------------------------------------------------------------------
# GET /api/videos/{id}
# ---------------------------------------------------------------------------

class TestGet:
    def test_not_found(self, client):
        r = client.get("/api/videos/999")
        assert r.status_code == 404

    def test_found(self, client, session):
        insert_video(session, 1, "test.mp4")
        with patch("util.create_soft_link"):
            r = client.get("/api/videos/1")
        assert r.status_code == 200
        assert r.json()["name"] == "test.mp4"

    def test_creates_soft_link(self, client, session, tmp_path):
        insert_video(session, 5, path="/data/videos/test.mp4")
        with patch("util.create_soft_link") as mock_link:
            client.get("/api/videos/5")
        mock_link.assert_called_once()
        args = mock_link.call_args[0]
        assert args[0] == "/data/videos/test.mp4"
        assert "5" in args[1]


# ---------------------------------------------------------------------------
# DELETE /api/videos/{id}
# ---------------------------------------------------------------------------

class TestDelete:
    def test_not_found(self, client):
        r = client.delete("/api/videos/999")
        assert r.status_code == 404

    def test_archive_soft_delete(self, client, session, engine_and_client):
        engine, _ = engine_and_client
        insert_video(session, 1, path="/nonexistent/test.mp4")
        r = client.delete("/api/videos/1")
        assert r.status_code == 200
        from sqlmodel import Session as S
        with S(engine) as s:
            v = s.get(VideoEntity, 1)
            assert v is not None
            assert v.archived is True

    def test_permanent_removes_db_row(self, client, session, engine_and_client):
        engine, _ = engine_and_client
        insert_video(session, 1, path="/nonexistent/test.mp4")
        r = client.delete("/api/videos/1?permanent=true")
        assert r.status_code == 200
        from sqlmodel import Session as S
        with S(engine) as s:
            assert s.get(VideoEntity, 1) is None

    def test_permanent_removes_file(self, client, session, tmp_path):
        f = tmp_path / "vid.mp4"
        f.write_bytes(b"video data")
        insert_video(session, 1, path=str(f))
        client.delete("/api/videos/1?permanent=true")
        assert not f.exists()

    def test_missing_file_is_ok(self, client, session):
        insert_video(session, 1, path="/nonexistent/missing.mp4")
        r = client.delete("/api/videos/1?permanent=true")
        assert r.status_code == 200
