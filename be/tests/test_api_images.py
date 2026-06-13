"""Tests for in-memory image API"""
import pytest
from datetime import datetime
from conftest import make_jpeg_bytes
import api.images as img_api
from model import ImageEntity


def make_entity(id=1, name="album", path="/nonexistent/album", page=3, **kwargs) -> ImageEntity:
    return ImageEntity(id=id, name=name, path=path, size=1000, updateTime=datetime.now(), page=page, **kwargs)


@pytest.fixture(autouse=True)
def clear_store():
    img_api._store.clear()
    yield
    img_api._store.clear()


def set_store(*entities: ImageEntity):
    img_api._store.clear()
    img_api._store.update({e.id: e for e in entities})


@pytest.fixture
def scan_env(tmp_path, monkeypatch):
    """Fixture providing separate scan_path and nginx_path under tmp_path."""
    import global_data
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()
    nginx_dir = tmp_path / "nginx"
    nginx_dir.mkdir()
    monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(scan_dir)])
    monkeypatch.setattr(global_data.Config, "nginx_image_path", str(nginx_dir))
    return scan_dir


class TestBootstrap:
    def test_loads_folders_with_images(self, scan_env):
        for name in ["album1", "album2"]:
            d = scan_env / name
            d.mkdir()
            (d / "a.jpg").write_bytes(make_jpeg_bytes())
        img_api.bootstrap()
        assert len(img_api._store) == 2

    def test_assigns_integer_ids(self, scan_env):
        d = scan_env / "album"
        d.mkdir()
        (d / "a.jpg").write_bytes(make_jpeg_bytes())
        img_api.bootstrap()
        assert list(img_api._store.keys()) == [1]
        assert isinstance(img_api._store[1].id, int)

    def test_empty_folders_excluded(self, scan_env):
        (scan_env / "empty").mkdir()
        d = scan_env / "has_images"
        d.mkdir()
        (d / "a.jpg").write_bytes(make_jpeg_bytes())
        img_api.bootstrap()
        assert len(img_api._store) == 1

    def test_nonexistent_scan_path_skipped(self, monkeypatch):
        import global_data
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", ["/nonexistent/xyz"])
        img_api.bootstrap()
        assert len(img_api._store) == 0

    def test_sets_page_count(self, scan_env):
        d = scan_env / "album"
        d.mkdir()
        for i in range(3):
            (d / f"{i}.jpg").write_bytes(make_jpeg_bytes())
        img_api.bootstrap()
        assert img_api._store[1].page == 3


class TestGetAll:
    def test_empty(self, client):
        r = client.get("/api/images")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_all(self, client):
        set_store(make_entity(id=1), make_entity(id=2, name="b"))
        r = client.get("/api/images")
        assert len(r.json()) == 2

    def test_sorted_by_update_time_desc(self, client):
        e1 = make_entity(id=1, name="old")
        e1.updateTime = datetime(2020, 1, 1)
        e2 = make_entity(id=2, name="new")
        e2.updateTime = datetime(2023, 1, 1)
        set_store(e1, e2)
        names = [e["name"] for e in client.get("/api/images").json()]
        assert names[0] == "new"

    def test_top_param(self, client):
        set_store(make_entity(id=1), make_entity(id=2, name="b"), make_entity(id=3, name="c"))
        r = client.get("/api/images?top=2")
        assert len(r.json()) == 2

    def test_id_is_integer(self, client):
        set_store(make_entity(id=7))
        assert client.get("/api/images").json()[0]["id"] == 7


class TestGet:
    def test_existing(self, client):
        set_store(make_entity(id=1, name="album", page=5))
        r = client.get("/api/images/1")
        assert r.status_code == 200
        assert r.json()["id"] == 1
        assert r.json()["page"] == 5

    def test_missing_returns_404(self, client):
        assert client.get("/api/images/999").status_code == 404


