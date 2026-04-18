import time
from datetime import datetime

from model import ComicEntity, FileEntity, VideoEntity, get_dir_size


def test_entity_update_time_is_per_instance():
    t0 = datetime.now()
    time.sleep(0.01)
    e1 = ComicEntity(id=1, name="a", path="/a", size=0, updateTime=t0, page=1)
    time.sleep(0.01)
    e2 = ComicEntity(id=2, name="b", path="/b", size=0, updateTime=t0, page=1)
    assert e1.entityUpdateTime != e2.entityUpdateTime


def test_comic_entity_from_path(tmp_path):
    f = tmp_path / "comic.zip"
    f.write_bytes(b"x" * 100)
    entity = ComicEntity.from_path(f, id=42)
    assert entity.id == 42
    assert entity.name == "comic.zip"
    assert entity.path == str(f)
    assert entity.size == 100


def test_video_entity_from_path(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"y" * 200)
    entity = VideoEntity.from_path(f, id=7)
    assert entity.id == 7
    assert entity.size == 200


def test_file_entity_from_path_file(tmp_path):
    f = tmp_path / "file.bin"
    f.write_bytes(b"z" * 50)
    entity = FileEntity.from_path(f)
    assert entity.size == 50
    assert entity.name == "file.bin"


def test_get_dir_size(tmp_path):
    (tmp_path / "a.txt").write_bytes(b"1" * 10)
    (tmp_path / "b.txt").write_bytes(b"2" * 20)
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "c.txt").write_bytes(b"3" * 30)
    assert get_dir_size(tmp_path) == 60


def test_file_entity_from_path_dir(tmp_path):
    (tmp_path / "a").write_bytes(b"x" * 15)
    entity = FileEntity.from_path(tmp_path)
    assert entity.size == 15
    assert entity.name == tmp_path.name
