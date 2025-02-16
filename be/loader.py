from abc import abstractmethod
import io
from multiprocessing.pool import ThreadPool
import os
import pathlib
import subprocess
from typing import List
import threading

from sqlalchemy import func
from sqlmodel import Session, select
from rich.progress import track, Progress
from PIL import Image

from comicfile import Comicfile
import comicfile
import global_data
from model import ComicEntity, FileEntity, VideoEntity
import db
import util

p = ThreadPool(8)


class Loader:
    def __init__(self):
        self._starting_id = 0
        self.lock = threading.Lock()

    def _get_id(self):
        with self.lock:
            self._starting_id += 1
            return self._starting_id

    @abstractmethod
    def load(self, path: str):
        pass

    def work(self):
        old_pathes = set(self._load_old())
        all_pathes = set(self._load_all())
        print(f"old: {len(old_pathes)}, all: {len(all_pathes)}")
        if len(all_pathes) == 0:
            print("not work due to no file, perhaps specify wrong pathes?")
            return
        new_pathes = list(all_pathes.difference(old_pathes))
        if len(new_pathes) == 0:
            print("not work due to no new file.")
            return

        new_entities = []
        with Progress() as progress:
            task = progress.add_task("[green]Processing...", total=len(new_pathes))

            def do(p: str):
                progress.update(task, advance=1)
                return self._to_entity(p)

            entities = p.map(do, [e for e in new_pathes])
            new_entities = [e for e in entities if e is not None]

        self._commit_news(new_entities)

    @abstractmethod
    def _load_old(self) -> List[str]:
        pass

    @abstractmethod
    def _load_all(self) -> List[str]:
        pass

    @abstractmethod
    def _commit_news(self, news: FileEntity):
        print(f"commit {len(news)} entities to db.")
        with Session(db.engine) as session:
            session.add_all(news)
            session.commit()

    @abstractmethod
    def _to_entity(self, path: str):
        pass

    @abstractmethod
    def _gen_covers(self):
        pass


def scan(exts: List[str], pathes: List[str]):
    ret = []
    scanDir = "" in exts  # "" means scan dir
    for path in pathes:
        for root, dirs, files in os.walk(path):
            file_exts = [os.path.splitext(file)[1] for file in files]
            # dir with no sub dir
            if scanDir and len(dirs) == 0:
                # if has image file, add dir
                if any([ext in comicfile.allowImgs for ext in file_exts]):
                    ret.append(root)
            for file, ext in zip(files, file_exts):
                if ext in exts:
                    f = os.path.join(root, file)
                    ret.append(f)

    return list(set(ret))


class ComicLoader(Loader):
    comic_ext = [".zip", ".rar", ""]

    def __init__(self):
        super().__init__()
        with Session(db.engine) as session:
            sub_query = select(func.max(ComicEntity.id)).scalar_subquery()
            statement = select(ComicEntity).where(ComicEntity.id == sub_query)
            entity = session.exec(statement).first()
            self._starting_id = entity.id if entity is not None else 0

    def load(self, path: str):
        with Session(db.engine) as session:
            statement = select(ComicEntity).where(ComicEntity.path == path)
            entities = session.exec(statement).all()
            if len(entities) > 0:
                raise Exception(f"{path} already exists in db.")
            entity = self._to_entity(path)
            if entity is not None:
                session.add(entity)
                session.commit()

    def _load_old(self) -> List[str]:
        with Session(db.engine) as session:
            # load
            statement = select(ComicEntity)
            entities = session.exec(statement).all()
            print(f"read {len(entities)} entities from db.")

            return [e.path for e in entities]

    def _load_all(self) -> List[str]:
        return scan(self.comic_ext, global_data.Config.Comic.scan_pathes)

    def _to_entity(self, path: str):
        ret = ComicEntity.from_path(pathlib.Path(path), self._get_id())

        try:
            with comicfile.create(ret.path) as cf:
                ret.page = cf.page
                ComicLoader.gen_comic_cover(ret, cf, True)
        except Exception as ex:
            print("skip", ret.path, ex)
            global_data.err_message.append(f"{ret.path}: {ex}")
            return None

        return ret

    @staticmethod
    def gen_comic_cover(
        c: ComicEntity, cf: Comicfile = None, overwrite=False, page=0
    ) -> bool:
        thumbnail_maxsize = (300, 300)
        name = f"{c.id}_0.jpg"
        cover_path = os.path.join(global_data.Config.nginx_comic_path, name)
        if overwrite or not os.path.exists(cover_path):
            try:
                if cf is None:
                    with comicfile.create(c.path) as cf:
                        ok, buf = cf.read(page)
                else:
                    ok, buf = cf.read(page)
                if ok:
                    img = Image.open(io.BytesIO(buf))
                    img.thumbnail(thumbnail_maxsize)
                    img = img.convert("RGB")
                    img.save(cover_path, "JPEG")
                    return True
            except RuntimeError as ex:
                if "password required for extraction" in str(ex):
                    print("skip due to encrypted", c.path)
                else:
                    raise ex
            except Exception as ex:
                print("gen cover fail:", c.path, ex)
        return False


class VideoLoader(Loader):
    video_ext = [
        ".mp4",
        ".mkv",
        ".avi",
        ".wmv",
        ".flv",
        ".mov",
        ".mpg",
        ".mpeg",
        ".m4v",
        ".webm",
    ]
    _starting_id: int

    def __init__(self):
        super().__init__()
        with Session(db.engine) as session:
            sub_query = select(func.max(VideoEntity.id)).scalar_subquery()
            statement = select(VideoEntity).where(VideoEntity.id == sub_query)
            entity = session.exec(statement).first()
            self._starting_id = entity.id if entity is not None else 0

    def load(self, path):
        with Session(db.engine) as session:
            statement = select(VideoEntity).where(VideoEntity.path == path)
            entities = session.exec(statement).all()
            if len(entities) > 0:
                raise Exception(f"{path} already exists in db.")
            entity = self._to_entity(path)
            if entity is not None:
                session.add(entity)
                session.commit()

    def _load_old(self) -> List[str]:
        with Session(db.engine) as session:
            statement = select(VideoEntity)
            entities = session.exec(statement).all()
            print(f"read {len(entities)} entities from db.")
            return [e.path for e in entities]

    def _load_all(self) -> List[str]:
        return scan(self.video_ext, global_data.Config.Video.scan_pathes)

    def _to_entity(self, path: str):
        ret = VideoEntity.from_path(pathlib.Path(path), self._get_id())

        try:
            VideoLoader.gen_video_cover(ret)
            ret.durationInSecond = VideoLoader.get_video_length(path)
        except Exception as ex:
            print("skip", ret.path, ex)

        return ret

    @staticmethod
    def gen_video_cover(c: VideoEntity):
        cover_name = f"{c.id}.jpg"
        outpath = os.path.join(global_data.Config.nginx_video_path, cover_name)
        if not os.path.exists(outpath):
            subprocess.call(
                [
                    "ffmpeg",
                    "-i",
                    c.path,
                    "-ss",
                    "00:00:00.000",
                    "-vf",
                    "scale=320:320:force_original_aspect_ratio=decrease",
                    "-vframes",
                    "1",
                    outpath,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )

        new_name = str(c.id)
        new_path = os.path.join(global_data.Config.nginx_video_path, new_name)
        util.create_soft_link(c.path, new_path)

    @staticmethod
    def get_video_length(filename: str):
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                filename,
            ]
            result = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            print(filename, e)
            return 0
        return int(float(result.stdout.decode()))
