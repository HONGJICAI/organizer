from datetime import datetime
from unittest.mock import patch


import comicfile
from conftest import MockComicfile, insert_comic, make_zip_comic
from loader import ComicLoader
from model import ComicEntity
from util import PathState


# ---------------------------------------------------------------------------
# GET /api/comics
# ---------------------------------------------------------------------------

class TestGetAll:
    def test_empty(self, client):
        r = client.get("/api/comics")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_all(self, client, session):
        insert_comic(session, 1, "a.zip")
        insert_comic(session, 2, "b.zip")
        r = client.get("/api/comics")
        assert r.status_code == 200
        assert len(r.json()) == 2

    def test_top_limit(self, client, session):
        for i in range(5):
            insert_comic(session, i + 1, f"{i}.zip")
        r = client.get("/api/comics?top=2")
        assert len(r.json()) == 2

    def test_default_excludes_missing(self, client, session):
        # The missing flag is maintained by the scan reconcile; the default
        # list hides flagged rows so an unmounted drive shows no ghosts.
        insert_comic(session, 1, "here.zip")
        insert_comic(session, 2, "gone.zip", missing=True)
        r = client.get("/api/comics")
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert names == ["here.zip"]

    def test_file_miss_returns_only_missing(self, client, session):
        insert_comic(session, 1, "here.zip")
        insert_comic(session, 2, "gone.zip", missing=True)
        r = client.get("/api/comics?fileMiss=true")
        assert r.status_code == 200
        names = [c["name"] for c in r.json()]
        assert names == ["gone.zip"]

    def test_file_miss_false_returns_present(self, client, session):
        insert_comic(session, 1)
        r = client.get("/api/comics?fileMiss=false")
        assert len(r.json()) == 1


# ---------------------------------------------------------------------------
# GET /api/comics/{id}
# ---------------------------------------------------------------------------

class TestGet:
    def test_not_found(self, client):
        r = client.get("/api/comics/999")
        assert r.status_code == 404

    def test_found(self, client, session):
        insert_comic(session, 1, "hello.zip")
        r = client.get("/api/comics/1")
        assert r.status_code == 200
        assert r.json()["name"] == "hello.zip"


# ---------------------------------------------------------------------------
# GET /api/comics/{id}/detail
# ---------------------------------------------------------------------------

class TestDetail:
    def test_comic_not_found(self, client):
        r = client.get("/api/comics/999/detail")
        assert r.status_code == 404

    def test_file_not_found(self, client, session):
        insert_comic(session, 1)
        with patch("comicfile.create_open", return_value=None):
            r = client.get("/api/comics/1/detail")
        assert r.status_code == 404

    def test_success(self, client, session):
        insert_comic(session, 1, page=3)
        mock_cf = MockComicfile(pages=3)
        with patch("comicfile.create_open", return_value=mock_cf):
            r = client.get("/api/comics/1/detail")
        assert r.status_code == 200
        assert len(r.json()["pageDetails"]) == 3


# ---------------------------------------------------------------------------
# POST /DELETE /api/comics/{id}/favor
# ---------------------------------------------------------------------------

class TestFavor:
    def test_favor(self, client, session):
        insert_comic(session, 1)
        r = client.post("/api/comics/1/favor")
        assert r.status_code == 200
        assert r.json()["favorited"] is True

    def test_favor_not_found(self, client):
        r = client.post("/api/comics/999/favor")
        assert r.status_code == 404

    def test_unfavor(self, client, session):
        insert_comic(session, 1, favorited=True)
        r = client.request("DELETE", "/api/comics/1/favor")
        assert r.status_code == 200
        assert r.json()["favorited"] is False

    def test_unfavor_not_found(self, client):
        r = client.request("DELETE", "/api/comics/999/favor")
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/comics/{id}/refresh
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_success(self, client, session, tmp_path):
        path = tmp_path / "comic.zip"
        make_zip_comic(str(path), pages=4)
        insert_comic(session, 1, name="comic.zip", path=str(path), page=0)
        with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            r = client.post("/api/comics/1/refresh")
        assert r.status_code == 200
        assert r.json()["page"] == 4

    def test_not_found(self, client):
        r = client.post("/api/comics/999/refresh")
        assert r.status_code == 404

    def test_bumps_cover_version(self, client, session, tmp_path):
        # Regenerating the cover must bump entityUpdateTime so the frontend's
        # cache-busting cover URL changes.
        path = tmp_path / "comic.zip"
        make_zip_comic(str(path), pages=4)
        old = datetime(2000, 1, 1)
        insert_comic(
            session, 1, name="comic.zip", path=str(path), page=0,
            entityUpdateTime=old,
        )
        with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            r = client.post("/api/comics/1/refresh")
        assert r.status_code == 200
        assert datetime.fromisoformat(r.json()["entityUpdateTime"]) > old


