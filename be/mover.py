"""Move comics into another folder, keeping their records.

A file moved behind the app's back is a new path to the next scan: it is
imported as a new comic and the old record is flagged missing, losing its
favorite and reading progress. Moving through here updates the record's path
instead, so the id (and with it the cover file, progress and stats) stays.

Moves run as a "move" job on the heavy-job queue, so they never overlap a scan
(which could import a half-copied file) or a cover run (which reads the files).

Within one filesystem a move is a rename. Across filesystems -- two separate
drives or network shares mounted into the container, which the kernel reports
as EXDEV -- the comic is copied to a hidden temporary name next to its
destination, checked by size, renamed into place, and only then is the original
deleted. A failed copy leaves the original and the record untouched.
"""
import errno
import os
import shutil
import unicodedata
from typing import Dict, Iterable, List, Optional, Tuple

from sqlmodel import Session, col, select

import comicfile
import db
import global_data
from core.jobs import Job, jobs
from model import ComicEntity
from schemas.comic import ComicMovePlanItem

class MoveError(Exception):
    """The target folder can't be used; the message says why."""


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([path, root]) == root
    except ValueError:  # different drives (Windows) or mixed abs/rel
        return False


def _existing_ancestor(path: str) -> str:
    while not os.path.exists(path):
        parent = os.path.dirname(path)
        if parent == path:
            break
        path = parent
    return path


def _mount_point(path: str) -> str:
    path = os.path.realpath(_existing_ancestor(path))
    while not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def in_container_fs(path: str) -> bool:
    """Whether ``path`` would land in the container's own writable layer
    (nothing mounted there), where files are lost when the container is
    recreated."""
    return os.path.exists("/.dockerenv") and _mount_point(path) == "/"


def _device(path: str) -> int:
    return os.stat(_existing_ancestor(path)).st_dev


def _same_name(a: str, b: str) -> bool:
    """Whether two names are the same file on a case-insensitive or
    normalizing filesystem (NTFS, SMB, macOS): equal after Unicode NFC and
    case folding."""
    return unicodedata.normalize("NFC", a).casefold() == unicodedata.normalize("NFC", b).casefold()


def on_disk(path: str, listings: Optional[Dict[str, Optional[List[str]]]] = None) -> str:
    """``path`` spelled the way the filesystem lists it.

    On a case-insensitive filesystem ``artist/Hoge`` opens an existing
    ``artist/hoge``, but a scan lists it as ``hoge``: a record saved under
    the other spelling would look like a different file and get imported
    again. So each existing component takes the listed name that matches it
    (exactly, else ignoring case and Unicode normalization); components that
    don't exist yet are kept as given.

    ``listings`` caches folder listings across calls (one request resolving
    many paths under the same, possibly slow network, folder).
    """
    path = os.path.normpath(path)
    if not os.path.isabs(path):
        return path
    resolved, rest = os.sep, [p for p in path.split(os.sep) if p]
    if listings is None:
        listings = {}
    for i, part in enumerate(rest):
        if resolved not in listings:
            try:
                listings[resolved] = os.listdir(resolved)
            except OSError:
                listings[resolved] = None
        names = listings[resolved]
        if names is None:
            return os.path.join(resolved, *rest[i:])
        if part not in names:
            match = next((n for n in names if _same_name(n, part)), None)
            if match is None:
                return os.path.join(resolved, *rest[i:])
            part = match
        resolved = os.path.join(resolved, part)
    return resolved


