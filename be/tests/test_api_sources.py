"""Media sources (sources.py, /api/system/sources and /api/system/folders) and
how scans hold folders that are missing or empty."""
import os
from datetime import datetime

import pytest
from sqlmodel import select

import api.images as img_api
import api.system
import global_data
import mover
import smb
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
        def local(path):
            return sources.Source(media="comic", path=str(path), builtin=False)

        monkeypatch.setattr(mover, "in_container_fs", lambda path: False)
        assert sources.status(local(tmp_path)) == "ok"
        assert sources.status(local(tmp_path / "gone")) == "not_found"
        monkeypatch.setattr(mover, "in_container_fs", lambda path: True)
        assert sources.status(local(tmp_path)) == "not_mounted"


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
            {"id": None, "media": "comic", "path": str(builtin["comic"]), "builtin": True, "status": "ok", "kind": "local", "error": None, "smb": None},
            {"id": None, "media": "video", "path": str(builtin["video"]), "builtin": True, "status": "ok", "kind": "local", "error": None, "smb": None},
            {"id": None, "media": "image", "path": str(builtin["image"]), "builtin": True, "status": "ok", "kind": "local", "error": None, "smb": None},
            {"id": None, "media": "image", "path": str(builtin["liked"]), "builtin": True, "status": "ok", "kind": "local", "error": None, "smb": None},
            {"id": row.id, "media": "video", "path": str(tmp_path / "gone"), "builtin": False, "status": "not_found", "kind": "local", "error": None, "smb": None},
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



# ---------------------------------------------------------------------------
# SMB shares (smb.py is faked: see tests/test_smb.py)
# ---------------------------------------------------------------------------

SHARE = {"share": r"\\nas\media\manga", "username": "me", "password": "secret"}


def add_share(client, media="comic", **smb_fields):
    body = {"media": media, "kind": "smb", "smb": {**SHARE, **smb_fields}}
    return client.post("/api/system/sources", json=body)


class TestAddShare:
    def test_adds_mounts_and_queues_a_scan(self, client, session, builtin, scans, mounts):
        r = add_share(client)
        assert r.status_code == 200
        body = r.json()
        source = body["source"]
        assert source["kind"] == "smb" and source["status"] == "ok" and source["error"] is None
        assert os.path.dirname(source["path"]) == smb.MOUNT_ROOT
        assert source["smb"] == {
            "share": "//nas/media/manga", "username": "me", "domain": None, "options": None, "hasPassword": True,
        }
        assert "password" not in str(source)
        assert body["scan"] == "started" and scans == ["comics"]
        assert source["path"] in mounts.mounted
        row = session.get(MediaSource, source["id"])
        assert (row.smbPassword, row.kind) == ("secret", "smb")

    def test_connect_failure_adds_nothing(self, client, session, builtin, scans, mounts):
        mounts.fail["//nas/media/manga"] = (32, "mount error(13): Permission denied")
        r = add_share(client)
        assert r.status_code == 400
        assert r.json()["msg"].startswith("Can't connect: Permission denied")
        assert session.exec(select(MediaSource)).all() == []
        assert scans == []
        assert os.listdir(smb.MOUNT_ROOT) == []

    def test_mount_points_are_not_reused(self, client, session, builtin, scans, mounts):
        first = add_share(client).json()["source"]
        assert client.delete(f"/api/system/sources/{first['id']}").status_code == 200
        second = add_share(client).json()["source"]
        assert second["path"] != first["path"]

    def test_new_mount_point_skips_taken_names(self, mounts, monkeypatch):
        names = iter(["a" * 32, "b" * 32])
        monkeypatch.setattr(smb.uuid, "uuid4", lambda: type("U", (), {"hex": next(names)})())
        os.makedirs(os.path.join(smb.MOUNT_ROOT, "a" * 12))
        assert smb.new_mount_point() == os.path.join(smb.MOUNT_ROOT, "b" * 12)

    @pytest.mark.parametrize("fields, message", [
        ({"share": "nas/media"}, "//server/share"),
        ({"options": "password=x"}, "user name, password and domain"),
        ({"password": "a\nb"}, "line breaks"),
    ])
    def test_bad_settings(self, client, builtin, scans, mounts, fields, message):
        r = add_share(client, **fields)
        assert r.status_code == 400
        assert message in r.json()["msg"]

    def test_missing_settings(self, client, builtin, scans, mounts):
        r = client.post("/api/system/sources", json={"media": "comic", "kind": "smb"})
        assert r.status_code == 400
        assert r.json()["msg"] == "SMB settings are missing"

    @pytest.mark.parametrize("share", [r"\\NAS\media", "//nas/media/manga/sub"])
    def test_overlapping_share(self, client, builtin, scans, mounts, share):
        assert add_share(client, media="image").status_code == 200
        r = add_share(client, share=share)
        assert r.status_code == 400
        assert "Overlaps the added image share //nas/media/manga" in r.json()["msg"]

    def test_other_folder_of_the_share(self, client, builtin, scans, mounts):
        assert add_share(client).status_code == 200
        assert add_share(client, media="video", share="//nas/media/videos").status_code == 200

    def test_unsupported(self, client, builtin, scans, mounts, monkeypatch):
        monkeypatch.setattr(smb, "unsupported", lambda: "No CIFS here")
        r = add_share(client)
        assert r.status_code == 400
        assert r.json()["msg"] == "No CIFS here"

    def test_unknown_media(self, session, mounts):
        with pytest.raises(sources.SourceError, match="Unknown media"):
            sources.add_smb(session, "audio", sources.SmbSettings(share="//nas/x"))

    def test_local_folder_in_the_mount_root(self, client, builtin, scans, mounts):
        os.makedirs(os.path.join(smb.MOUNT_ROOT, "7"))
        r = client.post("/api/system/sources", json={"media": "comic", "path": os.path.join(smb.MOUNT_ROOT, "7")})
        assert r.status_code == 400
        assert "SMB mounts" in r.json()["msg"]


