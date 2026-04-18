from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, select

import comicfile
import global_data
from conftest import insert_comic, make_zip_comic
from loader import ComicLoader, VideoLoader, scan
from model import ComicEntity, VideoEntity


# ---------------------------------------------------------------------------
# scan()
# ---------------------------------------------------------------------------

class TestScan:
    def test_finds_zip_files(self, tmp_path):
        (tmp_path / "a.zip").write_bytes(b"x")
        (tmp_path / "b.zip").write_bytes(b"x")
        (tmp_path / "c.txt").write_text("text")
        result = scan([".zip"], [str(tmp_path)])
        assert len(result) == 2

    def test_finds_directories_with_images(self, tmp_path):
        d = tmp_path / "mycomic"
        d.mkdir()
        (d / "0.jpg").write_bytes(b"img")
        result = scan([""], [str(tmp_path)])
        assert str(d) in result

    def test_skips_dirs_with_subdirs(self, tmp_path):
        parent = tmp_path / "parent"
        parent.mkdir()
        child = parent / "child"
        child.mkdir()
        (child / "0.jpg").write_bytes(b"img")
        result = scan([""], [str(tmp_path)])
        # parent has a subdir so it's skipped; child has no subdir so it's included
        assert str(child) in result
        assert str(parent) not in result

    def test_empty_directory(self, tmp_path):
        result = scan([".zip"], [str(tmp_path)])
        assert result == []

    def test_deduplicates_results(self, tmp_path):
        (tmp_path / "a.zip").write_bytes(b"x")
        result = scan([".zip"], [str(tmp_path), str(tmp_path)])
        assert len(result) == 1

    def test_multiple_extensions(self, tmp_path):
        (tmp_path / "a.zip").write_bytes(b"x")
        (tmp_path / "b.rar").write_bytes(b"x")
        result = scan([".zip", ".rar"], [str(tmp_path)])
        assert len(result) == 2


# ---------------------------------------------------------------------------
# ComicLoader
# ---------------------------------------------------------------------------

class TestComicLoaderInit:
    def test_empty_db_starts_at_zero(self, task_engine):
        loader = ComicLoader()
        assert loader._starting_id == 0

    def test_existing_db_picks_up_max_id(self, task_session, task_engine):
        for i in [3, 7, 2]:
            task_session.add(ComicEntity(id=i, name=f"{i}.zip", path=f"/{i}.zip",
                                         size=0, updateTime=datetime.now(), page=1))
        task_session.commit()
        loader = ComicLoader()
        assert loader._starting_id == 7


class TestComicLoaderLoadOld:
    def test_returns_paths(self, task_session, task_engine):
        task_session.add(ComicEntity(id=1, name="a.zip", path="/a/a.zip",
                                     size=0, updateTime=datetime.now(), page=1))
        task_session.commit()
        loader = ComicLoader()
        old = loader._load_old()
        assert "/a/a.zip" in old

    def test_empty_returns_empty(self, task_engine):
        loader = ComicLoader()
        assert loader._load_old() == []


class TestComicLoaderLoad:
    def test_adds_comic_to_db(self, task_engine, tmp_path):
        f = tmp_path / "new.zip"
        make_zip_comic(str(f), pages=2)
        loader = ComicLoader()
        with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            loader.load(str(f))
        with Session(task_engine) as s:
            comics = s.exec(select(ComicEntity)).all()
            assert len(comics) == 1
            assert comics[0].path == str(f)
            assert comics[0].page == 2

    def test_raises_on_duplicate_path(self, task_session, task_engine, tmp_path):
        f = tmp_path / "dup.zip"
        make_zip_comic(str(f))
        insert_comic(task_session, id=1, name="dup.zip", path=str(f))
        loader = ComicLoader()
        with pytest.raises(Exception, match="already exists"):
            loader.load(str(f))


class TestComicLoaderToEntity:
    def test_success(self, task_engine, tmp_path):
        f = tmp_path / "comic.zip"
        make_zip_comic(str(f), pages=3)
        loader = ComicLoader()
        with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            entity = loader._to_entity(str(f))
        assert entity is not None
        assert entity.page == 3
        assert entity.path == str(f)

    def test_bad_zip_returns_none(self, task_engine, tmp_path):
        f = tmp_path / "bad.zip"
        f.write_bytes(b"not a zip")
        loader = ComicLoader()
        entity = loader._to_entity(str(f))
        assert entity is None

    def test_adds_error_message_on_failure(self, task_engine, tmp_path):
        import global_data
        f = tmp_path / "bad.zip"
        f.write_bytes(b"not a zip")
        global_data.err_message.clear()
        loader = ComicLoader()
        loader._to_entity(str(f))
        assert len(global_data.err_message) > 0
        global_data.err_message.clear()