class TestGetPage:
    def test_valid_page(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())
        (d / "002.jpg").write_bytes(make_jpeg_bytes())
        set_store(make_entity(id=1, path=str(d), page=2))
        r = client.get("/api/images/1/1")
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("image/")

    def test_out_of_range_returns_404(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())
        set_store(make_entity(id=1, path=str(d), page=1))
        assert client.get("/api/images/1/99").status_code == 404

    def test_negative_page_returns_404(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())
        (d / "002.jpg").write_bytes(make_jpeg_bytes())
        set_store(make_entity(id=1, path=str(d), page=2))
        assert client.get("/api/images/1/-1").status_code == 404

    def test_get_does_not_record_progress(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())
        set_store(make_entity(id=1, path=str(d), page=1))
        client.get("/api/images/1/1")
        assert img_api._store[1].lastViewedPosition == 0
        assert img_api._store[1].lastViewedTime is None

    def test_if_none_match_returns_304(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())
        set_store(make_entity(id=1, path=str(d), page=1))
        r1 = client.get("/api/images/1/1")
        etag = r1.headers["etag"]
        r2 = client.get("/api/images/1/1", headers={"if-none-match": etag})
        assert r2.status_code == 304

    def test_width_downscales_image(self, client, tmp_path):
        import io
        from PIL import Image
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())  # 10x10
        set_store(make_entity(id=1, path=str(d), page=1))
        r = client.get("/api/images/1/1?width=5")
        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.content))
        assert img.width == 5

    def test_missing_image_returns_404(self, client):
        assert client.get("/api/images/999/1").status_code == 404


class TestUpdateProgress:
    def test_missing_returns_404(self, client):
        r = client.put("/api/images/999/progress", json={"position": 1})
        assert r.status_code == 404

    def test_success(self, client):
        set_store(make_entity(id=1, page=3))
        r = client.put("/api/images/1/progress", json={"position": 2})
        assert r.status_code == 200
        assert r.json()["position"] == 2
        assert img_api._store[1].lastViewedPosition == 2
        assert img_api._store[1].lastViewedTime is not None

    def test_position_beyond_last_page_rejected(self, client):
        set_store(make_entity(id=1, page=3))
        r = client.put("/api/images/1/progress", json={"position": 4})
        assert r.status_code == 400


