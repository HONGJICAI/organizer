"""Tag classification: which file-name tags are authors, languages or noise, and which are aliases of each other.

Tags themselves are split from file names by the frontend; this only stores
what the user decided about them (see ``model.TagInfo``).
"""
from datetime import datetime
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from fastapi_utils.cbv import cbv
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

import db
from core.exceptions import abort
from model import TagInfo

router = APIRouter()

TagKind = Literal["author", "language", "ignored"]


class TagKindRequest(BaseModel):
    """Set the kind of some tags"""
    names: List[str] = Field(min_length=1)
    kind: Optional[TagKind] = Field(
        default=None,
        description="null unclassifies: the tags lose their kind and stop being aliases",
    )


class TagMergeRequest(BaseModel):
    """Make tags aliases of one primary tag"""
    primary: str
    aliases: List[str] = Field(min_length=1)


class TagUpdateResponse(BaseModel):
    tags: List[TagInfo] = Field(description="Every classified tag after the change")


def _clean(names: List[str]) -> List[str]:
    cleaned = list(dict.fromkeys(n.strip() for n in names))
    if any(not n for n in cleaned):
        abort(400, "Tag names can't be empty")
    return cleaned


@cbv(router)
class TagCBV:
    session: Session = Depends(db.get_session)

    @router.get("/api/tags", tags=["tags"])
    def get_all(self) -> List[TagInfo]:
        return list(self.session.exec(select(TagInfo).order_by(TagInfo.name)).all())

    @router.post(
        "/api/tags/kind",
        tags=["tags"],
        responses={200: {"model": TagUpdateResponse}, 400: {"model": dict}},
    )
    def set_kind(self, req: TagKindRequest) -> TagUpdateResponse:
        """Give the tags a kind (they stop being aliases), or with ``kind``
        null forget them. Aliases of a forgotten tag are forgotten too."""
        names = _clean(req.names)
        for name in names:
            row = self.session.get(TagInfo, name)
            if req.kind is None:
                if row is not None:
                    self.session.delete(row)
                for alias in self._aliases_of(name):
                    self.session.delete(alias)
                continue
            row = row or TagInfo(name=name)
            row.kind, row.canonical, row.updateTime = req.kind, None, datetime.now()
            self.session.add(row)
        self.session.commit()
        return TagUpdateResponse(tags=self.get_all())

    @router.post(
        "/api/tags/merge",
        tags=["tags"],
        responses={200: {"model": TagUpdateResponse}, 400: {"model": dict}},
    )
    def merge(self, req: TagMergeRequest) -> TagUpdateResponse:
        """Make ``aliases`` aliases of ``primary``. Their own aliases move to
        ``primary``; if ``primary`` was an alias, it becomes a primary tag.
        ``primary`` keeps its kind, or takes the first kind among the aliases
        when it has none."""
        primary = _clean([req.primary])[0]
        aliases = [a for a in _clean(req.aliases) if a != primary]
        if not aliases:
            abort(400, "Choose at least one tag other than the primary one")
        now = datetime.now()
        head = self.session.get(TagInfo, primary) or TagInfo(name=primary)
        kinds = [self._kind(a) for a in aliases]
        head.kind = head.kind or self._kind(head.canonical) or next((k for k in kinds if k), None)
        head.canonical, head.updateTime = None, now
        self.session.add(head)
        for name in aliases:
            for alias in self._aliases_of(name):
                alias.canonical, alias.updateTime = primary, now
                self.session.add(alias)
            row = self.session.get(TagInfo, name) or TagInfo(name=name)
            row.kind, row.canonical, row.updateTime = None, primary, now
            self.session.add(row)
        self.session.commit()
        return TagUpdateResponse(tags=self.get_all())

    def _aliases_of(self, name: str) -> List[TagInfo]:
        return list(self.session.exec(select(TagInfo).where(col(TagInfo.canonical) == name)).all())

    def _kind(self, name: Optional[str]) -> Optional[str]:
        row = self.session.get(TagInfo, name) if name else None
        return row.kind if row else None
