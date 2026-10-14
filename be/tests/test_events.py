"""ActivityEvent logging (comics only): adds on scan/import, reads on progress, deletes."""
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlmodel import Session, select

import comicfile
import events
import global_data
from conftest import MockComicfile, insert_comic, insert_video, make_zip_comic
from loader import ComicLoader, VideoLoader
from model import ActivityEvent, VideoEntity


def all_events(session: Session):
    session.expire_all()
    return session.exec(select(ActivityEvent).order_by(ActivityEvent.id)).all()


class TestComicDelete:
    def test_archive_logs_delete(self, client, session):
        insert_comic(session, id=1, name="a.zip")
        with patch.object(comicfile, "create_open", return_value=MockComicfile()):
            assert client.delete("/api/comics/1").status_code == 200
        [e] = all_events(session)
        assert (e.kind, e.mediaType, e.entityId) == ("delete", "comic", 1)
        assert e.data == {"name": "a.zip", "size": 1000, "permanent": False}

    def test_permanent_delete_keeps_event(self, client, session):
        insert_comic(session, id=1)
        with patch.object(comicfile, "create_open", return_value=MockComicfile()):
            assert client.delete("/api/comics/1?permanent=true").status_code == 200
        [e] = all_events(session)
        assert e.data["permanent"] is True

    def test_not_found_logs_nothing(self, client, session):
        assert client.delete("/api/comics/99").status_code == 404
        assert all_events(session) == []

    def test_favorited_logs_nothing(self, client, session):
        insert_comic(session, id=1, favorited=True)
        assert client.delete("/api/comics/1").status_code == 400
        assert all_events(session) == []

    def test_failed_file_delete_logs_nothing(self, client, session, tmp_path):
        f = tmp_path / "a.zip"
        f.write_bytes(b"")
        insert_comic(session, id=1, path=str(f))
        with patch.object(comicfile, "create_open", return_value=None), \
                patch("os.remove", side_effect=PermissionError("denied")):
            assert client.delete("/api/comics/1").status_code == 500
        assert all_events(session) == []


class TestVideoDelete:
    def test_not_logged(self, client, session):
        insert_video(session, id=3)
        assert client.delete("/api/videos/3").status_code == 200
        assert all_events(session) == []


class TestComicRead:
    def test_logs_read(self, client, session):
        insert_comic(session, id=1, page=10)
        assert client.put("/api/comics/1/progress", json={"position": 4}).status_code == 200
        [e] = all_events(session)
        assert (e.kind, e.mediaType, e.entityId) == ("read", "comic", 1)
        assert e.data == {"position": 4}

    def test_same_day_updates_one_row_with_furthest_position(self, client, session):
        insert_comic(session, id=1, page=10)
        for position in (4, 8, 2):
            client.put("/api/comics/1/progress", json={"position": position})
        [e] = all_events(session)
        assert e.data == {"position": 8}

    def test_new_day_adds_row(self, client, session):
        insert_comic(session, id=1, page=10)
        session.add(ActivityEvent(
            kind="read", mediaType="comic", entityId=1,
            time=datetime.now() - timedelta(days=1), data={"position": 9},
        ))
        session.commit()
        client.put("/api/comics/1/progress", json={"position": 3})
        assert [e.data["position"] for e in all_events(session)] == [9, 3]

    def test_items_are_counted_separately(self, client, session):
        insert_comic(session, id=1, page=10)
        insert_comic(session, id=2, path="/nonexistent/b.zip", page=10)
        client.put("/api/comics/1/progress", json={"position": 1})
        client.put("/api/comics/2/progress", json={"position": 1})
        assert [e.entityId for e in all_events(session)] == [1, 2]

    def test_rejected_progress_logs_nothing(self, client, session):
        insert_comic(session, id=1, page=10)
        assert client.put("/api/comics/1/progress", json={"position": 11}).status_code == 400
        assert all_events(session) == []


class TestAdd:
    def test_scan_logs_add_per_new_comic(self, task_engine, tmp_path, monkeypatch):
        make_zip_comic(str(tmp_path / "a.zip"), pages=2)
        make_zip_comic(str(tmp_path / "b.zip"), pages=2)
        monkeypatch.setattr(global_data.Config.Comic, "scan_pathes", [str(tmp_path)])
        with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            ComicLoader().work()
            # A rescan finds nothing new and logs nothing more.
            ComicLoader().work()
        with Session(task_engine) as s:
            evs = all_events(s)
        assert sorted(e.data["name"] for e in evs) == ["a.zip", "b.zip"]
        assert {(e.kind, e.mediaType) for e in evs} == {("add", "comic")}

    def test_load_logs_add(self, task_engine, tmp_path):
        f = tmp_path / "c.zip"
        make_zip_comic(str(f), pages=2)
        with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            ComicLoader().load(str(f))
        with Session(task_engine) as s:
            [e] = all_events(s)
        assert (e.kind, e.mediaType, e.data["name"]) == ("add", "comic", "c.zip")

    def test_video_scan_not_logged(self, task_engine, tmp_path, monkeypatch):
        (tmp_path / "v.mp4").write_bytes(b"")
        monkeypatch.setattr(global_data.Config.Video, "scan_pathes", [str(tmp_path)])
        with patch.object(VideoLoader, "_to_entity", lambda self, path: VideoEntity(
                id=self._get_id(), name="v.mp4", path=path, size=0, updateTime=datetime.now())):
            VideoLoader().work()
        with Session(task_engine) as s:
            assert len(s.exec(select(VideoEntity)).all()) == 1
            assert all_events(s) == []


def test_record_read_without_prior_position(task_session):
    task_session.add(ActivityEvent(kind="read", mediaType="comic", entityId=1, data={}))
    task_session.commit()
    events.record_read(task_session, events.COMIC, 1, 5)
    task_session.commit()
    [e] = all_events(task_session)
    assert e.data == {"position": 5}