class TestListShares:
    def test_not_connected(self, client, builtin, scans, mounts):
        id = add_share(client).json()["source"]["id"]
        mounts.mounted.clear()
        [share] = [s for s in client.get("/api/system/sources").json() if s["kind"] == "smb"]
        assert (share["id"], share["status"], share["error"]) == (id, "not_connected", "Not connected yet")
        smb._errors[id] = "Can't reach the server"
        [share] = [s for s in client.get("/api/system/sources").json() if s["kind"] == "smb"]
        assert share["error"] == "Can't reach the server"


class TestUpdateShare:
    def test_changes_settings_and_keeps_the_password(self, client, session, builtin, scans, mounts):
        id = add_share(client).json()["source"]["id"]
        r = client.patch(
            f"/api/system/sources/{id}",
            json={"share": "//nas2/media", "username": "you", "password": "", "options": "vers=2.0"},
        )
        assert r.status_code == 200
        assert r.json()["smb"] == {
            "share": "//nas2/media", "username": "you", "domain": None, "options": "vers=2.0", "hasPassword": True,
        }
        assert r.json()["status"] == "ok"
        session.expire_all()
        assert session.get(MediaSource, id).smbPassword == "secret"
        assert mounts.calls[-1][1] == "//nas2/media"
        assert "password=secret" in mounts.credentials[-1][0]

    def test_failure_keeps_the_old_settings(self, client, session, builtin, scans, mounts):
        id = add_share(client).json()["source"]["id"]
        mounts.fail["//nas2/media"] = (32, "mount error(2): No such file or directory")
        r = client.patch(f"/api/system/sources/{id}", json={"share": "//nas2/media", "password": "new"})
        assert r.status_code == 400
        assert r.json()["msg"].startswith("Can't connect: Share or folder not found")
        session.expire_all()
        row = session.get(MediaSource, id)
        assert (row.smbShare, row.smbPassword) == ("//nas/media/manga", "secret")
        # Reconnected with the old settings.
        assert mounts.calls[-1][1] == "//nas/media/manga"
        assert row.path in mounts.mounted

    def test_not_found(self, client, mounts):
        assert client.patch("/api/system/sources/99", json={"share": "//a/b"}).status_code == 404

    def test_local_source(self, client, session, builtin, mounts, tmp_path):
        row = add_source(session, "comic", tmp_path / "x")
        r = client.patch(f"/api/system/sources/{row.id}", json={"share": "//a/b"})
        assert r.status_code == 400
        assert r.json()["msg"] == "Not an SMB share"


class TestConnectShare:
    def test_reconnects(self, client, builtin, scans, mounts):
        id = add_share(client).json()["source"]["id"]
        r = client.post(f"/api/system/sources/{id}/connect")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"
        assert [c[0] for c in mounts.calls[-2:]] == ["umount", "mount.cifs"]

    def test_failure(self, client, builtin, scans, mounts):
        id = add_share(client).json()["source"]["id"]
        mounts.fail["//nas/media/manga"] = (32, "mount error(112): Host is down")
        r = client.post(f"/api/system/sources/{id}/connect")
        assert r.status_code == 200
        assert r.json()["status"] == "not_connected"
        assert r.json()["error"].startswith("Can't reach the server")

    def test_not_found(self, client, mounts):
        assert client.post("/api/system/sources/99/connect").status_code == 404


class TestRemoveShare:
    def test_unmounts(self, client, session, builtin, scans, mounts):
        source = add_share(client).json()["source"]
        r = client.delete(f"/api/system/sources/{source['id']}")
        assert r.status_code == 200
        assert source["path"] not in mounts.mounted
        assert not os.path.exists(source["path"])
        assert scans == ["comics", "comics"]


class TestSmbSupport:
    def test_supported(self, client, monkeypatch):
        monkeypatch.setattr(smb, "unsupported", lambda: None)
        assert client.get("/api/system/smb").json() == {"supported": True, "reason": None}

    def test_unsupported(self, client, monkeypatch):
        monkeypatch.setattr(smb, "unsupported", lambda: "No mount.cifs")
        assert client.get("/api/system/smb").json() == {"supported": False, "reason": "No mount.cifs"}


class TestScanShares:
    def test_connected_share_is_scanned(self, task_session, builtin, mounts):
        row = share_source(task_session)
        os.makedirs(row.path)
        make_zip_comic(os.path.join(row.path, "a.zip"))
        ComicLoader().work()
        assert task_session.exec(select(ComicEntity.path)).all() == [os.path.join(row.path, "a.zip")]
        assert row.path in mounts.mounted

    def test_share_that_cannot_connect_is_held(self, task_session, builtin, mounts):
        row = share_source(task_session)
        insert_comic(task_session, id=1, path=os.path.join(row.path, "kept.zip"))
        mounts.fail["//nas/media"] = (32, "mount error(112): Host is down")
        progress.start("comics")
        ComicLoader().work()
        task_session.expire_all()
        assert not task_session.get(ComicEntity, 1).missing
        [issue] = [i for i in issues() if i[2] == row.path]
        assert issue[3].startswith("SMB share //nas/media isn't connected: Can't reach the server")


def share_source(session) -> MediaSource:
    row = MediaSource(media="comic", kind="smb", path=smb.new_mount_point(), smbShare="//nas/media")
    session.add(row)
    session.commit()
    session.refresh(row)
    return row
