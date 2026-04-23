from unittest.mock import patch

import global_data
from conftest import MockComicfile, insert_comic, make_jpeg_bytes
from loader import ComicLoader
from tasks.cache import comic_access_cache


# ---------------------------------------------------------------------------
# GET /api/comics/{id}/{page}
# ---------------------------------------------------------------------------

class TestGetPage:
    def test_comic_not_found(self, client):
        r = client.get("/api/comics/999/1")
        assert r.status_code == 404

    def test_file_not_found(self, client, session):
        insert_comic(session, 1, page=3)
        with patch("comicfile.create_open", return_value=None):
            r = client.get("/api/comics/1/1")
        assert r.status_code == 404

    def test_page_out_of_range(self, client, session):
        insert_comic(session, 1, page=2)
        mock_cf = MockComicfile(pages=2)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/99")
        assert r.status_code == 404

    def test_success_returns_jpeg(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/1")
        assert r.status_code == 200
        assert "image/jpeg" in r.headers["content-type"]

    def test_success_records_access_cache(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            client.get("/api/comics/1/2")
        assert 1 in comic_access_cache
        _, page = comic_access_cache[1]
        assert page == 2

    def test_cache_control_header(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/1")
        assert "max-age=604800" in r.headers.get("cache-control", "")


# ---------------------------------------------------------------------------
# POST /api/comics/{id}/{page}/like
# ---------------------------------------------------------------------------

class TestLike:
    def test_comic_not_found(self, client):
        r = client.post("/api/comics/999/1/like")
        assert r.status_code == 404

    def test_file_not_found(self, client, session):
        insert_comic(session, 1, page=3)
        with patch("comicfile.create_open", return_value=None):
            r = client.post("/api/comics/1/1/like")
        assert r.status_code == 404

    def test_page_out_of_range(self, client, session):
        insert_comic(session, 1, page=2)
        mock_cf = MockComicfile(pages=2)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.post("/api/comics/1/99/like")
        assert r.status_code == 404

    def test_creates_image_file(self, client, session, tmp_path, monkeypatch):
        liked_dir = tmp_path / "liked"
        monkeypatch.setattr(global_data.Config.Image, "liked_path", str(liked_dir))
        insert_comic(session, 1, name="hero.zip", page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.post("/api/comics/1/2/like")
        assert r.status_code == 200
        assert r.json()["detail"] == "OK"
        assert (liked_dir / "hero.zip_2.jpg").exists()

    def test_already_liked_returns_ok(self, client, session, tmp_path, monkeypatch):
        liked_dir = tmp_path / "liked"
        liked_dir.mkdir()
        monkeypatch.setattr(global_data.Config.Image, "liked_path", str(liked_dir))
        insert_comic(session, 1, name="hero.zip", page=3)
        existing = liked_dir / "hero.zip_1.jpg"
        existing.write_bytes(make_jpeg_bytes())
        r = client.post("/api/comics/1/1/like")
        assert r.status_code == 200
        assert r.json()["detail"] == "OK"


# ---------------------------------------------------------------------------
# POST /api/comics/{id}/{page}/cover
# ---------------------------------------------------------------------------

class TestSetCover:
    def test_comic_not_found(self, client):
        r = client.post("/api/comics/999/1/cover")
        assert r.status_code == 404

    def test_file_not_found(self, client, session):
        insert_comic(session, 1, page=3)
        with patch("comicfile.create_open", return_value=None):
            r = client.post("/api/comics/1/1/cover")
        assert r.status_code == 404

    def test_success(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
                r = client.post("/api/comics/1/2/cover")
        assert r.status_code == 200

    def test_gen_cover_fails(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            with patch.object(ComicLoader, "gen_comic_cover", return_value=False):
                r = client.post("/api/comics/1/2/cover")
        assert r.status_code == 500

    def test_page_zero_uses_zero_index(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        captured = {}
        def fake_gen(comic, cf, overwrite, page):
            captured["page"] = page
            return True
        with patch("comicfile.create_open", return_value=mock_cf):
            with patch.object(ComicLoader, "gen_comic_cover", side_effect=fake_gen):
                client.post("/api/comics/1/0/cover")
        assert captured["page"] == 0
