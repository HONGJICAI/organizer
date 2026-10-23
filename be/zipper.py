"""Turn folder comics and RARs into zip files, keeping their records.

A folder comic is hundreds of small files, and on a network mount every one of
them costs a round trip: scans list each folder, moves across drives copy file
by file. A RAR is one file, but every page read runs the external 7-Zip, and a
solid RAR decompresses from its start up to the page. A stored zip avoids both:
one file, read in-process with a seek. Converting outside the app would make
the zip a new comic to the next scan (its size and time don't match the
original's), losing the favorite and progress; converting here updates the
record's path instead, so its id, cover, progress and stats stay.

Conversion runs as a "zip" job on the heavy-job queue (one comic at a time,
each committed as it's done, cancellable between comics). The zip stores the
files as they are, uncompressed: pages are already compressed images. It is
written under a hidden name next to the original, checked (every file, its
size and CRC), renamed into place, and only then is the folder or RAR deleted.
A failure part way removes the partial zip and leaves the original and the
record untouched.

A RAR is extracted once, with one 7-Zip run, into a temporary folder on the
container's own disk, and zipped from there; entries keep their names and
folders, and are checked against the RAR's own list (names, sizes, CRCs).
Encrypted and multi-volume RARs, and ones with links or unsafe names, are
refused.
"""
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading
import zipfile
from typing import Dict, List, Optional, Tuple

import rarfile
from sqlmodel import Session, col, select

import comicfile
import db
from core.jobs import Job, jobs
from model import ComicEntity, FileEntity
from schemas.comic import ComicZipPlanItem

ARCHIVE_EXTS = {".zip", ".rar"}


class ZipError(Exception):
    """A comic that can't be converted; the message says why."""


def destination(path: str) -> str:
    """The zip replacing a folder (its path plus .zip) or a RAR (.rar → .zip)."""
    path = os.path.normpath(path)
    root, ext = os.path.splitext(path)
    return root + ".zip" if ext.lower() == ".rar" else path + ".zip"


def plan(session: Session, ids: Optional[List[int]] = None) -> List[ComicZipPlanItem]:
    """The folder comics and RARs (of ``ids``, or all) and what converting
    each would do.

    Comic records don't say whether they are folders, so only paths without an
    archive extension are checked on disk: the zips, almost all of a library,
    cost nothing.
    """
    query = select(ComicEntity.id, ComicEntity.name, ComicEntity.path, ComicEntity.page).where(
        col(ComicEntity.archived).is_(False), col(ComicEntity.missing).is_(False)
    )
    if ids is not None:
        query = query.where(col(ComicEntity.id).in_(ids))
    items: List[ComicZipPlanItem] = []
    taken = set()
    for id, name, path, pages in session.exec(query.order_by(ComicEntity.path)):
        ext = os.path.splitext(path)[1].lower()
        if ext == ".rar":
            if not os.path.isfile(path):
                continue
            kind = "rar"
        elif ext in ARCHIVE_EXTS or not os.path.isdir(path):
            continue
        else:
            kind = "folder"
        dest = destination(path)
        item = ComicZipPlanItem(
            id=id, name=name, kind=kind, source=path, destination=dest, pages=pages, status="zip"
        )
        if os.path.lexists(dest):
            item.status, item.reason = "conflict", "A file with this name is already there"
        elif session.exec(select(ComicEntity.id).where(ComicEntity.path == dest)).first() is not None:
            item.status, item.reason = "conflict", "Another comic is recorded at this path"
        elif dest in taken:
            # A folder "A" and a RAR "A.rar" side by side both make "A.zip".
            item.status, item.reason = "conflict", "Another comic here converts to the same name"
        taken.add(dest)
        items.append(item)
    return items


def _part(dest: str) -> str:
    # Hidden, so a scan never imports a half-written zip.
    return os.path.join(os.path.dirname(dest), "." + os.path.basename(dest) + ".organizer-part")


Expected = Dict[str, Tuple[int, Optional[int]]]


def _write_zip(dest: str, files: List[Tuple[str, str]], expected: Expected) -> None:
    """Zip ``files`` (``(path, name in the zip)``) into ``dest``, check the
    entries against ``expected`` (name → size and CRC, None when unknown),
    and rename it into place; raises when nothing was written."""
    part = _part(dest)
    try:
        # strict_timestamps=False: files dated before 1980 (which zip can't
        # record) get 1980 instead of failing.
        with zipfile.ZipFile(part, "w", zipfile.ZIP_STORED, strict_timestamps=False) as zf:
            for path, name in files:
                zf.write(path, name)
        with zipfile.ZipFile(part) as zf:
            written = {i.filename: (i.file_size, i.CRC) for i in zf.infolist()}
            if written.keys() != expected.keys() or any(
                written[n][0] != size or (crc is not None and written[n][1] != crc)
                for n, (size, crc) in expected.items()
            ):
                raise OSError("The zip doesn't match the original")
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


