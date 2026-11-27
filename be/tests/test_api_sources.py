"""Media sources (sources.py, /api/system/sources and /api/system/folders) and
how scans hold folders that are missing or empty."""
from datetime import datetime

import pytest
from sqlmodel import select

import api.images as img_api
import api.system
import global_data
import mover
import sources
from core.scan_progress import progress
from loader import ComicLoader, VideoLoader
from model import ComicEntity, ImageEntity, MediaSource, VideoEntity
from tests.conftest import insert_comic, insert_video, make_jpeg_bytes, make_zip_comic


@pytest.fixture
def builtin(tmp_path, monkeypatch):
    """Built-in folders under tmp_path; nothing counts as unmounted."""
    paths = {}
    for media, cls in (("comic", global_data.Config.Comic), ("video", global_data.Config.Video)):
        path = tmp_path / f"builtin-{media}"
        path.mkdir()
        monkeypatch.setattr(cls, "scan_pathes", [str(path)])
        paths[media] = path
    images, liked = tmp_path / "builtin-image", tmp_path / "liked"
    images.mkdir()
    liked.mkdir()
    monkeypatch.setattr(global_data.Config.Image, "scan_pathes", [str(images), str(liked)])
    monkeypatch.setattr(global_data.Config.Image, "liked_path", str(liked))
    paths["image"], paths["liked"] = images, liked
    monkeypatch.setattr(mover, "in_container_fs", lambda path: False)
    return paths


@pytest.fixture
def scans(monkeypatch):
    """Record the scans the endpoints queue instead of running them."""
    queued = []

    def start_scan(media_type):
        queued.append(media_type)
        return "started"

    monkeypatch.setattr(api.system, "start_scan", start_scan)
    return queued


def add_source(session, media, path) -> MediaSource:
    row = MediaSource(media=media, path=str(path))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def issues():
    return [(i["media"], i["level"], i["path"], i["reason"]) for i in progress.snapshot()["issues"]]


class TestAllSources:
    def test_builtin_then_added(self, task_session, builtin, tmp_path):
        extra = tmp_path / "extra"
        row = add_source(task_session, "comic", extra)
        found = sources.all_sources("comic")
        assert [(s.path, s.builtin, s.id) for s in found] == [
            (str(builtin["comic"]), True, None),
            (str(extra), False, row.id),
        ]
        assert sources.paths("comic") == [str(builtin["comic"]), str(extra)]
        assert sources.paths("video") == [str(builtin["video"])]

    def test_every_media(self, task_session, builtin):
        assert [s.media for s in sources.all_sources()] == ["comic", "video", "image", "image"]

    def test_duplicate_path_counts_once(self, task_session, builtin):
        add_source(task_session, "comic", str(builtin["comic"]) + "/")
        assert sources.paths("comic") == [str(builtin["comic"])]

    def test_inside(self):
        assert sources.inside("/a/b", "/a")
        assert sources.inside("/a", "/a")
        assert not sources.inside("/ab", "/a")
        assert not sources.inside("rel", "/a")


class TestStatus:
    def test_status(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mover, "in_container_fs", lambda path: False)
        assert sources.status(str(tmp_path)) == "ok"
        assert sources.status(str(tmp_path / "gone")) == "not_found"
        monkeypatch.setattr(mover, "in_container_fs", lambda path: True)
        assert sources.status(str(tmp_path)) == "not_mounted"


class TestComicScanHolds:
    def test_missing_folder_keeps_its_records(self, task_session, builtin, tmp_path):
        make_zip_comic(builtin["comic"] / "here.zip")
        nas = tmp_path / "nas"  # not there: the share is down
        add_source(task_session, "comic", nas)
        insert_comic(task_session, id=1, path=str(nas / "kept.zip"))
        progress.start("comics")
        ComicLoader().work()
        task_session.expire_all()
        kept = task_session.get(ComicEntity, 1)
        assert not kept.missing
        assert ("comic", "warning", str(nas), sources.NOT_FOUND) in issues()
        # The other folder was still scanned.
        paths = task_session.exec(select(ComicEntity.path)).all()
        assert str(builtin["comic"] / "here.zip") in paths

    def test_empty_folder_keeps_its_records(self, task_session, builtin, tmp_path):
        make_zip_comic(builtin["comic"] / "here.zip")
        nas = tmp_path / "nas"
        nas.mkdir()  # an unmounted mount point: there, but empty
        add_source(task_session, "comic", nas)
        insert_comic(task_session, id=1, path=str(nas / "kept.zip"))
        progress.start("comics")
        ComicLoader().work()
        task_session.expire_all()
        assert not task_session.get(ComicEntity, 1).missing
        assert ("comic", "warning", str(nas), sources.EMPTY) in issues()

    def test_removed_folder_flags_its_records(self, task_session, builtin, tmp_path):
        make_zip_comic(builtin["comic"] / "here.zip")
        insert_comic(task_session, id=1, path=str(tmp_path / "was-a-source" / "x.zip"))
        ComicLoader().work()
        task_session.expire_all()
        assert task_session.get(ComicEntity, 1).missing

    def test_held_record_is_not_taken_over_by_a_copy(self, task_session, builtin, tmp_path):
        copy = builtin["comic"] / "copy.zip"
        make_zip_comic(copy)
        stat = copy.stat()
        nas = tmp_path / "nas"
        add_source(task_session, "comic", nas)
        # Same size and mtime as the copy: without the hold this record would
        # be taken for a moved file.
        insert_comic(
            task_session, id=1, path=str(nas / "copy.zip"), size=stat.st_size,
            updateTime=datetime.fromtimestamp(stat.st_mtime),
        )
        ComicLoader().work()
        task_session.expire_all()
        assert task_session.get(ComicEntity, 1).path == str(nas / "copy.zip")
        assert len(task_session.exec(select(ComicEntity)).all()) == 2

    def test_added_folder_is_scanned(self, task_session, builtin, tmp_path):
        extra = tmp_path / "extra"
        extra.mkdir()
        make_zip_comic(extra / "new.zip")
        add_source(task_session, "comic", extra)
        ComicLoader().work()
        assert task_session.exec(select(ComicEntity.path)).all() == [str(extra / "new.zip")]


