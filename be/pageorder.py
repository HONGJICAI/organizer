"""Keep saved page numbers pointing at the same pages when the page order changes.

A record's custom cover (``coverPosition``) and reading progress
(``lastViewedPosition``) are 1-based page numbers, valid only in the order they
were saved under. ``ComicEntity.pageOrder`` records that order's version
(``comicfile.PAGE_ORDER_VERSION``). When ``order_pages()`` changes, older
records get their numbers remapped by page name: the page that was number 5 in
the old order is looked up in the new one.

A queued ``page-order`` job, submitted at startup ahead of the scan, remaps every
older record it can open; records it can't (an unmounted drive) wait for the
next start. Code that saves or uses a page number on a record opened anyway
(progress, set cover, cover runs) calls ``migrate`` first, so a record the job
hasn't reached yet never mixes two orders.

The cover image itself already shows the right page and isn't rewritten.
"""
from typing import Callable, Dict, List

from sqlmodel import Session, select, update

import comicfile
import db
from core.jobs import Job, jobs
from model import ComicEntity

KIND = "page-order"

# Page order of each earlier version, from the pages in the current order.
_ORDERS: Dict[int, Callable[[List[str]], List[str]]] = {
    0: comicfile.legacy_order_pages,
}


def _needs_pages(comic: ComicEntity) -> bool:
    """Whether remapping needs the comic's pages: 0 means "first page" for the
    cover and "not read" for progress, which no order changes."""
    return comic.coverPosition > 0 or comic.lastViewedPosition > 0


def migrate(comic: ComicEntity, pages: List[str]) -> bool:
    """Bring ``comic``'s page numbers to the current order, given its pages in
    that order. Returns whether a number changed; the caller commits."""
    if comic.pageOrder >= comicfile.PAGE_ORDER_VERSION:
        return False
    before = (comic.coverPosition, comic.lastViewedPosition)
    old_order = _ORDERS.get(comic.pageOrder)
    if old_order is not None and _needs_pages(comic):
        old = old_order(pages)
        index = {name: i for i, name in enumerate(pages)}

        def remap(position: int) -> int:
            # A finished comic stays finished, whichever page is last now; a
            # number beyond the pages (the file changed) can't be matched.
            if position < 1 or position >= len(old):
                return position
            return index[old[position - 1]] + 1

        comic.coverPosition = remap(comic.coverPosition)
        comic.lastViewedPosition = remap(comic.lastViewedPosition)
    comic.pageOrder = comicfile.PAGE_ORDER_VERSION
    return (comic.coverPosition, comic.lastViewedPosition) != before


def migrate_from_file(comic: ComicEntity) -> bool:
    """``migrate`` with the pages read from the comic's file. Leaves the record
    as it is when the file can't be read."""
    if comic.pageOrder >= comicfile.PAGE_ORDER_VERSION:
        return False
    if not _needs_pages(comic):
        return migrate(comic, [])
    try:
        cf = comicfile.create(comic.path)
        if cf is None:
            return False
        with cf:
            return migrate(comic, cf.namelist)
    except Exception:
        return False


def run(job: Job) -> None:
    with Session(db.engine) as session:
        outdated = ComicEntity.pageOrder < comicfile.PAGE_ORDER_VERSION
        # Records with no page numbers just take the new version.
        session.exec(
            update(ComicEntity)
            .where(outdated)
            .where(ComicEntity.coverPosition <= 0)
            .where(ComicEntity.lastViewedPosition <= 0)
            .values(pageOrder=comicfile.PAGE_ORDER_VERSION)
        )
        session.commit()
        ids = session.exec(select(ComicEntity.id).where(outdated)).all()
    changed = unreadable = 0
    for n, id in enumerate(ids, 1):
        with Session(db.engine) as session:
            comic = session.get(ComicEntity, id)
            if comic is not None:
                changed += migrate_from_file(comic)
                if comic.pageOrder < comicfile.PAGE_ORDER_VERSION:
                    unreadable += 1
                else:
                    session.add(comic)
                    session.commit()
        job.progress = f"{n} / {len(ids)}"
    if unreadable:
        job.progress += f", {unreadable} unreadable (retried on next start)"
    print(f"[PageOrder] remapped {changed} comic(s), {unreadable} unreadable", flush=True)


def submit():
    """Queue the remap; returns ``(job, status)`` like ``jobs.submit``."""
    return jobs.submit(KIND)


jobs.register(KIND, run)