class TestComicLoaderGenCover:
    def test_generates_cover(self, task_engine, tmp_path, monkeypatch):
        f = tmp_path / "comic.zip"
        make_zip_comic(str(f), pages=2)
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()
        monkeypatch.setattr(global_data.Config, "nginx_comic_path", str(cover_dir))

        entity = ComicEntity(id=42, name="comic.zip", path=str(f),
                             size=0, updateTime=datetime.now(), page=2)
        with comicfile.create(str(f)) as cf:
            result = ComicLoader.gen_comic_cover(entity, cf, overwrite=True)
        assert result is True
        assert (cover_dir / "42_0.jpg").exists()

    def test_skips_if_cover_exists_no_overwrite(self, task_engine, tmp_path, monkeypatch):
        f = tmp_path / "comic.zip"
        make_zip_comic(str(f), pages=1)
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()
        monkeypatch.setattr(global_data.Config, "nginx_comic_path", str(cover_dir))

        existing = cover_dir / "10_0.jpg"
        existing.write_bytes(b"existing cover")
        entity = ComicEntity(id=10, name="comic.zip", path=str(f),
                             size=0, updateTime=datetime.now(), page=1)
        with comicfile.create(str(f)) as cf:
            result = ComicLoader.gen_comic_cover(entity, cf, overwrite=False)
        assert result is False
        # File should be unchanged
        assert existing.read_bytes() == b"existing cover"

    def test_generates_cover_without_cf_arg(self, task_engine, tmp_path, monkeypatch):
        f = tmp_path / "comic.zip"
        make_zip_comic(str(f), pages=1)
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()
        monkeypatch.setattr(global_data.Config, "nginx_comic_path", str(cover_dir))

        entity = ComicEntity(id=77, name="comic.zip", path=str(f),
                             size=0, updateTime=datetime.now(), page=1)
        result = ComicLoader.gen_comic_cover(entity, cf=None, overwrite=True)
        assert result is True
        assert (cover_dir / "77_0.jpg").exists()

    def test_specific_page(self, task_engine, tmp_path, monkeypatch):
        f = tmp_path / "comic.zip"
        make_zip_comic(str(f), pages=3)
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()
        monkeypatch.setattr(global_data.Config, "nginx_comic_path", str(cover_dir))

        entity = ComicEntity(id=55, name="comic.zip", path=str(f),
                             size=0, updateTime=datetime.now(), page=3)
        with comicfile.create(str(f)) as cf:
            result = ComicLoader.gen_comic_cover(entity, cf, overwrite=True, page=2)
        assert result is True


class TestComicLoaderWork:
    def test_work_adds_new_comics(self, task_engine, tmp_path, monkeypatch):
        f = tmp_path / "new.zip"
        make_zip_comic(str(f), pages=2)
        monkeypatch.setattr(global_data.Config.Comic, "scan_pathes", [str(tmp_path)])
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()
        monkeypatch.setattr(global_data.Config, "nginx_comic_path", str(cover_dir))

        loader = ComicLoader()
        with patch.object(ComicLoader, "gen_comic_cover", return_value=True):
            loader.work()

        with Session(task_engine) as s:
            comics = s.exec(select(ComicEntity)).all()
            assert len(comics) == 1

    def test_work_skips_if_no_files(self, task_engine, tmp_path, monkeypatch):
        monkeypatch.setattr(global_data.Config.Comic, "scan_pathes", [str(tmp_path)])
        loader = ComicLoader()
        loader.work()
        with Session(task_engine) as s:
            assert s.exec(select(ComicEntity)).all() == []

    def test_work_skips_existing(self, task_session, task_engine, tmp_path, monkeypatch):
        f = tmp_path / "existing.zip"
        make_zip_comic(str(f), pages=1)
        insert_comic(task_session, id=1, name="existing.zip", path=str(f))
        monkeypatch.setattr(global_data.Config.Comic, "scan_pathes", [str(tmp_path)])
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()
        monkeypatch.setattr(global_data.Config, "nginx_comic_path", str(cover_dir))

        loader = ComicLoader()
        loader.work()

        with Session(task_engine) as s:
            assert len(s.exec(select(ComicEntity)).all()) == 1


