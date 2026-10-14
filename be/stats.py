"""Comic stats for the stats page: library state plus activity from the
``ActivityEvent`` log (see ``events.py``).

Activity is bucketed by local calendar month, matching the naive local
timestamps the log stores.
"""
from datetime import datetime
from typing import Dict, List

from sqlalchemy import func
from sqlmodel import Session, select

import events
from model import ActivityEvent, ComicEntity
from schemas.comic import (
    ComicActivityStats,
    ComicLibraryStats,
    ComicMonthStats,
    ComicStatsResponse,
    ComicTopRead,
)

TOP_READ_LIMIT = 10


def _month_starts(now: datetime, months: int) -> List[datetime]:
    """First instant of each of the last ``months`` months, oldest first."""
    year, month = now.year, now.month
    starts = []
    for _ in range(months):
        starts.append(datetime(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return starts[::-1]


def _library(session: Session) -> ComicLibraryStats:
    live = (ComicEntity.archived == False) & (ComicEntity.missing == False)  # noqa: E712
    total, size, favorited, started, finished = session.exec(
        select(
            func.count(),
            func.coalesce(func.sum(ComicEntity.size), 0),
            func.count().filter(ComicEntity.favorited == True),  # noqa: E712
            func.count().filter(ComicEntity.lastViewedTime.is_not(None)),
            func.count().filter(
                (ComicEntity.page > 0) & (ComicEntity.lastViewedPosition >= ComicEntity.page)
            ),
        ).where(live)
    ).one()
    archived = session.exec(
        select(func.count()).where(ComicEntity.archived == True)  # noqa: E712
    ).one()
    return ComicLibraryStats(
        total=total, totalSize=size, favorited=favorited,
        started=started, finished=finished, archived=archived,
    )


def _activity(session: Session, since: datetime | None = None) -> Dict[str, ComicActivityStats]:
    """Activity per month (``YYYY-MM``) from ``since`` on, plus ``"total"``."""
    month = func.strftime("%Y-%m", ActivityEvent.time)
    size = func.coalesce(func.sum(func.json_extract(ActivityEvent.data, "$.size")), 0)

    def grouped(*columns, kind: str):
        stmt = (
            select(month, *columns)
            .where(ActivityEvent.mediaType == events.COMIC)
            .where(ActivityEvent.kind == kind)
            .group_by(month)
        )
        if since is not None:
            stmt = stmt.where(ActivityEvent.time >= since)
        return session.exec(stmt).all()

    out: Dict[str, dict] = {}

    def put(key, **values):
        for k in (key, "total"):
            bucket = out.setdefault(k, dict(added=0, read=0, readDays=0, deleted=0, deletedSize=0))
            for name, v in values.items():
                bucket[name] += v

    for m, n in grouped(func.count(), kind=events.ADD):
        put(m, added=n)
    for m, comics, days in grouped(func.count(ActivityEvent.entityId.distinct()), func.count(), kind=events.READ):
        put(m, read=comics, readDays=days)
    for m, n, freed in grouped(func.count(), size, kind=events.DELETE):
        put(m, deleted=n, deletedSize=freed)

    # Distinct comics don't add up across months; count them over the whole span.
    distinct = select(func.count(ActivityEvent.entityId.distinct())).where(
        ActivityEvent.mediaType == events.COMIC, ActivityEvent.kind == events.READ
    )
    if since is not None:
        distinct = distinct.where(ActivityEvent.time >= since)
    out.setdefault("total", dict(added=0, read=0, readDays=0, deleted=0, deletedSize=0))
    out["total"]["read"] = session.exec(distinct).one()
    return {k: ComicActivityStats(**v) for k, v in out.items()}


def _top_read(session: Session) -> List[ComicTopRead]:
    days = func.count().label("days")
    rows = session.exec(
        select(ComicEntity.id, ComicEntity.name, days)
        .join(ActivityEvent, ActivityEvent.entityId == ComicEntity.id)
        .where(ActivityEvent.mediaType == events.COMIC, ActivityEvent.kind == events.READ)
        .group_by(ComicEntity.id)
        .order_by(days.desc(), ComicEntity.id)
        .limit(TOP_READ_LIMIT)
    ).all()
    return [ComicTopRead(id=i, name=n, readDays=d) for i, n, d in rows]


def comic_stats(session: Session, months: int, now: datetime | None = None) -> ComicStatsResponse:
    starts = _month_starts(now or datetime.now(), months)
    per_month = _activity(session, since=starts[0])
    empty = ComicActivityStats(added=0, read=0, readDays=0, deleted=0, deletedSize=0)
    since = session.exec(
        select(func.min(ActivityEvent.time)).where(ActivityEvent.mediaType == events.COMIC)
    ).one()
    return ComicStatsResponse(
        library=_library(session),
        since=since,
        total=_activity(session)["total"],
        months=[
            ComicMonthStats(month=s.strftime("%Y-%m"), **per_month.get(s.strftime("%Y-%m"), empty).model_dump())
            for s in starts
        ],
        topRead=_top_read(session),
    )
