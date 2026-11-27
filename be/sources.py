"""Scan folders ("media sources") per media type.

Each media type has built-in folders from the environment
(``global_data.Config.*.scan_pathes``: ``/data/comics``, ``/data/videos``,
``/data/images`` and ``/data/liked`` in the container), always scanned and not
removable, plus folders added at runtime through Admin -> Media sources
(``MediaSource`` rows). Only folders the container can already see can be
added: a new drive still needs a volume in compose.yaml.

Scans go through ``check()``, which also decides which folders are *held*: a
folder that is missing or where a scan found nothing is usually an unmounted
drive or a network share that is down, not a library that was emptied. The
records under a held folder are left exactly as they were (not flagged
missing, not taken over by a moved-file match, image albums kept from the last
scan) until a scan finds files there again.
"""
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from sqlmodel import Session, select

import db
import global_data
from core.scan_progress import progress
from model import MediaSource

MEDIA = ("comic", "video", "image")
# The scan endpoint's media types (api.system.start_scan) by source media.
SCAN_TYPE = {"comic": "comics", "video": "videos", "image": "images"}

NOT_FOUND = "Scan path not found (not mounted?)"
EMPTY = "No media files found"


@dataclass
class Source:
    media: str
    path: str
    builtin: bool
    id: Optional[int] = None


def _builtin_paths(media: str) -> List[str]:
    return list({
        "comic": global_data.Config.Comic.scan_pathes,
        "video": global_data.Config.Video.scan_pathes,
        "image": global_data.Config.Image.scan_pathes,
    }[media])


def all_sources(media: Optional[str] = None) -> List[Source]:
    """Built-in folders first, then added ones in the order they were added;
    a path listed twice for a media type counts once."""
    medias = [media] if media else list(MEDIA)
    found: List[Source] = []
    seen = set()

    def add(source: Source):
        key = (source.media, os.path.normpath(source.path))
        if key not in seen:
            seen.add(key)
            found.append(source)

    for m in medias:
        for path in _builtin_paths(m):
            add(Source(media=m, path=path, builtin=True))
    with Session(db.engine) as session:
        query = select(MediaSource).order_by(MediaSource.id)
        if media:
            query = query.where(MediaSource.media == media)
        for row in session.exec(query):
            add(Source(media=row.media, path=row.path, builtin=False, id=row.id))
    return found


def paths(media: str) -> List[str]:
    """Every scan folder of ``media``, built-in ones first."""
    return [s.path for s in all_sources(media)]


def inside(path: str, root: str) -> bool:
    """Whether ``path`` is ``root`` or somewhere below it."""
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives (Windows) or mixed abs/rel
        return False


class Check:
    """The outcome of ``check()``: what to scan and what to hold."""

    def __init__(self, media: str, scan: List[str], held: List[str]):
        self.media = media
        self.scan = scan
        self.held = held

    def hold(self, root: str, reason: Optional[str] = EMPTY):
        """Hold a folder whose scan found nothing, saying so unless ``reason``
        is None."""
        if reason:
            progress.add_issue(self.media, "warning", root, reason)
        self.scan = [p for p in self.scan if p != root]
        self.held.append(root)

    def is_held(self) -> Callable[[str], bool]:
        """A predicate: whether a recorded path lies in a held folder."""
        roots = [os.path.normpath(r) for r in self.held]
        if not roots:
            return lambda path: False
        return lambda path: any(inside(os.path.normpath(path), r) for r in roots)


def check(media: str) -> Check:
    """Split the scan folders of ``media`` into those to scan and those to
    hold because they are missing (reported as a scan warning). Callers hold
    the ones a scan then finds empty with ``Check.hold``."""
    scan, held = [], []
    for path in paths(media):
        if os.path.isdir(path):
            scan.append(path)
        else:
            progress.add_issue(media, "warning", path, NOT_FOUND)
            held.append(path)
    return Check(media, scan, held)


def status(path: str) -> str:
    """``ok``, ``not_found`` or ``not_mounted`` (a folder in the container's own
    filesystem: nothing from the host is there, see ``mover.in_container_fs``)."""
    import mover
    if not os.path.isdir(path):
        return "not_found"
    if mover.in_container_fs(path):
        return "not_mounted"
    return "ok"


class SourceError(Exception):
    """The folder can't be added; the message says why."""


def validate_new(media: str, path: str) -> str:
    """Normalize ``path`` and check it can become a ``media`` source; raises
    SourceError."""
    import mover
    if media not in MEDIA:
        raise SourceError(f"Unknown media type {media!r}")
    path = (path or "").strip()
    if not path or not os.path.isabs(path):
        raise SourceError("The folder must be an absolute path")
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        raise SourceError("Folder not found (the container only sees folders mounted in compose.yaml)")
    # A folder in two sources would be scanned twice, and one under both a
    # comic and an image source would be a comic and an album at once.
    for source in all_sources():
        root = os.path.normpath(source.path)
        if inside(path, root) or inside(root, path):
            what = "built-in" if source.builtin else "added"
            raise SourceError(f"Overlaps the {what} {source.media} folder {root}")
    if mover.in_container_fs(path):
        raise SourceError(
            "Not on a mounted drive: nothing from the host is there. Mount a volume in compose.yaml first"
        )
    return path


def add(session: Session, media: str, path: str) -> MediaSource:
    row = MediaSource(media=media, path=validate_new(media, path))
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def browse(path: str) -> Dict:
    """The subfolders of ``path`` (hidden ones left out), for picking a folder
    to add; raises SourceError when it can't be listed."""
    if not path or not os.path.isabs(path):
        raise SourceError("The folder must be an absolute path")
    path = os.path.normpath(path)
    if not os.path.isdir(path):
        raise SourceError("Folder not found")
    try:
        with os.scandir(path) as it:
            dirs = [e for e in it if not e.name.startswith(".") and e.is_dir()]
    except OSError as e:
        raise SourceError(f"Can't read the folder: {e.strerror or e}")
    parent = os.path.dirname(path)
    return {
        "path": path,
        "parent": parent if parent != path else None,
        "dirs": [
            {"name": e.name, "path": e.path, "mount": os.path.ismount(e.path)}
            for e in sorted(dirs, key=lambda e: e.name.casefold())
        ],
    }


def default_browse_root() -> str:
    """Where the folder picker starts: the media folder of the container."""
    return "/data" if os.path.isdir("/data") else os.path.abspath(os.sep)

