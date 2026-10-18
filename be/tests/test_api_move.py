"""Tests for moving comics into a folder (POST /api/comics/move[/preview])."""
import errno
import os

import pytest
from sqlmodel import Session

import comicfile
import global_data
import mover
from core.jobs import Job, jobs
from model import ComicEntity
from tests.conftest import insert_comic, make_zip_comic


@pytest.fixture
def root(tmp_path, monkeypatch):
    root = tmp_path / "library"
    root.mkdir()
    monkeypatch.setattr(global_data.Config.Comic, "scan_pathes", [str(root)])
    monkeypatch.setattr(mover, "in_container_fs", lambda path: False)
    return root


def add_zip(session, root, id, rel):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    make_zip_comic(path)
    return insert_comic(session, id=id, name=path.name, path=str(path))


def add_folder(session, root, id, rel):
    path = root / rel
    path.mkdir(parents=True)
    (path / "001.jpg").write_bytes(b"x" * 10)
    (path / "002.jpg").write_bytes(b"y" * 20)
    return insert_comic(session, id=id, name=path.name, path=str(path))


def path_of(engine, id):
    with Session(engine) as s:
        return s.get(ComicEntity, id).path


def run_job(target, ids):
    mover.run(Job(1, "move", {"target": str(target), "ids": ",".join(map(str, ids))}))


# ---------------------------------------------------------------------------
# Preview
# ---------------------------------------------------------------------------

