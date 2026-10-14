"""Write helpers for ``model.ActivityEvent``.

Each helper only adds to the session; the caller commits together with the
change being recorded, so an event never exists for a write that rolled back.
"""
from datetime import datetime, time
from typing import Iterable

from sqlmodel import Session, select

from model import ActivityEvent, FileEntity

ADD = "add"
READ = "read"
DELETE = "delete"

COMIC = "comic"
VIDEO = "video"
IMAGE = "image"


def record(session: Session, kind: str, media_type: str, entity_id: int, **data) -> None:
    session.add(ActivityEvent(kind=kind, mediaType=media_type, entityId=entity_id, data=data))


def record_adds(session: Session, media_type: str, entities: Iterable[FileEntity]) -> None:
    for e in entities:
        record(session, ADD, media_type, e.id, name=e.name, size=e.size)


def record_delete(session: Session, media_type: str, entity: FileEntity, permanent: bool) -> None:
    record(session, DELETE, media_type, entity.id, name=entity.name, size=entity.size, permanent=permanent)


def record_read(session: Session, media_type: str, entity_id: int, position: int) -> None:
    """Log a read, at most one row per item per day.

    Progress is saved on every page turn, so a later save on the same day
    updates that day's row (time and furthest position) instead of adding one.
    """
    today = datetime.combine(datetime.now().date(), time.min)
    event = session.exec(
        select(ActivityEvent)
        .where(ActivityEvent.kind == READ)
        .where(ActivityEvent.mediaType == media_type)
        .where(ActivityEvent.entityId == entity_id)
        .where(ActivityEvent.time >= today)
    ).first()
    if event is None:
        record(session, READ, media_type, entity_id, position=position)
        return
    event.time = datetime.now()
    # Reassign rather than mutate: a plain JSON column doesn't track in-place edits.
    event.data = {**event.data, "position": max(position, event.data.get("position", 0))}
    session.add(event)
