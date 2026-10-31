"""Remapping saved page numbers when the page order changes (pageorder.py)."""
import zipfile
from datetime import datetime
from unittest.mock import patch

from sqlmodel import Session, select

import comicfile
import covers
import pageorder
from api.images import _image_files
from core.jobs import jobs
from loader import ComicLoader
from model import ComicEntity
from tests.conftest import MockComicfile, insert_comic, make_jpeg_bytes

# The old order compared whole names, so the extension's dot sorted after "-".
NAMES = ["000.jpg", "000-00.jpg", "001.jpg"]
OLD = ["000-00.jpg", "000.jpg", "001.jpg"]


def write_zip(path, names=NAMES):
    jpeg = make_jpeg_bytes()
    with zipfile.ZipFile(path, "w") as zf:
        for name in names:
            zf.writestr(name, jpeg)


def outdated(**kwargs) -> ComicEntity:
    fields = dict(id=1, name="a.zip", path="/x/a.zip", size=1, updateTime=datetime.now(), page=3, pageOrder=0)
    return ComicEntity(**{**fields, **kwargs})


class TestOrder:
    def test_order_pages_puts_the_bare_name_first(self):
        assert comicfile.order_pages(reversed(NAMES)) == NAMES
        assert comicfile.legacy_order_pages(NAMES) == OLD

    def test_versions_differ_only_where_the_order_changed(self):
        names = ["0001.jpg", "0002.jpg", "0010.jpg"]
        assert comicfile.order_pages(names) == comicfile.legacy_order_pages(names) == names

    def test_new_records_use_the_current_order(self):
        fresh = ComicEntity(id=2, name="b", path="b", size=1, updateTime=datetime.now())
        assert fresh.pageOrder == comicfile.PAGE_ORDER_VERSION

    def test_page_order_is_not_in_api_responses(self, client, session):
        insert_comic(session, 1)
        assert "pageOrder" not in client.get("/api/comics/1").json()

    def test_image_albums_use_the_same_order(self, tmp_path):
        for name in ["10.jpg", "2.jpg", "000-00.jpg", "000.jpg", "notes.txt"]:
            (tmp_path / name).write_bytes(b"x")
        assert _image_files(str(tmp_path)) == ["000.jpg", "000-00.jpg", "2.jpg", "10.jpg"]


class TestMigrate:
    def test_remaps_cover_and_progress_by_page_name(self):
        comic = outdated(coverPosition=1, lastViewedPosition=2)
        assert pageorder.migrate(comic, NAMES)
        # Old page 1 was 000-00.jpg, now page 2; old page 2 was 000.jpg, now page 1.
        assert (comic.coverPosition, comic.lastViewedPosition) == (2, 1)
        assert comic.pageOrder == comicfile.PAGE_ORDER_VERSION

    def test_finished_comic_stays_finished(self):
        names = ["1.jpg", "1-1.jpg"]  # old order: 1-1, 1; new: 1, 1-1
        comic = outdated(lastViewedPosition=2, page=2)
        assert not pageorder.migrate(comic, names)
        assert comic.lastViewedPosition == 2

    def test_unset_and_out_of_range_numbers_are_kept(self):
        comic = outdated(coverPosition=0, lastViewedPosition=9)
        assert not pageorder.migrate(comic, NAMES)
        assert (comic.coverPosition, comic.lastViewedPosition) == (0, 9)
        assert comic.pageOrder == comicfile.PAGE_ORDER_VERSION

    def test_unchanged_order_reports_no_change(self):
        comic = outdated(coverPosition=2, lastViewedPosition=1)
        assert not pageorder.migrate(comic, ["1.jpg", "2.jpg", "3.jpg"])
        assert (comic.coverPosition, comic.lastViewedPosition) == (2, 1)

    def test_current_record_is_left_alone(self):
        comic = outdated(coverPosition=1)
        comic.pageOrder = comicfile.PAGE_ORDER_VERSION
        assert not pageorder.migrate(comic, NAMES)
        assert not pageorder.migrate_from_file(comic)
        assert comic.coverPosition == 1

    def test_from_file_reads_the_pages(self, tmp_path):
        write_zip(tmp_path / "a.zip")
        comic = outdated(coverPosition=1)
        comic.path = str(tmp_path / "a.zip")
        assert pageorder.migrate_from_file(comic)
        assert comic.coverPosition == 2

    def test_from_file_without_numbers_needs_no_file(self):
        comic = outdated()
        assert not pageorder.migrate_from_file(comic)
        assert comic.pageOrder == comicfile.PAGE_ORDER_VERSION

    def test_from_file_keeps_unreadable_records_outdated(self, tmp_path):
        comic = outdated(coverPosition=1)
        assert not pageorder.migrate_from_file(comic)  # no such file
        broken = tmp_path / "broken.zip"
        broken.write_bytes(b"not a zip")
        comic.path = str(broken)
        assert not pageorder.migrate_from_file(comic)
        assert (comic.pageOrder, comic.coverPosition) == (0, 1)


