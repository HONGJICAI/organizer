"""Regenerate comic covers (Admin → Covers), as a job on core.jobs' queue.

Two modes: ``all`` rewrites every live comic's cover; ``missing`` only
generates covers whose file doesn't exist (quick, e.g. after fixing a reader
bug that made generation fail).

Covers are ``{id}_0.jpg`` files that outlive their comic: when a cover can't be
generated, an older file under the same id keeps showing — possibly another
comic's, after an id was reused. Each processed comic's cover is rewritten
from its custom cover page (``coverPosition``), falling back to the first page,
and deletes the file when neither renders so no stale image survives. Every
processed comic gets a new ``entityUpdateTime``, the version the frontend puts
on cover URLs, so browsers drop their cached copies, and its page count is
refreshed from the file, since page detection may have changed since import.
"""
import os
import threading
from datetime import datetime
from multiprocessing.pool import ThreadPool
from typing import List, Literal, Optional

from sqlmodel import Session, select

import comicfile
import db
import global_data
from loader import ComicLoader
from model import ComicEntity

# Failures kept for the status endpoint; the count covers the rest.
MAX_FAILURES = 100
_COMMIT_EVERY = 50

Mode = Literal["all", "missing"]


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
                    for i, (comic, reason, pages) in enumerate(pool.imap_unordered(_regenerate, comics), 1):
                        if self._cancel.is_set():
                            with self._lock:
                                self.cancelled = True
                            break
                        comic.entityUpdateTime = datetime.now()
                        if pages is not None:
                            comic.page = pages
                        session.add(comic)
                        if i % _COMMIT_EVERY == 0:
                            session.commit()
                        with self._lock:
                            self.processed += 1
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
                "failures": list(self.failures),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


def _cover_path(comic: ComicEntity) -> str:
    return os.path.join(global_data.Config.nginx_comic_path, f"{comic.id}_0.jpg")


def _regenerate(comic: ComicEntity):
    """Rewrite one cover.

    Returns ``(comic, failure reason or None, page count or None)``; the page
    count is None when the file couldn't be opened.
    """
    # coverPosition is the 1-based page picked as cover; 0 means the first page.
    candidates = list(dict.fromkeys([max(comic.coverPosition - 1, 0), 0]))
    reason = "No page could be rendered as a cover"
    pages = None
    try:
        cf = comicfile.create(comic.path)
        if cf is None:
            reason = "Comic file not found or unsupported"
        else:
            with cf:
                pages = cf.page
                if any(ComicLoader.gen_comic_cover(comic, cf, True, p) for p in candidates):
                    return comic, None, pages
    except Exception as e:
        reason = str(e) or type(e).__name__
    cover = _cover_path(comic)
    if os.path.exists(cover):
        os.remove(cover)
    return comic, reason, pages


# Process-wide singleton.
regen = CoverRegen()
