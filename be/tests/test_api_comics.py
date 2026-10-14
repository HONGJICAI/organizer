from datetime import datetime, timedelta
from unittest.mock import patch

import pytest


import comicfile
from conftest import MockComicfile, insert_comic, make_zip_comic
from loader import ComicLoader
from model import ActivityEvent, ComicEntity
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


# ---------------------------------------------------------------------------
# GET /api/comics/duplicates
# ---------------------------------------------------------------------------

class TestDuplicates:
    def test_empty(self, client):
        r = client.get("/api/comics/duplicates")
        assert r.status_code == 200
        assert r.json() == {"groups": []}

    def test_groups_tagged_copies(self, client, session):
        insert_comic(session, 1, name="[GroupA] Title 01 [DL版].zip", page=20)
        insert_comic(session, 2, name="[GroupB] Title 1.rar", page=24)
        insert_comic(session, 3, name="Title 02.zip")
        insert_comic(session, 4, name="Unrelated.zip")
        r = client.get("/api/comics/duplicates")
        assert r.status_code == 200
        groups = r.json()["groups"]
        assert len(groups) == 1
        assert groups[0]["exact"] is True
        assert sorted(c["id"] for c in groups[0]["items"]) == [1, 2]
        assert groups[0]["keepId"] == 2

    def test_keep_prefers_favorited(self, client, session):
        insert_comic(session, 1, name="[A] Title.zip", page=50)
        insert_comic(session, 2, name="[B] Title.zip", page=10, favorited=True)
        groups = client.get("/api/comics/duplicates").json()["groups"]
        assert groups[0]["keepId"] == 2

    def test_similar_names_depend_on_threshold(self, client, session):
        insert_comic(session, 1, name="Some Long English Title.zip")
        insert_comic(session, 2, name="Some Long English Titel.zip")
        groups = client.get("/api/comics/duplicates").json()["groups"]
        assert len(groups) == 1
        assert groups[0]["exact"] is False
        r = client.get("/api/comics/duplicates", params={"threshold": 1.0})
        assert r.json()["groups"] == []

    def test_excludes_archived_and_missing(self, client, session):
        insert_comic(session, 1, name="[A] Title.zip")
        insert_comic(session, 2, name="[B] Title.zip", archived=True)
        insert_comic(session, 3, name="[C] Title.zip", missing=True)
        assert client.get("/api/comics/duplicates").json()["groups"] == []

    def test_threshold_out_of_range_returns_400(self, client):
        assert client.get("/api/comics/duplicates", params={"threshold": 0.1}).status_code == 400
        assert client.get("/api/comics/duplicates", params={"threshold": 2}).status_code == 400


class TestStats:
    @staticmethod
    def _event(session, kind, entity_id, time, **data):
        session.add(ActivityEvent(kind=kind, mediaType="comic", entityId=entity_id, time=time, data=data))
        session.commit()

    def test_empty(self, client):
        r = client.get("/api/comics/stats")
        assert r.status_code == 200
        body = r.json()
        assert body["library"] == {
            "total": 0, "totalSize": 0, "favorited": 0, "started": 0, "finished": 0, "archived": 0,
        }
        assert body["since"] is None
        assert body["total"] == {"added": 0, "read": 0, "readDays": 0, "deleted": 0, "deletedSize": 0}
        assert len(body["months"]) == 12
        assert body["months"][-1]["month"] == datetime.now().strftime("%Y-%m")
        assert body["topRead"] == []

    def test_library(self, client, session):
        now = datetime.now()
        insert_comic(session, id=1, path="/a", page=10, favorited=True, lastViewedTime=now, lastViewedPosition=10)
        insert_comic(session, id=2, path="/b", page=10, lastViewedTime=now, lastViewedPosition=3)
        insert_comic(session, id=3, path="/c", page=10)
        insert_comic(session, id=4, path="/d", archived=True)
        insert_comic(session, id=5, path="/e", missing=True)
        lib = client.get("/api/comics/stats").json()["library"]
        assert lib == {
            "total": 3, "totalSize": 3000, "favorited": 1, "started": 2, "finished": 1, "archived": 1,
        }

    def test_activity(self, client, session):
        insert_comic(session, id=1, name="one.zip", path="/a")
        insert_comic(session, id=2, name="two.zip", path="/b")
        now = datetime.now()
        long_ago = now - timedelta(days=800)
        self._event(session, "add", 1, long_ago, name="one.zip", size=10)
        self._event(session, "add", 2, now, name="two.zip", size=20)
        self._event(session, "read", 1, now - timedelta(days=1), position=1)
        self._event(session, "read", 1, now, position=2)
        self._event(session, "read", 2, now, position=1)
        self._event(session, "read", 2, long_ago, position=1)
        self._event(session, "delete", 9, now, name="gone.zip", size=500, permanent=True)
        # Other media types are not counted.
        session.add(ActivityEvent(kind="add", mediaType="video", entityId=1, time=now, data={}))
        session.commit()

        body = client.get("/api/comics/stats?months=1").json()
        assert body["since"].startswith(long_ago.strftime("%Y-%m-%d"))
        assert body["total"] == {"added": 2, "read": 2, "readDays": 4, "deleted": 1, "deletedSize": 500}
        [month] = body["months"]
        assert month["month"] == now.strftime("%Y-%m")
        assert month["added"] == 1
        assert month["deleted"] == 1 and month["deletedSize"] == 500
        # The day-before read can fall in last month on the 1st.
        assert month["read"] == 2
        assert month["readDays"] in (2, 3)
        assert body["topRead"] == [
            {"id": 1, "name": "one.zip", "readDays": 2},
            {"id": 2, "name": "two.zip", "readDays": 2},
        ]

    def test_top_read_skips_deleted_comics(self, client, session):
        self._event(session, "read", 42, datetime.now(), position=1)
        assert client.get("/api/comics/stats").json()["topRead"] == []

    @pytest.mark.parametrize("months", [0, 61, "x"])
    def test_invalid_months(self, client, months):
        assert client.get(f"/api/comics/stats?months={months}").status_code == 400


class TestStatsMonths:
    def test_spans_year_boundary(self, session):
        import stats
        r = stats.comic_stats(session, 3, now=datetime(2026, 2, 15))
        assert [m.month for m in r.months] == ["2025-12", "2026-01", "2026-02"]