def check_target(session: Session, target: str) -> str:
    """Normalize ``target`` and check it can receive comics; raises MoveError."""
    target = (target or "").strip()
    if not target or not os.path.isabs(target):
        raise MoveError("Target must be an absolute folder path")
    target = os.path.normpath(target)
    roots = [os.path.normpath(p) for p in global_data.Config.Comic.scan_pathes]
    if not any(_inside(target, root) for root in roots):
        raise MoveError(
            "Target must be inside a comic scan folder (" + ", ".join(roots) + ")"
        )
    # Record paths the way a scan will list them (see on_disk).
    target = on_disk(target)
    if os.path.exists(target) and not os.path.isdir(target):
        raise MoveError("Target exists and is not a folder")
    # A folder comic is a folder of images without subfolders: moving files
    # into one would change (or, with a folder comic, break) that comic. Only
    # the target and its parents can be one, so look those paths up.
    parents = [target]
    while os.path.dirname(parents[-1]) != parents[-1]:
        parents.append(os.path.dirname(parents[-1]))
    for path, name in session.exec(
        select(ComicEntity.path, ComicEntity.name).where(col(ComicEntity.path).in_(parents))
    ):
        if os.path.isdir(path):
            raise MoveError(f"Target is inside the folder comic {name!r}")
    if in_container_fs(target):
        raise MoveError(
            "Target isn't on a mounted drive: files there would live in the "
            "container and be lost when it is recreated"
        )
    return target


def folder_name(name: str) -> str:
    """A folder name from a tag: path separators and characters Windows/SMB
    shares reject become ``_``; trailing dots and spaces (also rejected) go."""
    cleaned = "".join("_" if c in '/\\:*?"<>|' or ord(c) < 32 else c for c in name.strip())
    return cleaned.rstrip(". ")


def suggest_targets(session: Session, groups: Iterable[Tuple[Iterable[int], str]]) -> List[str]:
    """Where to gather each ``(ids, name)`` group under the name ``name``: a
    folder of that name already holding some of them (the most common one),
    else ``<artist root>/<name>``; empty when ``name`` makes no folder name.

    Built for a whole table of authors at once: the comics' paths are read in
    one query and the artist folder is listed once."""
    groups = [(list(dict.fromkeys(ids)), name) for ids, name in groups]
    wanted = {id for ids, _ in groups for id in ids}
    paths: Dict[int, str] = {}
    chunk = list(wanted)
    # SQLite caps the number of bound parameters per statement.
    for start in range(0, len(chunk), 900):
        paths.update(
            session.exec(
                select(ComicEntity.id, ComicEntity.path).where(
                    col(ComicEntity.id).in_(chunk[start:start + 900])
                )
            ).all()
        )
    artist_root = os.path.normpath(global_data.Config.Comic.artist_root())
    listings: Dict[str, Optional[List[str]]] = {}
    targets: List[str] = []
    for ids, name in groups:
        folder = folder_name(name)
        if not folder:
            targets.append("")
            continue
        counts: Dict[str, int] = {}
        for id in ids:
            if id not in paths:
                continue
            parent = os.path.dirname(os.path.normpath(paths[id]))
            if _same_name(os.path.basename(parent), folder):
                counts[parent] = counts.get(parent, 0) + 1
        if counts:
            targets.append(max(counts, key=counts.__getitem__))
        else:
            targets.append(on_disk(os.path.join(artist_root, folder), listings))
    return targets


def unmounted_paths() -> List[str]:
    """Comic scan folders and the artist folder that sit in the container's
    own filesystem (see ``in_container_fs``): media there is lost with the
    container, and moves into them are refused."""
    paths = list(global_data.Config.Comic.scan_pathes) + [global_data.Config.Comic.artist_root()]
    return [p for p in dict.fromkeys(os.path.normpath(p) for p in paths) if in_container_fs(p)]