class TestPreview:
    def test_statuses(self, client, session, root):
        add_zip(session, root, 1, "a/one.zip")
        add_zip(session, root, 2, "Author/two.zip")
        add_zip(session, root, 3, "b/three.zip")
        (root / "Author" / "three.zip").write_bytes(b"taken")
        add_zip(session, root, 4, "a/four.zip")
        add_zip(session, root, 5, "b/four.zip")
        insert_comic(session, id=6, name="gone.zip", path=str(root / "x" / "gone.zip"))
        target = root / "Author"
        r = client.post(
            "/api/comics/move/preview",
            json={"ids": [1, 2, 3, 4, 5, 6, 99, 1], "target": str(target) + "/"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["target"] == str(target)
        status = {i["id"]: (i["status"], i.get("reason")) for i in body["items"]}
        assert len(body["items"]) == 7  # the repeated id is planned once
        assert status[1] == ("move", None)
        assert status[2] == ("same", None)
        assert status[3] == ("conflict", "A file with this name is already there")
        assert status[4] == ("move", None)
        assert status[5] == ("conflict", "Another selected comic has the same name")
        assert status[6] == ("missing", None)
        assert status[99] == ("notfound", None)
        one = next(i for i in body["items"] if i["id"] == 1)
        assert one["source"] == str(root / "a" / "one.zip")
        assert one["destination"] == str(target / "one.zip")
        assert one["crossDevice"] is False
        # Nothing changed on disk.
        assert (root / "a" / "one.zip").exists()
        assert not target.joinpath("one.zip").exists()

    def test_recorded_path_conflict(self, client, session, root):
        add_zip(session, root, 1, "a/one.zip")
        insert_comic(session, id=2, name="one.zip", path=str(root / "Author" / "one.zip"), missing=True)
        r = client.post(
            "/api/comics/move/preview", json={"ids": [1], "target": str(root / "Author")}
        )
        assert r.json()["items"][0]["reason"] == "Another comic is recorded at this path"

    def test_target_inside_moved_folder(self, client, session, root):
        add_folder(session, root, 1, "a/Folder Comic")
        add_zip(session, root, 2, "a/two.zip")
        # The target is checked against folder comics first...
        r = client.post(
            "/api/comics/move/preview",
            json={"ids": [2], "target": str(root / "a" / "Folder Comic" / "sub")},
        )
        assert r.status_code == 400
        assert "inside the folder comic" in r.json()["msg"]

    def test_cross_device_flag(self, client, session, root, monkeypatch):
        add_zip(session, root, 1, "a/one.zip")
        target = str(root / "b")
        monkeypatch.setattr(mover, "_device", lambda p: 2 if p == target else 1)
        r = client.post("/api/comics/move/preview", json={"ids": [1], "target": target})
        assert r.json()["items"][0]["crossDevice"] is True

    @pytest.mark.parametrize(
        "target, message",
        [
            ("", "absolute"),
            ("relative/dir", "absolute"),
            ("/elsewhere/Author", "inside a comic scan folder"),
        ],
    )
    def test_bad_target(self, client, session, root, target, message):
        add_zip(session, root, 1, "a/one.zip")
        r = client.post("/api/comics/move/preview", json={"ids": [1], "target": target})
        assert r.status_code == 400
        assert message in r.json()["msg"]

    def test_target_is_file(self, client, session, root):
        add_zip(session, root, 1, "a/one.zip")
        r = client.post(
            "/api/comics/move/preview", json={"ids": [1], "target": str(root / "a" / "one.zip")}
        )
        assert r.status_code == 400
        assert "not a folder" in r.json()["msg"]

    def test_target_in_container_fs(self, client, session, root, monkeypatch):
        add_zip(session, root, 1, "a/one.zip")
        monkeypatch.setattr(mover, "in_container_fs", lambda path: True)
        r = client.post(
            "/api/comics/move/preview", json={"ids": [1], "target": str(root / "Author")}
        )
        assert r.status_code == 400
        assert "mounted drive" in r.json()["msg"]

    def test_empty_ids(self, client, root):
        r = client.post("/api/comics/move/preview", json={"ids": [], "target": str(root)})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------

class TestMove:
    def test_moves_and_keeps_records(self, engine_and_client, session, root):
        engine, client = engine_and_client
        add_zip(session, root, 1, "a/one.zip")
        add_folder(session, root, 2, "b/Two")
        add_zip(session, root, 3, "Author/three.zip")
        target = root / "Author"
        r = client.post("/api/comics/move", json={"ids": [1, 2, 3], "target": str(target)})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "started"
        assert body["message"] == "Moving 2 comic(s)"
        assert jobs.wait_idle(10)
        job = jobs.snapshot()["history"][0]
        assert (job.id, job.kind, job.state) == (body["jobId"], "move", "succeeded")
        assert job.params["count"] == "2"
        assert path_of(engine, 1) == str(target / "one.zip")
        assert path_of(engine, 2) == str(target / "Two")
        assert (target / "one.zip").is_file()
        assert (target / "Two" / "002.jpg").read_bytes() == b"y" * 20
        assert not (root / "a" / "one.zip").exists()
        assert not (root / "b" / "Two").exists()

    def test_nothing_to_move(self, client, session, root):
        add_zip(session, root, 1, "Author/one.zip")
        r = client.post("/api/comics/move", json={"ids": [1], "target": str(root / "Author")})
        assert r.status_code == 400
        assert r.json()["msg"] == "Nothing to move"

    def test_bad_target(self, client, session, root):
        add_zip(session, root, 1, "a/one.zip")
        r = client.post("/api/comics/move", json={"ids": [1], "target": "/elsewhere"})
        assert r.status_code == 400

    def test_queued_behind_running_job(self, client, session, root, monkeypatch):
        add_zip(session, root, 1, "a/one.zip")
        monkeypatch.setattr(mover.jobs, "submit", lambda kind, params: (Job(7, kind, params), "queued"))
        r = client.post("/api/comics/move", json={"ids": [1], "target": str(root / "Author")})
        assert r.json() == {
            "jobId": 7, "status": "queued", "message": "Moving 1 comic(s) after the running job",
        }

    def test_listed_in_jobs(self, client, session, root):
        add_zip(session, root, 1, "a/one.zip")
        client.post("/api/comics/move", json={"ids": [1], "target": str(root / "Author")})
        assert jobs.wait_idle(10)
        info = client.get("/api/system/jobs").json()["history"][0]
        assert info["kind"] == "move"
        assert info["params"]["target"] == str(root / "Author")


# ---------------------------------------------------------------------------
# The job itself
# ---------------------------------------------------------------------------

class TestRun:
    def test_conflict_at_run_time_fails_job(self, engine_and_client, session, root):
        engine, _ = engine_and_client
        add_zip(session, root, 1, "a/one.zip")
        add_zip(session, root, 2, "a/two.zip")
        (root / "Author").mkdir()
        (root / "Author" / "two.zip").write_bytes(b"taken")
        with pytest.raises(RuntimeError, match=r"Moved 1 of 2; two.zip: A file with this name"):
            run_job(root / "Author", [1, 2])
        assert path_of(engine, 1) == str(root / "Author" / "one.zip")
        assert path_of(engine, 2) == str(root / "a" / "two.zip")

    def test_rename_error_is_reported(self, engine_and_client, session, root, monkeypatch):
        engine, _ = engine_and_client
        add_zip(session, root, 1, "a/one.zip")

        def denied(src, dst):
            raise PermissionError(errno.EACCES, "Permission denied")

        monkeypatch.setattr(mover.os, "rename", denied)
        with pytest.raises(RuntimeError, match="Moved 0 of 1; one.zip: Permission denied"):
            run_job(root / "Author", [1])
        assert path_of(engine, 1) == str(root / "a" / "one.zip")

    def test_skips_same_and_notfound(self, engine_and_client, session, root):
        add_zip(session, root, 1, "Author/one.zip")
        run_job(root / "Author", [1, 99])  # nothing to do, no error

    def test_evicts_cached_handle(self, engine_and_client, session, root):
        comic = add_zip(session, root, 1, "a/one.zip")
        cf = comicfile.create_open(comic.path)
        closed = []
        cf.close = lambda: closed.append(True)
        run_job(root / "Author", [1])
        assert closed == [True]
        assert len(comicfile.comic_cache) == 0


class TestCrossDevice:
    @pytest.fixture
    def exdev(self, monkeypatch):
        """Renames out of the source folder fail like a cross-filesystem move."""
        real = os.rename

        def rename(src, dst):
            if os.path.basename(os.path.dirname(src)) == "a":
                raise OSError(errno.EXDEV, "Invalid cross-device link")
            real(src, dst)

        monkeypatch.setattr(mover.os, "rename", rename)

    def test_copies_file_and_folder(self, engine_and_client, session, root, exdev):
        engine, _ = engine_and_client
        add_zip(session, root, 1, "a/one.zip")
        add_folder(session, root, 2, "a/Two")
        size = os.path.getsize(root / "a" / "one.zip")
        run_job(root / "Author", [1, 2])
        target = root / "Author"
        assert os.path.getsize(target / "one.zip") == size
        assert (target / "Two" / "001.jpg").read_bytes() == b"x" * 10
        assert sorted(os.listdir(target)) == ["Two", "one.zip"]  # no leftover part files
        assert os.listdir(root / "a") == []
        assert path_of(engine, 1) == str(target / "one.zip")
        assert path_of(engine, 2) == str(target / "Two")

    def test_failed_copy_keeps_original(self, engine_and_client, session, root, exdev, monkeypatch):
        engine, _ = engine_and_client
        add_zip(session, root, 1, "a/one.zip")

        def broken_copy(src, dst):
            open(dst, "wb").write(b"partial")
            raise OSError(errno.EIO, "Input/output error")

        monkeypatch.setattr(mover.shutil, "copy2", broken_copy)
        with pytest.raises(RuntimeError, match="Input/output error"):
            run_job(root / "Author", [1])
        assert (root / "a" / "one.zip").exists()
        assert os.listdir(root / "Author") == []
        assert path_of(engine, 1) == str(root / "a" / "one.zip")

    def test_incomplete_copy_is_rejected(self, engine_and_client, session, root, exdev, monkeypatch):
        engine, _ = engine_and_client
        add_zip(session, root, 1, "a/one.zip")
        real_size = mover._size
        monkeypatch.setattr(
            mover, "_size", lambda p: 0 if ".organizer-part" in p else real_size(p)
        )
        with pytest.raises(RuntimeError, match="copy is incomplete"):
            run_job(root / "Author", [1])
        assert (root / "a" / "one.zip").exists()
        assert os.listdir(root / "Author") == []
        assert path_of(engine, 1) == str(root / "a" / "one.zip")

    def test_original_not_deleted_is_a_warning(self, engine_and_client, session, root, exdev, monkeypatch):
        engine, _ = engine_and_client
        add_zip(session, root, 1, "a/one.zip")
        real_remove = mover._remove

        def remove(path):
            if path.endswith(os.path.join("a", "one.zip")):
                raise PermissionError(errno.EACCES, "Permission denied")
            real_remove(path)

        monkeypatch.setattr(mover, "_remove", remove)
        with pytest.raises(RuntimeError, match=r"Moved 1 of 1; one.zip: copied, but the original"):
            run_job(root / "Author", [1])
        # The copy is the comic now.
        assert path_of(engine, 1) == str(root / "Author" / "one.zip")
        assert (root / "Author" / "one.zip").exists()


class TestHelpers:
    def test_container_fs(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mover, "_mount_point", lambda path: "/")
        real_exists = os.path.exists
        monkeypatch.setattr(
            mover.os.path, "exists", lambda p: p == "/.dockerenv" or real_exists(p)
        )
        assert mover.in_container_fs(str(tmp_path / "new"))
        monkeypatch.setattr(mover, "_mount_point", lambda path: "/data/comics")
        assert not mover.in_container_fs(str(tmp_path / "new"))

    def test_not_in_container(self, tmp_path, monkeypatch):
        real_exists = os.path.exists
        monkeypatch.setattr(
            mover.os.path, "exists", lambda p: p != "/.dockerenv" and real_exists(p)
        )
        assert not mover.in_container_fs(str(tmp_path))

    def test_mount_point_of_missing_path(self, tmp_path):
        assert os.path.ismount(mover._mount_point(str(tmp_path / "does" / "not" / "exist")))

    def test_remove_ignores_missing(self, tmp_path):
        mover._remove(str(tmp_path / "nothing"))

    def test_inside_mixed_paths(self):
        assert not mover._inside("relative", "/abs")


# ---------------------------------------------------------------------------
# Suggested target and the artist folder
# ---------------------------------------------------------------------------

class TestSuggest:
    def test_artist_folder_by_default(self, client, session, root):
        add_zip(session, root, 1, "inbox/[Alice] One.zip")
        r = client.post("/api/comics/move/suggest", json={"ids": [1], "name": " Alice "})
        assert r.status_code == 200
        assert r.json() == {"target": str(root / "artist" / "Alice")}

    def test_configured_artist_folder(self, client, session, root, monkeypatch, tmp_path):
        add_zip(session, root, 1, "inbox/[A] One.zip")
        monkeypatch.setattr(global_data.Config.Comic, "artist_path", str(tmp_path / "authors"))
        r = client.post("/api/comics/move/suggest", json={"ids": [1], "name": "A/B"})
        assert r.json()["target"] == str(tmp_path / "authors" / "A_B")

    def test_prefers_existing_folder_of_that_name(self, client, session, root):
        add_zip(session, root, 1, "inbox/[Alice] One.zip")
        add_zip(session, root, 2, "old/Alice/[Alice] Two.zip")
        add_zip(session, root, 3, "nas/Alice/[Alice] Three.zip")
        add_zip(session, root, 4, "nas/Alice/[Alice] Four.zip")
        r = client.post(
            "/api/comics/move/suggest", json={"ids": [1, 2, 3, 4, 99], "name": "Alice"}
        )
        assert r.json()["target"] == str(root / "nas" / "Alice")

    def test_unusable_name(self, client, session, root):
        add_zip(session, root, 1, "inbox/one.zip")
        r = client.post("/api/comics/move/suggest", json={"ids": [1], "name": " .. "})
        assert r.json()["target"] == ""

    def test_empty_ids(self, client):
        r = client.post("/api/comics/move/suggest", json={"ids": [], "name": "A"})
        assert r.status_code == 400


class TestUnmountedWarning:
    def test_scan_warns_about_unmounted_paths(self, client, root, monkeypatch):
        from core.jobs import jobs as queue
        from core.scan_progress import progress
        import loader

        monkeypatch.setattr(loader.ComicLoader, "work", lambda self: None)
        monkeypatch.setattr(mover, "in_container_fs", lambda p: p.endswith("artist"))
        r = client.post("/api/system/scan", params={"media_type": "comics"})
        assert r.status_code == 200
        assert queue.wait_idle(10)
        issues = progress.snapshot()["issues"]
        assert [(i["level"], i["path"]) for i in issues] == [("warning", str(root / "artist"))]
        assert "Not on a mounted drive" in issues[0]["reason"]

    def test_folder_name(self):
        assert mover.folder_name(' A:B*C?"D<E>F|G\x01 ') == "A_B_C__D_E_F_G_"
        assert mover.folder_name("Name. .") == "Name"