class TestVideoScanHolds:
    def test_missing_folder_keeps_its_records(self, task_session, builtin, tmp_path):
        nas = tmp_path / "nas"
        add_source(task_session, "video", nas)
        insert_video(task_session, id=1, path=str(nas / "kept.mp4"))
        VideoLoader().work()
        task_session.expire_all()
        assert not task_session.get(VideoEntity, 1).missing


def album(path: str, id: int = 7) -> ImageEntity:
    return ImageEntity(id=id, name="a", path=path, size=0, updateTime=datetime.now(), page=1)


class TestImageScanHolds:
    @pytest.fixture(autouse=True)
    def empty_store(self):
        img_api._store.clear()
        yield
        img_api._store.clear()

    def test_missing_folder_keeps_its_albums(self, task_session, builtin, tmp_path):
        nas = tmp_path / "nas"
        add_source(task_session, "image", nas)
        img_api._store[7] = album(str(nas / "trip"))
        progress.start("images")
        img_api.bootstrap()
        assert [e.path for e in img_api._store.values()] == [str(nas / "trip")]
        assert ("image", "warning", str(nas), sources.NOT_FOUND) in issues()

    def test_empty_folder_keeps_its_albums(self, task_session, builtin, tmp_path):
        trip = builtin["image"] / "trip"
        trip.mkdir()
        (trip / "1.jpg").write_bytes(make_jpeg_bytes())
        nas = tmp_path / "nas"
        nas.mkdir()
        add_source(task_session, "image", nas)
        img_api._store[7] = album(str(nas / "old"))
        progress.start("images")
        img_api.bootstrap()
        assert sorted(e.path for e in img_api._store.values()) == sorted([str(nas / "old"), str(trip)])
        # An empty liked folder is normal and not reported.
        assert issues() == [("image", "warning", str(nas), sources.EMPTY)]

    def test_albums_outside_every_folder_go(self, task_session, builtin, tmp_path):
        img_api._store[7] = album(str(tmp_path / "removed-source" / "trip"))
        img_api.bootstrap()
        assert img_api._store == {}


class TestMoveTargets:
    def test_added_comic_folder_is_a_target(self, task_session, builtin, tmp_path):
        extra = tmp_path / "extra"
        extra.mkdir()
        add_source(task_session, "comic", extra)
        assert mover.check_target(task_session, str(extra / "artist")) == str(extra / "artist")
        with pytest.raises(mover.MoveError):
            mover.check_target(task_session, str(tmp_path / "elsewhere"))


class TestListEndpoint:
    def test_lists_builtin_and_added(self, client, session, builtin, tmp_path):
        row = add_source(session, "video", tmp_path / "gone")
        r = client.get("/api/system/sources")
        assert r.status_code == 200
        assert r.json() == [
            {"id": None, "media": "comic", "path": str(builtin["comic"]), "builtin": True, "status": "ok"},
            {"id": None, "media": "video", "path": str(builtin["video"]), "builtin": True, "status": "ok"},
            {"id": None, "media": "image", "path": str(builtin["image"]), "builtin": True, "status": "ok"},
            {"id": None, "media": "image", "path": str(builtin["liked"]), "builtin": True, "status": "ok"},
            {"id": row.id, "media": "video", "path": str(tmp_path / "gone"), "builtin": False, "status": "not_found"},
        ]