def plan(session: Session, ids: Iterable[int], target: str) -> List[ComicMovePlanItem]:
    """What moving ``ids`` into ``target`` (already checked) would do."""
    items: List[ComicMovePlanItem] = []
    taken: Dict[str, int] = {}
    target_dev: Optional[int] = None
    for id in dict.fromkeys(ids):
        comic = session.get(ComicEntity, id)
        if comic is None:
            items.append(ComicMovePlanItem(id=id, name="", source="", destination="", status="notfound"))
            continue
        source = os.path.normpath(comic.path)
        destination = os.path.join(target, os.path.basename(source))
        item = ComicMovePlanItem(
            id=id, name=comic.name, source=source, destination=destination, status="move"
        )
        items.append(item)
        if not os.path.exists(source):
            item.status = "missing"
        elif os.path.dirname(source) == target:
            item.status = "same"
        elif _inside(target, source):
            item.status, item.reason = "conflict", "Target is inside this comic"
        elif destination in taken:
            item.status, item.reason = "conflict", "Another selected comic has the same name"
        elif os.path.lexists(destination):
            item.status, item.reason = "conflict", "A file with this name is already there"
        elif session.exec(
            select(ComicEntity.id).where(ComicEntity.path == destination)
        ).first() is not None:
            item.status, item.reason = "conflict", "Another comic is recorded at this path"
        if item.status != "move":
            continue
        taken[destination] = id
        if target_dev is None:
            target_dev = _device(target)
        item.crossDevice = _device(os.path.dirname(source)) != target_dev
    return items


def _size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    return sum(
        os.path.getsize(os.path.join(root, f))
        for root, _, files in os.walk(path)
        for f in files
    )


def _remove(path: str) -> None:
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        os.remove(path)


def move_path(source: str, destination: str) -> Optional[str]:
    """Move one comic file or folder. Raises when nothing was moved; returns a
    warning when the copy landed but the original couldn't be deleted."""
    try:
        os.rename(source, destination)
        return None
    except OSError as e:
        if e.errno != errno.EXDEV:
            raise
    # Hidden, so a scan of the target folder never imports a partial copy.
    part = os.path.join(
        os.path.dirname(destination), "." + os.path.basename(destination) + ".organizer-part"
    )
    try:
        _remove(part)
        if os.path.isdir(source):
            shutil.copytree(source, part)
        else:
            shutil.copy2(source, part)
        if _size(part) != _size(source):
            raise OSError("The copy is incomplete (size differs from the original)")
        os.rename(part, destination)
    except BaseException:
        try:
            _remove(part)
        except OSError:
            pass
        raise
    try:
        _remove(source)
    except OSError as e:
        return f"copied, but the original couldn't be deleted ({e}); it will be imported again by the next scan"
    return None


def evict(path: str) -> None:
    # Drop the cached open handle, so a reader doesn't keep serving (or, on
    # Windows, locking) the old path.
    from cachetools.keys import hashkey

    key = hashkey(path)
    with comicfile.comic_lock:
        cached = comicfile.comic_cache.pop(key, None)
    if cached is not None:
        cached.close()


def run(job: Job) -> None:
    """The "move" job: move each comic, committing its new path right away so
    a failure part way keeps the comics already moved."""
    ids = [int(i) for i in job.params["ids"].split(",") if i]
    failures: List[str] = []
    warnings: List[str] = []
    moved = 0
    with Session(db.engine) as session:
        target = check_target(session, job.params["target"])
        for item in plan(session, ids, target):
            if item.status in ("same", "notfound"):
                continue
            if item.status != "move":
                failures.append(f"{item.name or item.id}: {item.reason or item.status}")
                continue
            try:
                os.makedirs(target, exist_ok=True)
                evict(item.source)
                warning = move_path(item.source, item.destination)
            except OSError as e:
                failures.append(f"{item.name}: {e.strerror or e}")
                continue
            comic = session.get(ComicEntity, item.id)
            comic.path = item.destination
            session.add(comic)
            session.commit()
            moved += 1
            if warning:
                warnings.append(f"{item.name}: {warning}")
    print(f"[Move] moved {moved} comic(s) into {target}", flush=True)
    problems = failures + warnings
    if problems:
        raise RuntimeError(
            f"Moved {moved} of {moved + len(failures)}; " + "; ".join(problems)
        )


def submit(ids: List[int], target: str):
    """Queue a move job; returns ``(job, status)`` like ``jobs.submit``."""
    return jobs.submit(
        "move", {"target": target, "ids": ",".join(str(i) for i in ids), "count": str(len(ids))}
    )


jobs.register("move", run)
