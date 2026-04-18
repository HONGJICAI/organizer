from conftest import make_jpeg_bytes


class TestGetImages:
    def test_no_dir_returns_empty(self, client, monkeypatch):
        import global_data
        monkeypatch.setattr(global_data.Config, "nginx_image_path", "/nonexistent/path/xyz")
        r = client.get("/api/images")
        assert r.status_code == 200
        assert r.json() == []

    def test_empty_dir(self, client):
        r = client.get("/api/images")
        assert r.status_code == 200
        assert r.json() == []

    def test_with_files(self, client, tmp_path, monkeypatch):
        import global_data
        img_dir = tmp_path / "imgs"
        img_dir.mkdir()
        (img_dir / "a.jpg").write_bytes(make_jpeg_bytes())
        (img_dir / "b.jpg").write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(img_dir))
        r = client.get("/api/images")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_top_limit(self, client, tmp_path, monkeypatch):
        import global_data
        img_dir = tmp_path / "imgs2"
        img_dir.mkdir()
        for i in range(5):
            (img_dir / f"{i}.jpg").write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(img_dir))
        r = client.get("/api/images?top=2")
        assert len(r.json()) == 2

    def test_ignores_subdirs(self, client, tmp_path, monkeypatch):
        import global_data
        img_dir = tmp_path / "imgs3"
        img_dir.mkdir()
        (img_dir / "a.jpg").write_bytes(make_jpeg_bytes())
        (img_dir / "subdir").mkdir()
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(img_dir))
        r = client.get("/api/images")
        assert len(r.json()) == 1

    def test_response_shape(self, client, tmp_path, monkeypatch):
        import global_data
        img_dir = tmp_path / "imgs4"
        img_dir.mkdir()
        (img_dir / "photo.jpg").write_bytes(make_jpeg_bytes())
        monkeypatch.setattr(global_data.Config, "nginx_image_path", str(img_dir))
        r = client.get("/api/images")
        item = r.json()[0]
        assert "name" in item
        assert "path" in item
        assert "updateTime" in item
