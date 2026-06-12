from unittest.mock import patch

import global_data
from conftest import MockComicfile, insert_comic, make_jpeg_bytes
from loader import ComicLoader
from model import ComicEntity


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

    def test_get_does_not_record_progress(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            client.get("/api/comics/1/2")
        session.expire_all()
        comic = session.get(ComicEntity, 1)
        assert comic.lastViewedPosition == 0
        assert comic.lastViewedTime is None

    def test_cache_control_header(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/1")
        assert "max-age=604800" in r.headers.get("cache-control", "")

    def test_content_type_from_extension(self, client, session):
        insert_comic(session, 1, page=2)
        mock_cf = MockComicfile(pages=2, names=["0000.png", "0001.webp"])
        with patch("comicfile.create_open", return_value=mock_cf):
            r1 = client.get("/api/comics/1/1")
            r2 = client.get("/api/comics/1/2")
        assert r1.headers["content-type"] == "image/png"
        assert r2.headers["content-type"] == "image/webp"

    def test_etag_present(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/1")
        assert r.headers.get("etag")

    def test_if_none_match_returns_304(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r1 = client.get("/api/comics/1/1")
            etag = r1.headers["etag"]
            r2 = client.get("/api/comics/1/1", headers={"if-none-match": etag})
        assert r2.status_code == 304
        assert r2.content == b""
        assert r2.headers["etag"] == etag

    def test_etag_differs_per_page_and_width(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            etags = {
                client.get("/api/comics/1/1").headers["etag"],
                client.get("/api/comics/1/2").headers["etag"],
                client.get("/api/comics/1/1?width=5").headers["etag"],
            }
        assert len(etags) == 3

    def test_width_downscales_image(self, client, session):
        import io
        from PIL import Image
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)  # pages are 10x10 JPEGs
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/1?width=5")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/webp"
        img = Image.open(io.BytesIO(r.content))
        assert img.width == 5

    def test_width_larger_than_image_returns_original(self, client, session):
        import io
        from PIL import Image
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/1?width=100")
        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.content))
        assert img.width == 10


# ---------------------------------------------------------------------------
# PUT /api/comics/{id}/progress
# ---------------------------------------------------------------------------

class TestUpdateProgress:
    def test_comic_not_found(self, client):
        r = client.put("/api/comics/999/progress", json={"position": 1})
        assert r.status_code == 404

    def test_success(self, client, session):
        insert_comic(session, 1, page=3)
        r = client.put("/api/comics/1/progress", json={"position": 2})
        assert r.status_code == 200
        assert r.json()["position"] == 2
        session.expire_all()
        comic = session.get(ComicEntity, 1)
        assert comic.lastViewedPosition == 2
        assert comic.lastViewedTime is not None

    def test_position_zero_rejected(self, client, session):
        insert_comic(session, 1, page=3)
        r = client.put("/api/comics/1/progress", json={"position": 0})
        assert r.status_code == 400

    def test_position_beyond_last_page_rejected(self, client, session):
        insert_comic(session, 1, page=3)
        r = client.put("/api/comics/1/progress", json={"position": 4})
        assert r.status_code == 400


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