class TestAddEndpoint:
    def test_adds_and_queues_a_scan(self, client, session, builtin, scans, tmp_path):
        extra = tmp_path / "extra"
        extra.mkdir()
        r = client.post("/api/system/sources", json={"media": "image", "path": f" {extra}/ "})
        assert r.status_code == 200
        body = r.json()
        assert body["scan"] == "started"
        assert body["source"]["path"] == str(extra)
        assert body["source"]["builtin"] is False and body["source"]["status"] == "ok"
        assert scans == ["images"]
        [row] = session.exec(select(MediaSource)).all()
        assert (row.id, row.media, row.path) == (body["source"]["id"], "image", str(extra))

    @pytest.mark.parametrize("path, message", [
        ("", "absolute path"),
        ("relative/dir", "absolute path"),
        ("{tmp}/gone", "Folder not found"),
        ("{tmp}/builtin-comic/sub", "Overlaps the built-in comic folder"),
        ("{tmp}", "Overlaps the built-in comic folder"),
    ])
    def test_refused(self, client, builtin, scans, tmp_path, path, message):
        (tmp_path / "builtin-comic" / "sub").mkdir()
        r = client.post("/api/system/sources", json={"media": "comic", "path": path.format(tmp=tmp_path)})
        assert r.status_code == 400
        assert message in r.json()["msg"]
        assert scans == []

    def test_overlapping_an_added_folder(self, client, session, builtin, scans, tmp_path):
        extra = tmp_path / "extra"
        (extra / "sub").mkdir(parents=True)
        add_source(session, "video", extra)
        r = client.post("/api/system/sources", json={"media": "comic", "path": str(extra / "sub")})
        assert r.status_code == 400
        assert "Overlaps the added video folder" in r.json()["msg"]

    def test_not_on_a_mounted_drive(self, client, builtin, scans, tmp_path, monkeypatch):
        extra = tmp_path / "extra"
        extra.mkdir()
        monkeypatch.setattr(mover, "in_container_fs", lambda path: True)
        r = client.post("/api/system/sources", json={"media": "comic", "path": str(extra)})
        assert r.status_code == 400
        assert "Not on a mounted drive" in r.json()["msg"]

    def test_unknown_media(self, client, builtin, scans, tmp_path):
        r = client.post("/api/system/sources", json={"media": "audio", "path": str(tmp_path)})
        assert r.status_code == 400

    def test_validate_new_unknown_media(self):
        with pytest.raises(sources.SourceError, match="Unknown media"):
            sources.validate_new("audio", "/x")


class TestRemoveEndpoint:
    def test_removes_and_queues_a_scan(self, client, session, builtin, scans, tmp_path):
        row = add_source(session, "comic", tmp_path / "extra")
        r = client.delete(f"/api/system/sources/{row.id}")
        assert r.status_code == 200
        assert r.json() == {"scan": "started"}
        assert scans == ["comics"]
        session.expire_all()
        assert session.exec(select(MediaSource)).all() == []

    def test_not_found(self, client, scans):
        r = client.delete("/api/system/sources/99")
        assert r.status_code == 404
        assert scans == []


class TestFoldersEndpoint:
    def test_lists_subfolders(self, client, tmp_path):
        tmp_path = tmp_path / "browse"
        for name in ("b", "A", ".hidden"):
            (tmp_path / name).mkdir(parents=True)
        (tmp_path / "file.txt").write_text("x")
        r = client.get("/api/system/folders", params={"path": str(tmp_path)})
        assert r.status_code == 200
        assert r.json() == {
            "path": str(tmp_path),
            "parent": str(tmp_path.parent),
            "dirs": [
                {"name": "A", "path": str(tmp_path / "A"), "mount": False},
                {"name": "b", "path": str(tmp_path / "b"), "mount": False},
            ],
        }

    def test_root_has_no_parent(self, client):
        r = client.get("/api/system/folders", params={"path": "/"})
        assert r.status_code == 200
        assert r.json()["parent"] is None

    def test_default_folder(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(sources, "default_browse_root", lambda: str(tmp_path))
        assert client.get("/api/system/folders").json()["path"] == str(tmp_path)

    def test_default_browse_root(self, monkeypatch):
        monkeypatch.setattr(sources.os.path, "isdir", lambda p: p == "/data")
        assert sources.default_browse_root() == "/data"
        monkeypatch.setattr(sources.os.path, "isdir", lambda p: False)
        assert sources.default_browse_root() == "/"

    @pytest.mark.parametrize("path, message", [
        ("relative", "absolute path"),
        ("/no/such/folder/here", "Folder not found"),
    ])
    def test_refused(self, client, path, message):
        r = client.get("/api/system/folders", params={"path": path})
        assert r.status_code == 400
        assert message in r.json()["msg"]

    def test_unreadable(self, client, tmp_path, monkeypatch):
        def scandir(path):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(sources.os, "scandir", scandir)
        r = client.get("/api/system/folders", params={"path": str(tmp_path)})
        assert r.status_code == 400
        assert "Permission denied" in r.json()["msg"]

