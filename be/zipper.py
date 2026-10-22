"""Turn folder comics into zip files, keeping their records.

A folder comic is hundreds of small files, and on a network mount every one of
them costs a round trip: scans list each folder, moves across drives copy file
by file. One zip per comic avoids that. Converting outside the app would make
the zip a new comic to the next scan (its size and time don't match the
folder's), losing the favorite and progress; converting here updates the
record's path instead, so its id, cover, progress and stats stay.

Conversion runs as a "zip" job on the heavy-job queue (one comic at a time,
each committed as it's done, cancellable between comics). The zip stores the
folder's files as they are, uncompressed: pages are already compressed images,
and stored entries read back with a plain seek. It is written under a hidden
name next to the folder, checked (every file, its size and CRC), renamed into
place, and only then is the folder deleted. A failure part way removes the
partial zip and leaves the folder and record untouched.
"""
import os
import pathlib
import shutil
import threading
import zipfile
from typing import List, Optional

from sqlmodel import Session, col, select

import comicfile
import db
from core.jobs import Job, jobs
from model import ComicEntity, FileEntity
from schemas.comic import ComicZipPlanItem

ARCHIVE_EXTS = {".zip", ".rar"}


class ZipError(Exception):
    """A folder that can't be converted; the message says why."""


def destination(path: str) -> str:
    return os.path.normpath(path) + ".zip"


def plan(session: Session, ids: Optional[List[int]] = None) -> List[ComicZipPlanItem]:
    """The folder comics (of ``ids``, or all) and what converting each would do.

    Comic records don't say whether they are folders, so only paths without an
    archive extension are checked on disk: the zips and rars, almost all of a
    library, cost nothing.
    """
    query = select(ComicEntity.id, ComicEntity.name, ComicEntity.path, ComicEntity.page).where(
        col(ComicEntity.archived).is_(False), col(ComicEntity.missing).is_(False)
    )
    if ids is not None:
        query = query.where(col(ComicEntity.id).in_(ids))
    items: List[ComicZipPlanItem] = []
    for id, name, path, pages in session.exec(query.order_by(ComicEntity.path)):
        if os.path.splitext(path)[1].lower() in ARCHIVE_EXTS or not os.path.isdir(path):
            continue
        dest = destination(path)
        item = ComicZipPlanItem(id=id, name=name, source=path, destination=dest, pages=pages, status="zip")
        if os.path.lexists(dest):
            item.status, item.reason = "conflict", "A file with this name is already there"
        elif session.exec(select(ComicEntity.id).where(ComicEntity.path == dest)).first() is not None:
            item.status, item.reason = "conflict", "Another comic is recorded at this path"
        items.append(item)
    return items


def _part(dest: str) -> str:
    # Hidden, so a scan never imports a half-written zip.
    return os.path.join(os.path.dirname(dest), "." + os.path.basename(dest) + ".organizer-part")


def zip_folder(source: str, dest: str) -> None:
    """Write ``source``'s files into the zip ``dest``; raises when nothing was
    written (``ZipError`` for a folder that isn't a flat folder of files)."""
    entries = list(os.scandir(source))
    if any(e.is_dir() for e in entries):
        raise ZipError("The folder has subfolders")
    files = sorted(e.name for e in entries if e.is_file())
    if not any(comicfile.is_page(f) for f in files):
        raise ZipError("The folder has no pages")
    part = _part(dest)
    try:
        # strict_timestamps=False: files dated before 1980 (which zip can't
        # record) get 1980 instead of failing.
        with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED, strict_timestamps=False) as zf:
            for name in files:
                zf.write(os.path.join(source, name), name)
        with zipfile.ZipFile(part) as zf:
            written = {i.filename: i.file_size for i in zf.infolist()}
            if written != {name: os.path.getsize(os.path.join(source, name)) for name in files}:
                raise OSError("The zip doesn't match the folder")
            bad = zf.testzip()
            if bad is not None:
                raise OSError(f"{bad} reads back corrupted")
        if os.path.lexists(dest):
            raise ZipError("A file with this name is already there")
        os.rename(part, dest)
    except BaseException:
        try:
            os.remove(part)
        except OSError:
            pass
        raise


_cancel = threading.Event()


def run(job: Job) -> None:
    """The "zip" job: convert each folder comic, committing its new path right
    away so a failure or cancel part way keeps the comics already done."""
    from mover import evict

    _cancel.clear()
    ids = [int(i) for i in job.params["ids"].split(",") if i]
    failures: List[str] = []
    warnings: List[str] = []
    done = 0
    with Session(db.engine) as session:
        items = plan(session, ids)
        for n, item in enumerate(items):
            if _cancel.is_set():
                break
            job.progress = f"{n} / {len(items)}"
            if item.status != "zip":
                failures.append(f"{item.name}: {item.reason}")
                continue
            try:
                zip_folder(item.source, item.destination)
            except (OSError, ZipError, zipfile.BadZipFile) as e:
                failures.append(f"{item.name}: {getattr(e, 'strerror', None) or e}")
                continue
            comic = session.get(ComicEntity, item.id)
            # Name, size and time as a scan would record them for the zip.
            found = FileEntity.from_path(pathlib.Path(item.destination))
            comic.path, comic.name = item.destination, found.name
            comic.size, comic.updateTime = found.size, found.updateTime
            session.add(comic)
            session.commit()
            done += 1
            evict(item.source)
            try:
                shutil.rmtree(item.source)
            except OSError as e:
                warnings.append(
                    f"{item.name}: zipped, but the folder couldn't be deleted ({e.strerror or e}); "
                    "it will be imported again by the next scan"
                )
        job.progress = f"{done} / {len(items)}"
    print(f"[Zip] converted {done} folder comic(s)", flush=True)
    problems = failures + warnings
    if problems:
        raise RuntimeError(f"Converted {done} of {done + len(failures)}; " + "; ".join(problems))


def submit(ids: List[int]):
    """Queue a zip job; returns ``(job, status)`` like ``jobs.submit``."""
    return jobs.submit("zip", {"ids": ",".join(str(i) for i in ids), "count": str(len(ids))})


jobs.register("zip", run, cancel=_cancel.set)