class TestJob:
    def test_remaps_every_outdated_record(self, client, session, tmp_path):
        write_zip(tmp_path / "a.zip")
        insert_comic(session, 1, path=str(tmp_path / "a.zip"), pageOrder=0, coverPosition=1, lastViewedPosition=2)
        insert_comic(session, 2, path=str(tmp_path / "gone.zip"), pageOrder=0, lastViewedPosition=1)
        insert_comic(session, 3, path=str(tmp_path / "gone.zip"), pageOrder=0)
        insert_comic(session, 4, path=str(tmp_path / "a.zip"), coverPosition=1)  # current already

        _, status = pageorder.submit()
        assert status == "started"
        assert jobs.wait_idle(10)

        session.expire_all()
        rows = {c.id: (c.pageOrder, c.coverPosition, c.lastViewedPosition) for c in session.exec(select(ComicEntity))}
        v = comicfile.PAGE_ORDER_VERSION
        assert rows == {1: (v, 2, 1), 2: (0, 0, 1), 3: (v, 0, 0), 4: (v, 1, 0)}
        job = client.get("/api/system/jobs").json()["history"][0]
        assert (job["kind"], job["state"]) == ("page-order", "succeeded")
        assert job["progress"] == "2 / 2, 1 unreadable (retried on next start)"

    def test_startup_queues_only_when_needed(self, client, session):
        insert_comic(session, 1)
        assert pageorder.submit_if_needed() == "not needed"
        assert jobs.wait_idle(10)
        assert client.get("/api/system/jobs").json()["history"] == []

        insert_comic(session, 2, pageOrder=0)
        insert_comic(session, 3, pageOrder=0)
        assert pageorder.submit_if_needed() == "started for 2 comic(s)"
        assert jobs.wait_idle(10)
        assert pageorder.outdated_count() == 0
        assert pageorder.submit_if_needed() == "not needed"

    def test_skips_a_record_deleted_meanwhile(self, client, session):
        insert_comic(session, 1, pageOrder=0, coverPosition=1)
        real_get = Session.get
        with patch.object(Session, "get", lambda self, cls, id: None if cls is ComicEntity else real_get(self, cls, id)):
            pageorder.submit()
            assert jobs.wait_idle(10)
        assert client.get("/api/system/jobs").json()["history"][0]["progress"] == "1 / 1"


class TestEndpoints:
    def test_progress_save_remaps_the_cover_first(self, client, session, tmp_path):
        write_zip(tmp_path / "a.zip")
        insert_comic(session, 1, path=str(tmp_path / "a.zip"), pageOrder=0, coverPosition=1, lastViewedPosition=3)
        assert client.put("/api/comics/1/progress", json={"position": 1}).status_code == 200
        session.expire_all()
        comic = session.get(ComicEntity, 1)
        assert (comic.pageOrder, comic.coverPosition, comic.lastViewedPosition) == (1, 2, 1)

    def test_set_cover_remaps_progress_first(self, client, session):
        insert_comic(session, 1, pageOrder=0, lastViewedPosition=1)
        mock_cf = MockComicfile(names=NAMES)
        with patch("comicfile.create_open", return_value=mock_cf), \
                patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            assert client.post("/api/comics/1/pages/3/cover").status_code == 200
        session.expire_all()
        comic = session.get(ComicEntity, 1)
        assert (comic.pageOrder, comic.coverPosition, comic.lastViewedPosition) == (1, 3, 2)

    def test_cover_run_uses_the_remapped_page(self, tmp_path):
        write_zip(tmp_path / "a.zip")
        comic = outdated(coverPosition=1)
        comic.path = str(tmp_path / "a.zip")
        pages = []
        with patch.object(ComicLoader, "gen_comic_cover", side_effect=lambda c, cf, o, p: pages.append(p) or True):
            covers._refresh(comic)
        assert pages == [1]  # 0-based: 000-00.jpg is the second page now
        assert comic.pageOrder == comicfile.PAGE_ORDER_VERSION
