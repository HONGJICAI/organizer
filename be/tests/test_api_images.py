from conftest import make_jpeg_bytes


class TestGetImages:
    def test_no_scan_dir_returns_empty(self, client, monkeypatch):
        import global_data
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", ["/nonexistent/xyz"])
        r = client.get("/api/images")
        assert r.status_code == 200
        assert r.json() == []

    def test_no_subfolders_returns_empty(self, client, tmp_path, monkeypatch):
        import global_data
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(tmp_path / "nginx"))
        (tmp_path / "nginx").mkdir()
        r = client.get("/api/images")
        assert r.status_code == 200
        assert r.json() == []

    def test_folders_with_images_returned(self, client, tmp_path, monkeypatch):
        import global_data
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        album1 = tmp_path / "album1"
        album1.mkdir()
        (album1 / "a.jpg").write_bytes(make_jpeg_bytes())
        album2 = tmp_path / "album2"
        album2.mkdir()
        (album2 / "b.jpg").write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(nginx_dir))
        r = client.get("/api/images")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_empty_folder_excluded(self, client, tmp_path, monkeypatch):
        import global_data
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        (tmp_path / "with_images").mkdir()
        (tmp_path / "with_images" / "a.jpg").write_bytes(make_jpeg_bytes())
        (tmp_path / "empty").mkdir()
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(nginx_dir))
        r = client.get("/api/images")
        assert len(r.json()) == 1
        assert r.json()[0]["id"] == "with_images"

    def test_non_image_files_excluded_from_count(self, client, tmp_path, monkeypatch):
        import global_data
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        album = tmp_path / "album"
        album.mkdir()
        (album / "a.jpg").write_bytes(make_jpeg_bytes())
        (album / "readme.txt").write_text("not an image")
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(nginx_dir))
        r = client.get("/api/images")
        assert r.json()[0]["count"] == 1

    def test_response_shape(self, client, tmp_path, monkeypatch):
        import global_data
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        album = tmp_path / "my-album"
        album.mkdir()
        (album / "photo.jpg").write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(nginx_dir))
        r = client.get("/api/images")
        item = r.json()[0]
        assert item["id"] == "my-album"
        assert item["name"] == "my-album"
        assert "path" in item
        assert "count" in item
        assert "size" in item
        assert "updateTime" in item
        assert item["coverUrl"] == "/images/my-album/photo.jpg"


class TestGetImageFolder:
    def test_get_existing_folder(self, client, tmp_path, monkeypatch):
        import global_data
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        album = tmp_path / "gallery"
        album.mkdir()
        (album / "001.jpg").write_bytes(make_jpeg_bytes())
        (album / "002.jpg").write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(nginx_dir))
        r = client.get("/api/images/gallery")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == "gallery"
        assert data["count"] == 2
        assert len(data["files"]) == 2
        assert data["files"][0]["url"] == "/images/gallery/001.jpg"

    def test_get_missing_folder_returns_404(self, client, tmp_path, monkeypatch):
        import global_data
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(tmp_path))
        r = client.get("/api/images/nonexistent")
        assert r.status_code == 404

    def test_files_sorted(self, client, tmp_path, monkeypatch):
        import global_data
        nginx_dir = tmp_path / "nginx"
        nginx_dir.mkdir()
        album = tmp_path / "sorted"
        album.mkdir()
        for name in ["c.jpg", "a.jpg", "b.jpg"]:
            (album / name).write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(tmp_path)])
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(nginx_dir))
        r = client.get("/api/images/sorted")
        names = [f["name"] for f in r.json()["files"]]
        assert names == ["a.jpg", "b.jpg", "c.jpg"]
