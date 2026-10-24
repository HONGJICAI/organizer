from abc import abstractmethod
from collections import defaultdict
import io
from multiprocessing.pool import ThreadPool
import os
import pathlib
import subprocess
import time
from typing import List
import threading
import unicodedata

from sqlalchemy import func
from sqlmodel import Session, col, delete, select, update
from rich.progress import Progress
from PIL import Image

from comicfile import Comicfile
import comicfile
import global_data
from core.scan_progress import progress
from model import ActivityEvent, ComicEntity, FileEntity, VideoEntity
import db
import events
import util

p = ThreadPool(8)


def _same_path(a: str, b: str) -> bool:
    """Whether two paths differ only in case or Unicode normalization: the
    same file on a case-insensitive filesystem (NTFS, SMB, macOS)."""
    def norm(p: str) -> str:
        return unicodedata.normalize("NFC", p).casefold()
    return norm(a) == norm(b)


class SkipFile(Exception):
    """A scanned path that can't be imported; the message says why."""


class Loader:
    # Subclasses set this to their SQLModel table class so the shared reconcile
    # can flag/clear the ``missing`` column generically.
    entity_cls = None
    # Human-readable phase label surfaced in the scan progress/metrics.
    phase = None
    # ActivityEvent.mediaType for the add events this loader records; None
    # records none (only comics are logged for now).
    media_type = None

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

    @property
    def media(self) -> str:
        """Issue label for this loader's media: "comic" or "video"."""
        return self.phase[:-1]

    def _scan_pathes(self) -> List[str]:
        return []

    def work(self):
        progress.set_phase(self.phase, 0)
        # A missing scan path is usually an unmounted drive; say so, since the
        # scan would otherwise just find nothing there.
        for path in self._scan_pathes():
            if not os.path.isdir(path):
                progress.add_issue(self.media, "warning", path, "Scan path not found (not mounted?)")
        old_pathes = set(self._load_old())
        all_pathes = set(self._load_all())
        print(f"old: {len(old_pathes)}, all: {len(all_pathes)}")
        # Before anything treats a moved file as new: carry records over to
        # where their files went.
        if self._follow_moves(all_pathes, old_pathes):
            old_pathes = set(self._load_old())
        # Reconcile the missing flag first: a file can disappear without any new
        # file appearing, so this must run even when the early-returns below fire.
        progress.add_reconciled(self._reconcile_missing(all_pathes))
        if len(all_pathes) == 0:
            present = [p for p in self._scan_pathes() if os.path.isdir(p)]
            if present:
                progress.add_issue(self.media, "warning", ", ".join(present), "No media files found")
            print("not work due to no file, perhaps specify wrong pathes?")
            return
        new_pathes = list(all_pathes.difference(old_pathes))
        if len(new_pathes) == 0:
            print("not work due to no new file.")
            return

        progress.set_phase(self.phase, len(new_pathes))
        new_entities = []
        with Progress() as bar:
            task = bar.add_task("[green]Processing...", total=len(new_pathes))

            def do(path: str):
                # Time the per-file work: on a network mount the open/parse is
                # the dominant cost and the metric worth surfacing.
                started = time.perf_counter()
                try:
                    return self._to_entity(path)
                except Exception as ex:
                    # Listed in the scan status (Admin) instead of failing the
                    # whole scan. Not remembered: the next scan tries again.
                    reason = str(ex) or type(ex).__name__
                    print("skip", path, reason)
                    progress.add_issue(self.media, "skipped", path, reason)
                    return None
                finally:
                    bar.update(task, advance=1)
                    progress.advance(path, (time.perf_counter() - started) * 1000)

            entities = p.map(do, [e for e in new_pathes])
            new_entities = [e for e in entities if e is not None]

        self._commit_news(new_entities)

    def _cover_path(self, entity_id: int) -> str | None:
        """The cover file of a record, removed when the record is merged away."""
        return None

    def _follow_moves(self, present: set, known: set) -> int:
        """Recognize files that moved instead of importing them as new.

        Records are keyed by path, so a file whose path changed (moved or
        renamed outside the app, or spelled differently by a case-insensitive
        filesystem) would get a second record and lose its favorite and
        progress. A record whose path is gone is matched to a file by its
        size and modification time, and only when exactly one gone record and
        one file share them:

        - a path not in the database yet: the record takes the new path;
        - another record of the same file under a path that differs only in
          case or Unicode normalization (the duplicate a case-insensitive
          filesystem leads to, whichever of the two spellings the folder has
          now): the two are merged into the older record, which keeps its id
          and takes the path that is present. Paths that differ otherwise are
          left alone: they may be a second copy on another drive.

        Returns how many records changed.
        """
        if self.entity_cls is None or not present:
            return 0
        cls = self.entity_cls
        with Session(db.engine) as session:
            rows = session.exec(select(cls).where(cls.archived == False)).all()  # noqa: E712
            gone = defaultdict(list)
            for e in rows:
                if e.path not in present:
                    gone[(e.size, e.updateTime)].append(e)
            if not gone:
                return 0
            changed = 0

            later = defaultdict(list)
            for e in rows:
                if e.path in present and (e.size, e.updateTime) in gone:
                    later[(e.size, e.updateTime)].append(e)
            for sig, (stale, *more) in list(gone.items()):
                found = later.get(sig, [])
                if more or len(found) != 1:
                    continue
                live = found[0]
                if not _same_path(live.path, stale.path):
                    continue
                keep, drop = sorted((stale, live), key=lambda e: e.id)
                old_path = keep.path
                self._merge(session, keep, drop, live.path)
                progress.add_issue(
                    self.media, "warning", keep.path,
                    f"Merged duplicate record #{drop.id} into #{keep.id} (it was recorded at {old_path!r})",
                )
                del gone[sig]
                changed += 1

            new_files = defaultdict(list)
            if gone:
                for path in present - known:
                    try:
                        entity = FileEntity.from_path(pathlib.Path(path))
                    except OSError:
                        continue
                    if (entity.size, entity.updateTime) in gone:
                        new_files[(entity.size, entity.updateTime)].append(path)
            for sig, paths in new_files.items():
                if len(paths) != 1 or len(gone[sig]) != 1:
                    continue
                keep = gone[sig][0]
                progress.add_issue(
                    self.media, "warning", paths[0], f"Recognized as moved from {keep.path!r} (record #{keep.id} kept)"
                )
                keep.path, keep.name, keep.missing = paths[0], os.path.basename(paths[0]), False
                session.add(keep)
                changed += 1
            session.commit()
        print(f"follow moves: updated {changed} record(s)")
        return changed

    def _merge(self, session: Session, keep: FileEntity, drop: FileEntity, path: str) -> None:
        """Fold ``drop`` (a later record of the same file) into ``keep``: keep
        takes ``path`` (the spelling present on disk), the favorite and the
        latest reading position; drop's add event goes and its other events
        move over."""
        keep.path, keep.name, keep.missing = path, os.path.basename(path), False
        keep.favorited = keep.favorited or drop.favorited
        if drop.lastViewedTime and (not keep.lastViewedTime or drop.lastViewedTime > keep.lastViewedTime):
            keep.lastViewedTime, keep.lastViewedPosition = drop.lastViewedTime, drop.lastViewedPosition
        if self.media_type:
            events_of_drop = (ActivityEvent.mediaType == self.media_type) & (col(ActivityEvent.entityId) == drop.id)
            session.exec(delete(ActivityEvent).where(events_of_drop & (ActivityEvent.kind == events.ADD)))
            session.exec(update(ActivityEvent).where(events_of_drop).values(entityId=keep.id))
        session.delete(drop)
        session.flush()
        session.add(keep)
        cover = self._cover_path(drop.id)
        if cover and os.path.exists(cover):
            try:
                os.remove(cover)
            except OSError:
                pass

    def _reconcile_missing(self, present_pathes: set):
        """Flag DB rows whose file is gone and clear ones that reappeared.

        Scoped to non-archived rows — archived entries are deliberate
        "deleted the file, kept the record" tombstones and must never be
        flagged. Skipped entirely when the scan found nothing on disk: an
        empty result almost always means a misconfigured or unmounted scan
        path, and flagging the whole library missing in that case is exactly
        the data-loss footgun we're trying to avoid. The next successful scan
        self-heals the flag once files reappear.

        Returns the number of rows whose flag changed (for progress/metrics).
        """
        if self.entity_cls is None or not present_pathes:
            return 0
        with Session(db.engine) as session:
            entities = session.exec(
                select(self.entity_cls).where(self.entity_cls.archived == False)  # noqa: E712
            ).all()
            changed = 0
            for e in entities:
                should_miss = e.path not in present_pathes
                if e.missing != should_miss:
                    e.missing = should_miss
                    session.add(e)
                    changed += 1
            if changed:
                session.commit()
                print(f"reconcile: updated missing flag on {changed} entit(y/ies)")
            return changed

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
            if self.media_type:
                events.record_adds(session, self.media_type, news)
            session.commit()

    @abstractmethod
    def _to_entity(self, path: str):
        pass

    @abstractmethod
    def _gen_covers(self):
        pass