# ---------------------------------------------------------------------------
# POST /api/comics/{id}/rename
# ---------------------------------------------------------------------------

class TestRename:
    def test_success(self, client, session, tmp_path):
        f = tmp_path / "old.zip"
        f.write_bytes(b"data")
        insert_comic(session, 1, name="old.zip", path=str(f))
        r = client.post("/api/comics/1/rename", json={"name": "new.zip"})
        assert r.status_code == 200
        assert r.json()["name"] == "new.zip"
        assert (tmp_path / "new.zip").exists()

    def test_same_name(self, client, session, tmp_path):
        f = tmp_path / "test.zip"
        f.write_bytes(b"data")
        insert_comic(session, 1, name="test.zip", path=str(f))
        r = client.post("/api/comics/1/rename", json={"name": "test.zip"})
        assert r.status_code == 400

    def test_comic_not_found(self, client):
        r = client.post("/api/comics/999/rename", json={"name": "new.zip"})
        assert r.status_code == 404

    def test_file_not_on_disk(self, client, session):
        insert_comic(session, 1, path="/nonexistent/test.zip")
        r = client.post("/api/comics/1/rename", json={"name": "new.zip"})
        assert r.status_code == 404

    def test_target_already_exists_on_disk(self, client, session, tmp_path):
        old = tmp_path / "old.zip"
        old.write_bytes(b"data")
        (tmp_path / "new.zip").write_bytes(b"data")
        insert_comic(session, 1, name="old.zip", path=str(old))
        r = client.post("/api/comics/1/rename", json={"name": "new.zip"})
        assert r.status_code == 400

    def test_name_conflict_in_db(self, client, session, tmp_path):
        f1 = tmp_path / "a.zip"
        f1.write_bytes(b"data")
        insert_comic(session, 1, name="a.zip", path=str(f1))
        insert_comic(session, 2, name="b.zip", path=str(tmp_path / "b.zip"))
        r = client.post("/api/comics/1/rename", json={"name": "b.zip"})
        assert r.status_code == 400

    def test_clears_cache_entry(self, client, session, tmp_path):
        f = tmp_path / "cached.zip"
        make_zip_comic(str(f))
        insert_comic(session, 1, name="cached.zip", path=str(f))
        comicfile.create_open(str(f))
        assert len(comicfile.comic_cache) == 1
        r = client.post("/api/comics/1/rename", json={"name": "renamed.zip"})
        assert r.status_code == 200
        assert len(comicfile.comic_cache) == 0


# ---------------------------------------------------------------------------
# DELETE /api/comics/{id}
# ---------------------------------------------------------------------------