# ---------------------------------------------------------------------------
# VideoLoader
# ---------------------------------------------------------------------------

class TestVideoLoaderInit:
    def test_empty_db(self, task_engine):
        loader = VideoLoader()
        assert loader._starting_id == 0

    def test_picks_up_max_id(self, task_session, task_engine):
        task_session.add(VideoEntity(id=9, name="v.mp4", path="/v.mp4",
                                     size=0, updateTime=datetime.now()))
        task_session.commit()
        loader = VideoLoader()
        assert loader._starting_id == 9


class TestVideoLoaderLoadOld:
    def test_returns_paths(self, task_session, task_engine):
        task_session.add(VideoEntity(id=1, name="v.mp4", path="/v.mp4",
                                     size=0, updateTime=datetime.now()))
        task_session.commit()
        loader = VideoLoader()
        assert "/v.mp4" in loader._load_old()


class TestVideoLoaderLoad:
    def test_adds_video(self, task_engine, tmp_path):
        f = tmp_path / "v.mp4"
        f.write_bytes(b"video")
        loader = VideoLoader()
        with patch("subprocess.call"), patch("util.create_soft_link"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"60.5\n")
            loader.load(str(f))
        with Session(task_engine) as s:
            videos = s.exec(select(VideoEntity)).all()
            assert len(videos) == 1

    def test_raises_on_duplicate(self, task_session, task_engine, tmp_path):
        f = tmp_path / "dup.mp4"
        f.write_bytes(b"x")
        task_session.add(VideoEntity(id=1, name="dup.mp4", path=str(f),
                                     size=0, updateTime=datetime.now()))
        task_session.commit()
        loader = VideoLoader()
        with pytest.raises(Exception, match="already exists"):
            loader.load(str(f))


class TestVideoLoaderToEntity:
    def test_success(self, task_engine, tmp_path):
        f = tmp_path / "vid.mp4"
        f.write_bytes(b"video")
        loader = VideoLoader()
        with patch("subprocess.call"), patch("util.create_soft_link"), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"120.0\n")
            entity = loader._to_entity(str(f))
        assert entity is not None
        assert entity.durationInSecond == 120
        assert entity.path == str(f)

    def test_subprocess_error_still_returns_entity(self, task_engine, tmp_path):
        f = tmp_path / "vid.mp4"
        f.write_bytes(b"video")
        loader = VideoLoader()
        with patch("subprocess.call", side_effect=Exception("ffmpeg not found")), \
             patch("util.create_soft_link"):
            entity = loader._to_entity(str(f))
        assert entity is not None


class TestVideoLoaderGenCover:
    def test_calls_ffmpeg(self, task_engine, tmp_path, monkeypatch):
        monkeypatch.setattr(global_data.Config, "nginx_video_path", str(tmp_path))
        entity = VideoEntity(id=1, name="v.mp4", path="/v.mp4",
                             size=0, updateTime=datetime.now())
        with patch("subprocess.call") as mock_ffmpeg, \
             patch("util.create_soft_link"):
            VideoLoader.gen_video_cover(entity)
        mock_ffmpeg.assert_called_once()
        args = mock_ffmpeg.call_args[0][0]
        assert "ffmpeg" in args

    def test_skips_if_cover_exists(self, task_engine, tmp_path, monkeypatch):
        monkeypatch.setattr(global_data.Config, "nginx_video_path", str(tmp_path))
        existing_cover = tmp_path / "1.jpg"
        existing_cover.write_bytes(b"cover")
        entity = VideoEntity(id=1, name="v.mp4", path="/v.mp4",
                             size=0, updateTime=datetime.now())
        with patch("subprocess.call") as mock_ffmpeg, \
             patch("util.create_soft_link"):
            VideoLoader.gen_video_cover(entity)
        mock_ffmpeg.assert_not_called()


class TestVideoLoaderGetLength:
    def test_returns_duration(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=b"90.5\n")
            result = VideoLoader.get_video_length("/some/video.mp4")
        assert result == 90

    def test_returns_zero_on_exception(self, tmp_path):
        with patch("subprocess.run", side_effect=Exception("no ffprobe")):
            result = VideoLoader.get_video_length("/some/video.mp4")
        assert result == 0
