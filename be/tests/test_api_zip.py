"""Tests for converting folder comics into zips (GET/POST /api/comics/zip)."""
import os
import zipfile
import zlib
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
            "kind": "folder",
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
        assert r.json()["msg"] == "None of these comics is a folder comic or RAR"

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
        with pytest.raises(RuntimeError, match="The zip doesn't match the original"):
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
    assert zipper.destination("/a/Vol.1") == "/a/Vol.1.zip"
    assert zipper.destination("/a/B.RAR") == "/a/B.zip"


# --- RARs -------------------------------------------------------------------
# CI has no 7-Zip, so RarFile and the extraction are faked: FakeRar lists what
# the archive holds, and the fake extraction writes it out.


class Info:
    def __init__(self, filename, data=b"", kind="file", crc=None):
        self.filename = filename
        self.data = data
        self.file_size = len(data)
        self.CRC = zlib.crc32(data) if crc is None else crc
        self.kind = kind

    def is_file(self):
        return self.kind == "file"

    def is_dir(self):
        return self.kind == "dir"

    def is_symlink(self):
        return self.kind == "link"


class FakeRar:
    def __init__(self, infos, encrypted=False, volumes=1):
        self.infos, self.encrypted, self.volumes = infos, encrypted, volumes

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def needs_password(self):
        return self.encrypted

    def volumelist(self):
        return ["x"] * self.volumes

    def infolist(self):
        return self.infos


PAGES = [Info("Title/", kind="dir"), Info("Title/002.jpg", b"b" * 20), Info("Title/001.jpg", b"a" * 10)]


@pytest.fixture
def fake_rar(monkeypatch):
    """Make every RAR hold ``holds["infos"]``; the extraction writes their data
    (``holds["written"]`` overrides what lands on disk)."""
    holds = {"infos": PAGES, "rar": {}, "written": None}
    monkeypatch.setattr(zipper.rarfile, "RarFile", lambda path: FakeRar(holds["infos"], **holds["rar"]))

    def extract(source, target):
        written = holds["written"] or {i.filename: i.data for i in holds["infos"] if i.is_file()}
        for name, data in written.items():
            path = os.path.join(target, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)

    monkeypatch.setattr(zipper, "_extract", extract)
    return holds


def add_rar(session, root, id, rel, **kwargs):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"Rar!")
    return insert_comic(session, id=id, name=path.name, path=str(path), **kwargs)


