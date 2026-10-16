"""Tests for the home page feed (GET /api/home)"""
from datetime import datetime, timedelta

import pytest

import api.images as img_api
from api.home import HOME_SIZE
from conftest import insert_comic, insert_video
from model import ImageEntity


def make_album(id, page=10, **kwargs) -> ImageEntity:
    kwargs.setdefault("updateTime", datetime.now())
    return ImageEntity(id=id, name=f"album{id}", path=f"/nonexistent/album{id}", size=0, page=page, **kwargs)


@pytest.fixture(autouse=True)
def clear_store():
    img_api._store.clear()
    yield
    img_api._store.clear()


def set_albums(*albums: ImageEntity):
    img_api._store.update({a.id: a for a in albums})


def ids(section, kind):
    return [e["id"] for e in section[kind]]


def get_home(client):
    r = client.get("/api/home")
    assert r.status_code == 200
    return r.json()


class TestHome:
    def test_empty(self, client):
        body = get_home(client)
        for name in ("continueReading", "recent", "favorites", "random"):
            assert body[name] == {"comics": [], "videos": [], "images": []}

    def test_continue_reading_only_unfinished(self, client, session):
        now = datetime.now()
        insert_comic(session, 1, "a.zip", page=10, lastViewedPosition=3, lastViewedTime=now - timedelta(hours=2))
        insert_comic(session, 2, "b.zip", page=10, lastViewedPosition=5, lastViewedTime=now)
        insert_comic(session, 3, "done.zip", page=10, lastViewedPosition=10, lastViewedTime=now)
        insert_comic(session, 4, "unread.zip", page=10)
        insert_comic(session, 5, "gone.zip", page=10, lastViewedPosition=2, lastViewedTime=now, missing=True)
        set_albums(
            make_album(11, lastViewedPosition=4, lastViewedTime=now),
            make_album(12, lastViewedPosition=10, lastViewedTime=now),
            make_album(13),
        )
        section = get_home(client)["continueReading"]
        # Most recently read first; finished, unread and missing ones left out.
        assert ids(section, "comics") == [2, 1]
        assert ids(section, "images") == [11]
        assert section["videos"] == []

    def test_recent_newest_first_without_archived(self, client, session):
        now = datetime.now()
        insert_comic(session, 1, "old.zip")
        newer = insert_comic(session, 2, "new.zip")
        newer.updateTime = now + timedelta(hours=1)
        session.add(newer)
        session.commit()
        insert_comic(session, 3, "archived.zip", archived=True)
        insert_video(session, 1, "a.mp4")
        set_albums(make_album(11, updateTime=now), make_album(12, updateTime=now + timedelta(hours=1)))
        section = get_home(client)["recent"]
        assert ids(section, "comics") == [2, 1]
        assert ids(section, "videos") == [1]
        assert ids(section, "images") == [12, 11]

    def test_favorites(self, client, session):
        insert_comic(session, 1, "fav.zip", favorited=True)
        insert_comic(session, 2, "plain.zip")
        insert_comic(session, 3, "archived.zip", favorited=True, archived=True)
        insert_video(session, 1, "fav.mp4", favorited=True)
        insert_video(session, 2, "plain.mp4")
        section = get_home(client)["favorites"]
        assert ids(section, "comics") == [1]
        assert ids(section, "videos") == [1]
        assert section["images"] == []

    def test_sections_are_capped(self, client, session):
        for i in range(HOME_SIZE + 3):
            insert_comic(session, i + 1, f"{i}.zip")
            insert_video(session, i + 1, f"{i}.mp4")
        set_albums(*(make_album(100 + i) for i in range(HOME_SIZE + 3)))
        body = get_home(client)
        for name in ("recent", "random"):
            for kind in ("comics", "videos", "images"):
                assert len(body[name][kind]) == HOME_SIZE

    def test_random_picks_visible_items(self, client, session):
        insert_comic(session, 1, "a.zip")
        insert_comic(session, 2, "archived.zip", archived=True)
        insert_video(session, 1, "gone.mp4", missing=True)
        set_albums(make_album(11))
        section = get_home(client)["random"]
        assert ids(section, "comics") == [1]
        assert section["videos"] == []
        assert ids(section, "images") == [11]
