"""Tests for converting folder comics into zips (GET/POST /api/comics/zip)."""
import os
import zipfile
from datetime import datetime

import pytest

import comicfile
import zipper
from core.jobs import Job, jobs
from model import ComicEntity
from tests.conftest import insert_comic, make_zip_comic


@pytest.fixture
def root(tmp_path):
    # Apart from the cover folders the client fixture puts in tmp_path.
    root = tmp_path / "library"
    root.mkdir()
    return root


@pytest.fixture
def deferred_jobs(monkeypatch):
    """Start queued jobs only when the test calls the returned function (see
    the fixture of the same name in test_api_move.py)."""
    import core.jobs

    started = []
    monkeypatch.setattr(core.jobs, "_spawn", started.append)

    def run():
        while started:
            started.pop(0)()

    return run


def add_folder(session, root, id, rel, files=("002.jpg", "001.jpg", "info.txt"), **kwargs):
    path = root / rel
    path.mkdir(parents=True)
    for i, name in enumerate(files):
        (path / name).write_bytes(bytes([i]) * (10 + i))
    return insert_comic(session, id=id, name=path.name, path=str(path), **kwargs)


def add_zip(session, root, id, rel):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    make_zip_comic(path)
    return insert_comic(session, id=id, name=path.name, path=str(path))


def run_job(ids):
    job = Job(1, "zip", {"ids": ",".join(map(str, ids))})
    zipper.run(job)
    return job


class TestPreview:
    def test_lists_folder_comics_only(self, client, session, root):
        add_folder(session, root, 1, "b/Folder")
        add_zip(session, root, 2, "a/one.zip")
        add_folder(session, root, 3, "a/Gone", missing=True)
        add_folder(session, root, 4, "a/Deleted", archived=True)
        # A record without a file, and one named like an archive, are skipped.
        insert_comic(session, id=5, name="Nowhere", path=str(root / "Nowhere"))
        add_folder(session, root, 6, "a/Vol.1")
        r = client.get("/api/comics/zip")
        assert r.status_code == 200
        items = r.json()["items"]
        assert [(i["id"], i["status"]) for i in items] == [(6, "zip"), (1, "zip")]
        assert items[1] == {
            "id": 1,
            "name": "Folder",
            "source": str(root / "b" / "Folder"),
            "destination": str(root / "b" / "Folder.zip"),
            "pages": 3,
            "status": "zip",
            "reason": None,
        }

    def test_conflicts(self, client, session, root):
        add_folder(session, root, 1, "Folder")
        (root / "Folder.zip").write_bytes(b"x")
        add_folder(session, root, 2, "Other")
        insert_comic(session, id=3, name="Other.zip", path=str(root / "Other.zip"), missing=True)
        items = client.get("/api/comics/zip").json()["items"]
        assert [(i["id"], i["reason"]) for i in items] == [
            (1, "A file with this name is already there"),
            (2, "Another comic is recorded at this path"),
        ]
        assert {i["status"] for i in items} == {"conflict"}


class TestSubmit:
    def test_queues_and_converts(self, client, session, root, deferred_jobs):
        add_folder(session, root, 1, "Folder")
        add_zip(session, root, 2, "one.zip")
        r = client.post("/api/comics/zip", json={"ids": [1, 2]})
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "started" and body["message"] == "Converting 1 comic(s)"
        job = jobs.snapshot()["queued"][0]
        assert job.params == {"ids": "1", "count": "1"}
        deferred_jobs()
        assert jobs.snapshot()["history"][0].state == "succeeded"
        assert jobs.snapshot()["history"][0].progress == "1 / 1"
        assert (root / "Folder.zip").is_file()

    def test_job_listing_reports_progress(self, client, session, root, deferred_jobs):
        add_folder(session, root, 1, "Folder")
        client.post("/api/comics/zip", json={"ids": [1]})
        deferred_jobs()
        info = client.get("/api/system/jobs").json()["history"][0]
        assert (info["kind"], info["progress"]) == ("zip", "1 / 1")

    def test_already_queued(self, client, session, root, deferred_jobs):
        add_folder(session, root, 1, "Folder")
        jobs.submit("covers", {"mode": "all"})
        assert client.post("/api/comics/zip", json={"ids": [1]}).json()["status"] == "queued"
        assert client.post("/api/comics/zip", json={"ids": [1]}).json()["status"] == "already_queued"
        jobs.reset()  # nothing ran; don't make teardown wait for the queue

    def test_nothing_to_convert(self, client, session, root):
        add_zip(session, root, 1, "one.zip")
        r = client.post("/api/comics/zip", json={"ids": [1, 99]})
        assert r.status_code == 400
        assert r.json()["msg"] == "None of these comics is a folder comic"

    @pytest.mark.parametrize("body", [{"ids": []}, {}])
    def test_bad_request(self, client, body):
        assert client.post("/api/comics/zip", json=body).status_code == 400