class TestRar:
    def test_preview(self, client, session, root):
        add_rar(session, root, 1, "a/One.rar")
        add_rar(session, root, 2, "b/Same.RAR")
        add_folder(session, root, 3, "b/Same")
        # A RAR record without its file isn't offered.
        insert_comic(session, id=4, name="Gone.rar", path=str(root / "Gone.rar"))
        items = client.get("/api/comics/zip").json()["items"]
        assert [(i["id"], i["kind"], i["destination"], i["status"]) for i in items] == [
            (1, "rar", str(root / "a" / "One.zip"), "zip"),
            (3, "folder", str(root / "b" / "Same.zip"), "zip"),
            (2, "rar", str(root / "b" / "Same.zip"), "conflict"),
        ]
        assert items[2]["reason"] == "Another comic here converts to the same name"

    def test_converts_and_keeps_the_record(self, client, session, root, fake_rar):
        add_rar(session, root, 1, "[Bob] One.rar", favorited=True)
        job = run_job([1])
        assert job.progress == "1 / 1"
        dest = root / "[Bob] One.zip"
        assert not (root / "[Bob] One.rar").exists()
        session.expire_all()
        comic = session.get(ComicEntity, 1)
        assert (comic.path, comic.name, comic.favorited) == (str(dest), dest.name, True)
        assert comic.size == dest.stat().st_size
        with zipfile.ZipFile(dest) as zf:
            assert zf.namelist() == ["Title/001.jpg", "Title/002.jpg"]
            assert {i.compress_type for i in zf.infolist()} == {zipfile.ZIP_STORED}
            assert zf.read("Title/002.jpg") == b"b" * 20
        assert not [p for p in os.listdir(root) if p.startswith(".")]

    @pytest.mark.parametrize(
        "infos, rar, reason",
        [
            (PAGES, {"encrypted": True}, "The archive is encrypted"),
            (PAGES, {"volumes": 2}, "Multi-volume archives aren't converted"),
            (PAGES + [Info("Title/x", kind="link")], {}, "The archive has links"),
            ([Info("../001.jpg", b"x")], {}, "Unsafe name in the archive: ../001.jpg"),
            ([Info("/abs/001.jpg", b"x")], {}, "Unsafe name in the archive: /abs/001.jpg"),
            ([Info("C:/001.jpg", b"x")], {}, "Unsafe name in the archive: C:/001.jpg"),
            ([Info("a.jpg", b"x"), Info("a.jpg", b"y")], {}, "The archive has duplicate names"),
            ([Info("notes.txt", b"x")], {}, "The archive has no pages"),
        ],
    )
    def test_refused(self, client, session, root, fake_rar, infos, rar, reason):
        fake_rar.update(infos=infos, rar=rar)
        add_rar(session, root, 1, "One.rar")
        with pytest.raises(RuntimeError) as e:
            run_job([1])
        assert str(e.value) == f"Converted 0 of 1; One.rar: {reason}"
        assert sorted(os.listdir(root)) == ["One.rar"]

    def test_unreadable_archive(self, client, session, root, monkeypatch):
        def broken(path):
            raise zipper.rarfile.BadRarFile("Not a RAR file")

        monkeypatch.setattr(zipper.rarfile, "RarFile", broken)
        add_rar(session, root, 1, "One.rar")
        with pytest.raises(RuntimeError, match=r"Can't read the archive \(BadRarFile: Not a RAR file\)"):
            run_job([1])

    def test_crc_mismatch(self, client, session, root, fake_rar):
        fake_rar["infos"] = [Info("001.jpg", b"a" * 10, crc=1)]
        add_rar(session, root, 1, "One.rar")
        with pytest.raises(RuntimeError, match="The zip doesn't match the original"):
            run_job([1])
        assert sorted(os.listdir(root)) == ["One.rar"]

    def test_missing_extracted_file(self, client, session, root, fake_rar):
        fake_rar["written"] = {"Title/001.jpg": b"a" * 10}
        add_rar(session, root, 1, "One.rar")
        with pytest.raises(RuntimeError, match="No such file"):
            run_job([1])
        assert sorted(os.listdir(root)) == ["One.rar"]

    def test_extracted_link_is_refused(self, client, session, root, fake_rar, monkeypatch):
        fake_rar["infos"] = [Info("001.jpg", b"a")]

        def extract(source, target):
            os.symlink("/etc/hostname", os.path.join(target, "001.jpg"))

        monkeypatch.setattr(zipper, "_extract", extract)
        add_rar(session, root, 1, "One.rar")
        with pytest.raises(RuntimeError, match="Unsafe name in the archive: 001.jpg"):
            run_job([1])

    def test_rar_left_behind_is_a_warning(self, client, session, root, fake_rar, monkeypatch):
        add_rar(session, root, 1, "One.rar")
        real = os.remove

        def remove(path):
            if str(path).endswith("One.rar"):
                raise PermissionError(13, "Permission denied")
            real(path)

        monkeypatch.setattr(zipper.os, "remove", remove)
        with pytest.raises(RuntimeError, match="zipped, but the rar couldn't be deleted"):
            run_job([1])
        session.expire_all()
        assert session.get(ComicEntity, 1).path == str(root / "One.zip")


class TestExtract:
    """zipper._extract runs 7-Zip; a stand-in script plays it here."""

    @pytest.fixture
    def tool(self, tmp_path, monkeypatch):
        bin = tmp_path / "bin"
        bin.mkdir()
        monkeypatch.setenv("PATH", str(bin))

        def install(script):
            path = bin / "7zz"
            path.write_text("#!/bin/sh\n" + script)
            path.chmod(0o755)

        return install

    def test_one_run_extracts_everything(self, tool, tmp_path):
        # Prints its arguments and locale, and writes a file where -o points.
        tool('for a; do echo "$a"; done > "$ARGS_OUT"; echo "$LC_ALL" >> "$ARGS_OUT"\n'
             'out="${4#-o}"; echo x > "$out/001.jpg"\n')
        args_out = tmp_path / "args"
        os.environ["ARGS_OUT"] = str(args_out)
        try:
            zipper._extract("/lib/One.rar", str(tmp_path))
        finally:
            del os.environ["ARGS_OUT"]
        assert args_out.read_text().split("\n")[:-1] == [
            "x", "-y", "-bd", f"-o{tmp_path}", "--", "/lib/One.rar", "C.UTF-8",
        ]
        assert (tmp_path / "001.jpg").read_text() == "x\n"

    def test_failure_reports_the_last_line(self, tool, tmp_path):
        tool('echo "Scanning" >&2; echo "ERROR: CRC Failed : 012.jpg" >&2; exit 2\n')
        with pytest.raises(zipper.ZipError, match="Extracting failed: ERROR: CRC Failed : 012.jpg"):
            zipper._extract("/lib/One.rar", str(tmp_path))

    def test_silent_failure(self, tool, tmp_path):
        tool("exit 7\n")
        with pytest.raises(zipper.ZipError, match="Extracting failed: exit code 7"):
            zipper._extract("/lib/One.rar", str(tmp_path))

    def test_no_tool(self, tmp_path, monkeypatch):
        monkeypatch.setenv("PATH", str(tmp_path))
        with pytest.raises(zipper.ZipError, match=r"No RAR extractor \(7zz\) is installed"):
            zipper._extract("/lib/One.rar", str(tmp_path))