def zip_folder(source: str, dest: str) -> None:
    """Write ``source``'s files into the zip ``dest``; raises when nothing was
    written (``ZipError`` for a folder that isn't a flat folder of files)."""
    entries = list(os.scandir(source))
    if any(e.is_dir() for e in entries):
        raise ZipError("The folder has subfolders")
    files = sorted(e.name for e in entries if e.is_file())
    if not any(comicfile.is_page(f) for f in files):
        raise ZipError("The folder has no pages")
    paths = [(os.path.join(source, name), name) for name in files]
    _write_zip(dest, paths, {name: (os.path.getsize(path), None) for path, name in paths})


def _safe(name: str) -> bool:
    """A name that extracts inside the target folder."""
    parts = name.split("/")
    return bool(name) and not name.startswith("/") and ".." not in parts and ":" not in parts[0]


def _extractor() -> str:
    for tool in ("7zz", "7z"):
        found = shutil.which(tool)
        if found:
            return found
    raise ZipError("No RAR extractor (7zz) is installed")


def _extract(source: str, target: str) -> None:
    """Extract the whole RAR ``source`` into ``target`` with one 7-Zip run (a
    solid RAR decompresses once, not once per page)."""
    proc = subprocess.run(
        [_extractor(), "x", "-y", "-bd", f"-o{target}", "--", source],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        # Non-ASCII names come out as UTF-8 whatever the container's locale.
        env={**os.environ, "LC_ALL": "C.UTF-8"},
    )
    if proc.returncode != 0:
        output = (proc.stderr or proc.stdout).decode(errors="replace").strip().splitlines()
        raise ZipError(f"Extracting failed: {output[-1] if output else f'exit code {proc.returncode}'}")


def zip_rar(source: str, dest: str) -> None:
    """Write the RAR ``source``'s files into the zip ``dest``; raises when
    nothing was written."""
    try:
        with rarfile.RarFile(source) as rf:
            if rf.needs_password():
                raise ZipError("The archive is encrypted")
            if len(rf.volumelist()) > 1:
                raise ZipError("Multi-volume archives aren't converted")
            infos = rf.infolist()
    except rarfile.Error as e:
        raise ZipError(f"Can't read the archive ({type(e).__name__}: {e})")
    if any(i.is_symlink() for i in infos):
        raise ZipError("The archive has links")
    files = [i for i in infos if i.is_file()]
    names = [i.filename.replace("\\", "/") for i in files]
    unsafe = next((n for n in names if not _safe(n)), None)
    if unsafe is not None:
        raise ZipError(f"Unsafe name in the archive: {unsafe}")
    if len(set(names)) != len(names):
        raise ZipError("The archive has duplicate names")
    if not any(comicfile.is_page(n) for n in names):
        raise ZipError("The archive has no pages")
    with tempfile.TemporaryDirectory(prefix="organizer-rar-") as tmp:
        _extract(source, tmp)
        root = os.path.realpath(tmp)
        paths = []
        for name in sorted(names):
            path = os.path.join(tmp, name)
            if os.path.islink(path) or not os.path.realpath(path).startswith(root + os.sep):
                raise ZipError(f"Unsafe name in the archive: {name}")
            paths.append((path, name))
        _write_zip(dest, paths, {n: (i.file_size, i.CRC) for n, i in zip(names, files)})


_cancel = threading.Event()


def run(job: Job) -> None:
    """The "zip" job: convert each folder comic or RAR, committing its new path
    right away so a failure or cancel part way keeps the comics already done."""
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
                (zip_rar if item.kind == "rar" else zip_folder)(item.source, item.destination)
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
                if item.kind == "rar":
                    os.remove(item.source)
                else:
                    shutil.rmtree(item.source)
            except OSError as e:
                warnings.append(
                    f"{item.name}: zipped, but the {item.kind} couldn't be deleted ({e.strerror or e}); "
                    "it will be imported again by the next scan"
                )
        job.progress = f"{done} / {len(items)}"
    print(f"[Zip] converted {done} comic(s)", flush=True)
    problems = failures + warnings
    if problems:
        raise RuntimeError(f"Converted {done} of {done + len(failures)}; " + "; ".join(problems))


def submit(ids: List[int]):
    """Queue a zip job; returns ``(job, status)`` like ``jobs.submit``."""
    return jobs.submit("zip", {"ids": ",".join(str(i) for i in ids), "count": str(len(ids))})


jobs.register("zip", run, cancel=_cancel.set)