class TestDetail:
    def test_returns_sorted_filenames(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        for name in ["c.jpg", "a.jpg", "b.jpg"]:
            (d / name).write_bytes(make_jpeg_bytes())
        set_store(make_entity(id=1, path=str(d), page=3))
        r = client.get("/api/images/1/detail")
        assert r.status_code == 200
        names = [p["name"] for p in r.json()["pageDetails"]]
        assert names == ["a.jpg", "b.jpg", "c.jpg"]

    def test_missing_returns_404(self, client):
        assert client.get("/api/images/999/detail").status_code == 404


class TestFavor:
    def test_favor(self, client):
        set_store(make_entity(id=1))
        r = client.post("/api/images/1/favor")
        assert r.status_code == 200
        assert r.json()["favorited"] is True
        assert img_api._store[1].favorited is True

    def test_unfavor(self, client):
        set_store(make_entity(id=1, favorited=True))
        r = client.request("DELETE", "/api/images/1/favor")
        assert r.status_code == 200
        assert r.json()["favorited"] is False
        assert img_api._store[1].favorited is False

    def test_missing_returns_404(self, client):
        assert client.post("/api/images/999/favor").status_code == 404


class TestRefresh:
    def test_updates_page_count(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())
        (d / "002.jpg").write_bytes(make_jpeg_bytes())
        set_store(make_entity(id=1, path=str(d), page=0))
        r = client.post("/api/images/1/refresh")
        assert r.status_code == 200
        assert r.json()["page"] == 2

    def test_missing_returns_404(self, client):
        assert client.post("/api/images/999/refresh").status_code == 404


class TestRename:
    def test_renames_folder(self, client, tmp_path):
        d = tmp_path / "old-name"
        d.mkdir()
        set_store(make_entity(id=1, name="old-name", path=str(d)))
        r = client.post("/api/images/1/rename", json={"name": "new-name"})
        assert r.status_code == 200
        assert r.json()["name"] == "new-name"
        assert img_api._store[1].name == "new-name"
        assert (tmp_path / "new-name").exists()

    def test_same_name_returns_400(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        set_store(make_entity(id=1, name="album", path=str(d)))
        assert client.post("/api/images/1/rename", json={"name": "album"}).status_code == 400

    def test_missing_returns_404(self, client):
        assert client.post("/api/images/999/rename", json={"name": "x"}).status_code == 404


class TestDelete:
    def test_deletes_folder(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "a.jpg").write_bytes(b"")
        set_store(make_entity(id=1, path=str(d)))
        r = client.delete("/api/images/1")
        assert r.status_code == 200
        assert not d.exists()
        assert 1 not in img_api._store

    def test_rejects_non_image_files(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "a.jpg").write_bytes(b"")
        (d / "readme.txt").write_bytes(b"")
        set_store(make_entity(id=1, path=str(d)))
        assert client.delete("/api/images/1").status_code == 400

    def test_rejects_subdirectory(self, client, tmp_path):
        d = tmp_path / "album"
        d.mkdir()
        (d / "a.jpg").write_bytes(b"")
        (d / "sub").mkdir()
        set_store(make_entity(id=1, path=str(d)))
        assert client.delete("/api/images/1").status_code == 400

    def test_favorited_returns_400(self, client):
        set_store(make_entity(id=1, favorited=True))
        assert client.delete("/api/images/1").status_code == 400

    def test_missing_returns_404(self, client):
        assert client.delete("/api/images/999").status_code == 404


class TestConvertToComic:
    def _album(self, tmp_path, pages=3):
        d = tmp_path / "album" / "My Album"
        d.mkdir(parents=True)
        for i in range(pages):
            (d / f"{i:03d}.jpg").write_bytes(make_jpeg_bytes())
        return d

    def _comic_dir(self, tmp_path, monkeypatch):
        import global_data
        comic_dir = tmp_path / "comics_src"
        comic_dir.mkdir()
        monkeypatch.setattr(global_data.Config.Comic, "scan_pathes", [str(comic_dir)])
        return comic_dir

    def test_creates_comic_zip(self, client, tmp_path, monkeypatch):
        import zipfile
        d = self._album(tmp_path, pages=3)
        comic_dir = self._comic_dir(tmp_path, monkeypatch)
        set_store(make_entity(id=1, name="My Album", path=str(d), page=3))

        r = client.post("/api/images/1/convert-to-comic")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "My Album.zip"
        assert body["page"] == 3

        zip_path = comic_dir / "My Album.zip"
        assert zip_path.exists()
        with zipfile.ZipFile(zip_path) as zf:
            assert sorted(zf.namelist()) == ["000.jpg", "001.jpg", "002.jpg"]

    def test_source_folder_preserved(self, client, tmp_path, monkeypatch):
        d = self._album(tmp_path)
        self._comic_dir(tmp_path, monkeypatch)
        set_store(make_entity(id=1, name="My Album", path=str(d)))
        assert client.post("/api/images/1/convert-to-comic").status_code == 200
        assert d.exists()
        assert 1 in img_api._store

    def test_imports_into_comic_db(self, client, tmp_path, monkeypatch):
        d = self._album(tmp_path)
        self._comic_dir(tmp_path, monkeypatch)
        set_store(make_entity(id=1, name="My Album", path=str(d)))
        client.post("/api/images/1/convert-to-comic")
        listing = client.get("/api/comics").json()
        assert any(c["name"] == "My Album.zip" for c in listing)

    def test_empty_folder_returns_400(self, client, tmp_path, monkeypatch):
        d = tmp_path / "empty"
        d.mkdir()
        self._comic_dir(tmp_path, monkeypatch)
        set_store(make_entity(id=1, name="empty", path=str(d), page=0))
        assert client.post("/api/images/1/convert-to-comic").status_code == 400

    def test_duplicate_returns_400(self, client, tmp_path, monkeypatch):
        d = self._album(tmp_path)
        self._comic_dir(tmp_path, monkeypatch)
        set_store(make_entity(id=1, name="My Album", path=str(d)))
        assert client.post("/api/images/1/convert-to-comic").status_code == 200
        assert client.post("/api/images/1/convert-to-comic").status_code == 400

    def test_missing_returns_404(self, client):
        assert client.post("/api/images/999/convert-to-comic").status_code == 404


class TestSetCover:
    def test_updates_cover_position(self, client, tmp_path, monkeypatch):
        import global_data
        d = tmp_path / "album"
        d.mkdir()
        (d / "001.jpg").write_bytes(make_jpeg_bytes())
        (d / "002.jpg").write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(tmp_path))
        set_store(make_entity(id=1, path=str(d), page=2))
        r = client.post("/api/images/1/2/cover")
        assert r.status_code == 200
        assert img_api._store[1].coverPosition == 2

    def test_missing_returns_404(self, client):
        assert client.post("/api/images/999/1/cover").status_code == 404