def scan(exts: List[str], pathes: List[str]):
    """Media paths under ``pathes``.

    Files match ``exts`` case-insensitively (``.ZIP`` counts). The empty
    string in ``exts`` stands for folder comics: a folder with no subfolders
    that holds at least one page image. It never matches extensionless files
    (``README``, ``.DS_Store``). Hidden files, such as macOS ``._name.zip``
    metadata, are skipped.
    """
    ret = []
    scan_dir = "" in exts
    file_exts = {e.lower() for e in exts if e}
    for path in pathes:
        for root, dirs, files in os.walk(path):
            if scan_dir and not dirs and any(comicfile.is_page(f) for f in files):
                ret.append(root)
            for file in files:
                if file.startswith("."):
                    continue
                if os.path.splitext(file)[1].lower() in file_exts:
                    ret.append(os.path.join(root, file))

    return list(set(ret))


class ComicLoader(Loader):
    comic_ext = [".zip", ".rar", ""]
    entity_cls = ComicEntity
    phase = "comics"
    media_type = events.COMIC

    def _cover_path(self, entity_id: int) -> str:
        return os.path.join(global_data.Config.nginx_comic_path, f"{entity_id}_0.jpg")

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
            # Raises when the file can't be imported, so callers see why.
            entity = self._to_entity(path)
            session.add(entity)
            events.record_adds(session, self.media_type, [entity])
            session.commit()

    def _load_old(self) -> List[str]:
        with Session(db.engine) as session:
            # load
            statement = select(ComicEntity)
            entities = session.exec(statement).all()
            print(f"read {len(entities)} entities from db.")

            return [e.path for e in entities]

    def _scan_pathes(self) -> List[str]:
        return global_data.Config.Comic.scan_pathes

    def _load_all(self) -> List[str]:
        return scan(self.comic_ext, self._scan_pathes())

    def _to_entity(self, path: str):
        """Build the entity for a new comic; raises when it can't be imported."""
        ret = ComicEntity.from_path(pathlib.Path(path), self._get_id())
        cf = comicfile.create(ret.path)
        if cf is None:
            raise SkipFile("Not a supported comic file")
        with cf:
            if cf.page == 0:
                raise SkipFile("No page images found")
            ret.page = cf.page
            # Cover failures other than encryption errors are logged inside and
            # don't block the import; "Generate missing" can retry them.
            ComicLoader.gen_comic_cover(ret, cf, True)
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
    entity_cls = VideoEntity
    phase = "videos"
    _starting_id: int

    def _cover_path(self, entity_id: int) -> str:
        return os.path.join(global_data.Config.nginx_video_path, f"{entity_id}.jpg")

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

    def _scan_pathes(self) -> List[str]:
        return global_data.Config.Video.scan_pathes

    def _load_all(self) -> List[str]:
        return scan(self.video_ext, self._scan_pathes())

    def _to_entity(self, path: str):
        ret = VideoEntity.from_path(pathlib.Path(path), self._get_id())

        try:
            VideoLoader.gen_video_cover(ret)
            ret.durationInSecond = VideoLoader.get_video_length(path)
        except Exception as ex:
            # Imported anyway; it just lacks a cover or duration.
            print("skip", ret.path, ex)
            progress.add_issue("video", "warning", path, f"No cover/duration: {str(ex) or type(ex).__name__}")

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
