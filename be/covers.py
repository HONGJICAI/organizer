"""Regenerate comic covers (Admin → Covers), as a job on core.jobs' queue.

Three modes: ``all`` rewrites every live comic's cover; ``missing`` only
generates covers whose file doesn't exist (quick, e.g. after fixing a reader
bug that made generation fail); ``changed`` only handles comics whose file
changed in place since it was recorded (say, its pages recompressed to webp by
another tool), which scans don't notice: scans only look for new and gone
paths. Telling a changed comic costs one stat, not an open: an archive whose
size or modification time differs from the record's, or a folder comic whose
folder time differs (files added, removed or renamed in it).

Covers are ``{id}_0.jpg`` files that outlive their comic: when a cover can't be
generated, an older file under the same id keeps showing — possibly another
comic's, after an id was reused. Each processed comic's cover is rewritten
from its custom cover page (``coverPosition``), falling back to the first page,
and deletes the file when neither renders so no stale image survives. Every
processed comic gets a new ``entityUpdateTime``, the version the frontend puts
on cover URLs, so browsers drop their cached copies, and its page count is
refreshed from the file, since page detection may have changed since import,
along with its size and modification time.
"""
import os
import pathlib
import threading
from datetime import datetime
from multiprocessing.pool import ThreadPool
from typing import List, Literal, Optional

from sqlmodel import Session, select

import comicfile
import db
import global_data
from loader import ComicLoader
from model import ComicEntity, FileEntity

# Failures kept for the status endpoint; the count covers the rest.
MAX_FAILURES = 100
_COMMIT_EVERY = 50

Mode = Literal["all", "missing", "changed"]


class CoverRegen:
    """Thread-safe progress of the running (or most recent) regeneration."""

    def __init__(self):
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self.reset()

    def reset(self):
        self.running = False
        self.mode: Optional[Mode] = None
        self.total = 0
        self.processed = 0
        self.failed = 0
        # Comics opened and updated; in "changed" mode, those that changed.
        self.refreshed = 0
        self.failures: List[dict] = []
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None
        self.cancelled = False

    def run(self, mode: Mode = "all"):
        """Regenerate covers on the calling thread (the job queue's worker)."""
        self._cancel.clear()
        with self._lock:
            self.reset()
            self.running = True
            self.mode = mode
            self.started_at = datetime.now()
        try:
            # Workers read comics while this thread commits; without
            # expire_on_commit=False a commit would make them lazy-reload
            # attributes through this session from other threads.
            with Session(db.engine, expire_on_commit=False) as session:
                comics = session.exec(
                    select(ComicEntity)
                    .where(ComicEntity.archived == False)  # noqa: E712
                    .where(ComicEntity.missing == False)  # noqa: E712
                ).all()
                if mode == "missing":
                    comics = [c for c in comics if not os.path.exists(_cover_path(c))]
                with self._lock:
                    self.total = len(comics)
                # Leaving the pool's block terminates it, so a cancel drops the
                # comics not yet handed out; finished ones are still committed.
                with ThreadPool(8) as pool:
                    work = _refresh_changed if mode == "changed" else _refresh
                    for i, (comic, reason, found, touched) in enumerate(pool.imap_unordered(work, comics), 1):
                        if self._cancel.is_set():
                            with self._lock:
                                self.cancelled = True
                            break
                        if touched:
                            comic.entityUpdateTime = datetime.now()
                            session.add(comic)
                        if found is not None:
                            comic.page = found.page
                            comic.size, comic.updateTime = found.size, found.updateTime
                        if i % _COMMIT_EVERY == 0:
                            session.commit()
                        with self._lock:
                            self.processed += 1
                            self.refreshed += touched
                            if reason is not None:
                                self.failed += 1
                                if len(self.failures) < MAX_FAILURES:
                                    self.failures.append({"id": comic.id, "name": comic.name, "reason": reason})
                session.commit()
        finally:
            with self._lock:
                self.running = False
                self.finished_at = datetime.now()

    def cancel(self):
        """Ask the running regeneration to stop after the comic in hand."""
        self._cancel.set()

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "cancelled": self.cancelled,
                "mode": self.mode,
                "total": self.total,
                "processed": self.processed,
                "failed": self.failed,
                "refreshed": self.refreshed,
                "failures": list(self.failures),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


def _cover_path(comic: ComicEntity) -> str:
    return os.path.join(global_data.Config.nginx_comic_path, f"{comic.id}_0.jpg")


class Found:
    """What a comic's file holds now."""

    def __init__(self, page: int, size: int, updateTime: datetime):
        self.page, self.size, self.updateTime = page, size, updateTime


def changed(comic: ComicEntity, st: os.stat_result) -> bool:
    """Whether the file behind ``comic`` changed since it was recorded. A
    folder's size is the sum of its files, which takes a walk to know; its own
    time changes when files are added, removed or renamed in it."""
    if datetime.fromtimestamp(st.st_mtime) != comic.updateTime:
        return True
    return not os.path.isdir(comic.path) and st.st_size != comic.size


def _refresh_changed(comic: ComicEntity):
    """``_refresh`` for a comic whose file changed; the others are left alone,
    cover included."""
    try:
        st = os.stat(comic.path)
    except OSError as e:
        # Gone: the next scan flags it missing. Its cover stays until then.
        return comic, f"Can't read the file ({e.strerror or e})", None, False
    if not changed(comic, st):
        return comic, None, None, False
    return _refresh(comic)


def _refresh(comic: ComicEntity):
    """Rewrite one cover and read the file's page count, size and time.

    Returns ``(comic, failure reason or None, Found or None, True)``; Found is
    None when the file couldn't be opened. The last item says the comic was
    handled: its cover was rewritten or removed.
    """
    # coverPosition is the 1-based page picked as cover; 0 means the first page.
    candidates = list(dict.fromkeys([max(comic.coverPosition - 1, 0), 0]))
    reason = "No page could be rendered as a cover"
    found = None
    try:
        cf = comicfile.create(comic.path)
        if cf is None:
            reason = "Comic file not found or unsupported"
        else:
            with cf:
                file = FileEntity.from_path(pathlib.Path(comic.path))
                found = Found(cf.page, file.size, file.updateTime)
                if any(ComicLoader.gen_comic_cover(comic, cf, True, p) for p in candidates):
                    return comic, None, found, True
    except Exception as e:
        reason = str(e) or type(e).__name__
    cover = _cover_path(comic)
    if os.path.exists(cover):
        os.remove(cover)
    return comic, reason, found, True


# Process-wide singleton.
regen = CoverRegen()