class TestRun:
    def test_keeps_the_record(self, client, session, root):
        folder = root / "[Alice] Folder"
        add_folder(session, root, 1, folder.name, favorited=True, lastViewedPosition=2)
        cache_key = str(folder)
        comicfile.create_open(cache_key)
        job = run_job([1])
        assert job.progress == "1 / 1"
        assert not folder.exists()
        dest = root / "[Alice] Folder.zip"
        session.expire_all()
        comic = session.get(ComicEntity, 1)
        assert (comic.path, comic.name) == (str(dest), dest.name)
        assert comic.size == dest.stat().st_size
        assert comic.updateTime == datetime.fromtimestamp(dest.stat().st_mtime)
        assert (comic.favorited, comic.lastViewedPosition, comic.page) == (True, 2, 3)
        # The folder's open handle was dropped from the cache.
        from cachetools.keys import hashkey

        assert hashkey(cache_key) not in comicfile.comic_cache
        # Stored as is, uncompressed, pages in the same order.
        with zipfile.ZipFile(dest) as zf:
            assert {i.compress_type for i in zf.infolist()} == {zipfile.ZIP_STORED}
            assert zf.namelist() == ["001.jpg", "002.jpg", "info.txt"]
            assert zf.read("001.jpg") == bytes([1]) * 11
        assert comicfile.create_open(str(dest)).namelist == ["001.jpg", "002.jpg"]
        assert not [p for p in os.listdir(root) if p.startswith(".")]

    def test_failures_leave_folder_and_record(self, client, session, root):
        add_folder(session, root, 1, "Nested")
        (root / "Nested" / "sub").mkdir()
        add_folder(session, root, 2, "Text", files=("a.txt",))
        add_folder(session, root, 3, "Taken")
        (root / "Taken.zip").write_bytes(b"x")
        add_folder(session, root, 4, "Fine")
        with pytest.raises(RuntimeError) as e:
            run_job([1, 2, 3, 4])
        message = str(e.value)
        assert message.startswith("Converted 1 of 4; ")
        assert "Nested: The folder has subfolders" in message
        assert "Text: The folder has no pages" in message
        assert "Taken: A file with this name is already there" in message
        for name in ("Nested", "Text", "Taken"):
            assert (root / name).is_dir()
        assert (root / "Taken.zip").read_bytes() == b"x"
        assert (root / "Fine.zip").is_file()
        session.expire_all()
        assert session.get(ComicEntity, 1).path == str(root / "Nested")

    def test_bad_zip_is_removed(self, client, session, root, monkeypatch):
        add_folder(session, root, 1, "Folder")
        monkeypatch.setattr(zipfile.ZipFile, "testzip", lambda self: "001.jpg")
        with pytest.raises(RuntimeError, match="001.jpg reads back corrupted"):
            run_job([1])
        assert sorted(os.listdir(root)) == ["Folder"]

    def test_size_mismatch_is_caught(self, client, session, root, monkeypatch):
        add_folder(session, root, 1, "Folder")
        real = os.path.getsize
        monkeypatch.setattr(zipper.os.path, "getsize", lambda p: real(p) + (p.endswith("001.jpg")))
        with pytest.raises(RuntimeError, match="The zip doesn't match the folder"):
            run_job([1])
        assert (root / "Folder").is_dir() and not (root / "Folder.zip").exists()

    def test_destination_taken_while_writing(self, client, session, root, monkeypatch):
        add_folder(session, root, 1, "Folder")
        real = zipfile.ZipFile.testzip

        def testzip(self):
            (root / "Folder.zip").write_bytes(b"x")
            return real(self)

        monkeypatch.setattr(zipfile.ZipFile, "testzip", testzip)
        with pytest.raises(RuntimeError, match="already there"):
            run_job([1])
        assert (root / "Folder.zip").read_bytes() == b"x"
        assert sorted(os.listdir(root)) == ["Folder", "Folder.zip"]

    def test_folder_left_behind_is_a_warning(self, client, session, root, monkeypatch):
        add_folder(session, root, 1, "Folder")

        def rmtree(path):
            raise PermissionError(13, "Permission denied")

        monkeypatch.setattr(zipper.shutil, "rmtree", rmtree)
        with pytest.raises(RuntimeError, match="zipped, but the folder couldn't be deleted"):
            run_job([1])
        session.expire_all()
        assert session.get(ComicEntity, 1).path == str(root / "Folder.zip")

    def test_cancel_stops_between_comics(self, client, session, root, monkeypatch):
        add_folder(session, root, 1, "A")
        add_folder(session, root, 2, "B")
        real = zipper.zip_folder

        def zip_then_cancel(source, dest):
            real(source, dest)
            zipper._cancel.set()

        monkeypatch.setattr(zipper, "zip_folder", zip_then_cancel)
        job = run_job([1, 2])
        assert job.progress == "1 / 2"
        assert (root / "A.zip").exists() and (root / "B").is_dir()

    def test_old_files_are_dated_1980(self, client, session, root):
        add_folder(session, root, 1, "Old")
        os.utime(root / "Old" / "001.jpg", (0, 0))
        run_job([1])
        with zipfile.ZipFile(root / "Old.zip") as zf:
            assert zf.getinfo("001.jpg").date_time[0] == 1980


def test_destination():
    assert zipper.destination("/a/b/") == "/a/b.zip"
