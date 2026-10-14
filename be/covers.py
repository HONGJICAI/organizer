"""Regenerate every comic cover in the background (Admin → Covers).

Covers are ``{id}_0.jpg`` files that outlive their comic: when a cover can't be
generated, an older file under the same id keeps showing — possibly another
comic's, after an id was reused. Regenerating rewrites each live comic's cover
from its custom cover page (``coverPosition``), falling back to the first page,
and deletes the file when neither renders so no stale image survives. Every
processed comic gets a new ``entityUpdateTime``, the version the frontend puts
on cover URLs, so browsers drop their cached copies.
"""
import os
import threading
from datetime import datetime
from multiprocessing.pool import ThreadPool
from typing import List, Optional

from sqlmodel import Session, select

import comicfile
import db
import global_data
from loader import ComicLoader
from model import ComicEntity

# Failures kept for the status endpoint; the count covers the rest.
MAX_FAILURES = 100
_COMMIT_EVERY = 50


class CoverRegen:
    """Thread-safe progress of the running (or most recent) regeneration."""

    def __init__(self):
        self._lock = threading.Lock()
        self.reset()

    def reset(self):
        self.running = False
        self.total = 0
        self.processed = 0
        self.failed = 0
        self.failures: List[dict] = []
        self.started_at: Optional[datetime] = None
        self.finished_at: Optional[datetime] = None

    def start(self) -> bool:
        """Start a run in a background thread unless one is already running."""
        with self._lock:
            if self.running:
                return False
            self.reset()
            self.running = True
            self.started_at = datetime.now()
        _in_background(self.run)
        return True

    def run(self):
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
                with self._lock:
                    self.total = len(comics)
                with ThreadPool(8) as pool:
                    for i, (comic, reason) in enumerate(pool.imap_unordered(_regenerate, comics), 1):
                        comic.entityUpdateTime = datetime.now()
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

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "running": self.running,
                "total": self.total,
                "processed": self.processed,
                "failed": self.failed,
                "failures": list(self.failures),
                "started_at": self.started_at,
                "finished_at": self.finished_at,
            }


def _in_background(target) -> None:
    threading.Thread(target=target, daemon=True).start()


def _regenerate(comic: ComicEntity):
    """Rewrite one cover. Returns ``(comic, None)`` or ``(comic, failure reason)``."""
    # coverPosition is the 1-based page picked as cover; 0 means the first page.
    pages = list(dict.fromkeys([max(comic.coverPosition - 1, 0), 0]))
    reason = "No page could be rendered as a cover"
    try:
        cf = comicfile.create(comic.path)
        if cf is None:
            reason = "Comic file not found or unsupported"
        else:
            with cf:
                if any(ComicLoader.gen_comic_cover(comic, cf, True, page) for page in pages):
                    return comic, None
    except Exception as e:
        reason = str(e) or type(e).__name__
    cover = os.path.join(global_data.Config.nginx_comic_path, f"{comic.id}_0.jpg")
    if os.path.exists(cover):
        os.remove(cover)
    return comic, reason


# Process-wide singleton.
regen = CoverRegen()