class TestDelete:
    def test_archive_soft_delete(self, client, session, engine_and_client):
        engine, _ = engine_and_client
        insert_comic(session, 1, path="/nonexistent/test.zip")
        r = client.delete("/api/comics/1")
        assert r.status_code == 200
        from sqlmodel import Session as S
        with S(engine) as s:
            comic = s.get(ComicEntity, 1)
            assert comic is not None
            assert comic.archived is True

    def test_permanent_deletes_db_row(self, client, session, engine_and_client, tmp_path):
        engine, _ = engine_and_client
        f = tmp_path / "perm.zip"
        make_zip_comic(str(f))
        insert_comic(session, 1, path=str(f))
        r = client.delete("/api/comics/1?permanent=true")
        assert r.status_code == 200
        from sqlmodel import Session as S
        with S(engine) as s:
            assert s.get(ComicEntity, 1) is None

    def test_permanent_removes_file(self, client, session, tmp_path):
        f = tmp_path / "del.zip"
        make_zip_comic(str(f))
        insert_comic(session, 1, path=str(f))
        client.delete("/api/comics/1?permanent=true")
        assert not f.exists()

    def test_permanent_removes_cover(self, client, session, tmp_path, engine_and_client):
        _, c = engine_and_client
        f = tmp_path / "del.zip"
        make_zip_comic(str(f))
        insert_comic(session, 1, path=str(f))
        cover = tmp_path / "comics" / "1_0.jpg"
        cover.write_bytes(b"cover")
        c.delete("/api/comics/1?permanent=true")
        assert not cover.exists()

    def test_favorited_blocked(self, client, session):
        insert_comic(session, 1, favorited=True)
        r = client.delete("/api/comics/1")
        assert r.status_code == 400

    def test_missing_file_is_ok(self, client, session):
        insert_comic(session, 1, path="/nonexistent/missing.zip")
        r = client.delete("/api/comics/1?permanent=true")
        assert r.status_code == 200

    def test_not_found(self, client):
        r = client.delete("/api/comics/999")
        assert r.status_code == 404

    def test_delete_directory(self, client, session, tmp_path):
        d = tmp_path / "mycomic"
        d.mkdir()
        (d / "0.jpg").write_bytes(b"x")
        insert_comic(session, 1, path=str(d), page=1)
        r = client.delete("/api/comics/1?permanent=true")
        assert r.status_code == 200
        assert not d.exists()


# ---------------------------------------------------------------------------
# POST /api/comics/check
# ---------------------------------------------------------------------------

class TestCheck:
    def test_empty_ids_is_400(self, client):
        r = client.post("/api/comics/check", json={"ids": []})
        assert r.status_code == 400

    def test_present_clears_missing(self, client, session, tmp_path):
        # File is back on disk -> the stale missing flag should be cleared.
        f = tmp_path / "back.zip"
        make_zip_comic(str(f), pages=1)
        insert_comic(session, 1, path=str(f), missing=True)
        r = client.post("/api/comics/check", json={"ids": [1]})
        assert r.status_code == 200
        assert r.json()["results"] == [{"id": 1, "status": "present"}]
        session.expire_all()
        assert not session.get(ComicEntity, 1).missing

    def test_absent_sets_missing(self, client, session, tmp_path):
        # Parent dir exists but the file is gone -> a confirmed deletion.
        insert_comic(session, 1, path=str(tmp_path / "gone.zip"), missing=False)
        r = client.post("/api/comics/check", json={"ids": [1]})
        assert r.status_code == 200
        assert r.json()["results"] == [{"id": 1, "status": "absent"}]
        session.expire_all()
        assert session.get(ComicEntity, 1).missing

    def test_unknown_leaves_flag_untouched(self, client, session):
        # A mount blip (UNKNOWN) must never flip the stored flag either way.
        insert_comic(session, 1, path="/lib/blip.zip", missing=True)
        with patch("util.probe_path", return_value=PathState.UNKNOWN):
            r = client.post("/api/comics/check", json={"ids": [1]})
        assert r.status_code == 200
        assert r.json()["results"] == [{"id": 1, "status": "unknown"}]
        session.expire_all()
        assert session.get(ComicEntity, 1).missing

    def test_notfound_for_unknown_id(self, client):
        r = client.post("/api/comics/check", json={"ids": [999]})
        assert r.status_code == 200
        assert r.json()["results"] == [{"id": 999, "status": "notfound"}]

    def test_mixed_batch(self, client, session, tmp_path):
        f = tmp_path / "here.zip"
        make_zip_comic(str(f), pages=1)
        insert_comic(session, 1, path=str(f), missing=True)
        insert_comic(session, 2, path=str(tmp_path / "gone.zip"), missing=True)
        r = client.post("/api/comics/check", json={"ids": [1, 2, 999]})
        assert r.status_code == 200
        statuses = {row["id"]: row["status"] for row in r.json()["results"]}
        assert statuses == {1: "present", 2: "absent", 999: "notfound"}
        session.expire_all()
        assert not session.get(ComicEntity, 1).missing
        assert session.get(ComicEntity, 2).missing

    def test_duplicate_ids_probed_once(self, client, session, tmp_path):
        f = tmp_path / "dup.zip"
        make_zip_comic(str(f), pages=1)
        insert_comic(session, 1, path=str(f), missing=True)
        r = client.post("/api/comics/check", json={"ids": [1, 1]})
        assert r.status_code == 200
        assert r.json()["results"] == [{"id": 1, "status": "present"}]
