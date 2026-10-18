"""Pydantic models for comic-related requests and responses"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Literal, Optional

from model import ComicEntity


class ComicPageDetailResponse(BaseModel):
    """Response for comic page details"""
    name: str
    size: int = Field(description="Page file size in bytes (uncompressed)")


class ComicDetailResponse(BaseModel):
    """Response for comic details"""
    pageDetails: List[ComicPageDetailResponse]


class ComicRenameRequest(BaseModel):
    """Request to rename a comic"""
    name: str


class ComicRenameResponse(BaseModel):
    """Response for comic rename operation"""
    name: str


class ComicMoveRequest(BaseModel):
    """Request to move comics into one folder"""
    ids: List[int] = Field(min_length=1)
    target: str = Field(description="Absolute folder path inside a comic scan folder; created if missing")


class ComicMoveSuggestRequest(BaseModel):
    """Request a target folder for gathering comics under one name"""
    ids: List[int] = Field(min_length=1)
    name: str = Field(description="Folder name, e.g. the author tag")


class ComicMoveSuggestion(BaseModel):
    """Suggested target folder"""
    target: str = Field(
        description="A folder with this name already holding some of the comics, else <artist folder>/<name>; "
        "empty when the name can't be a folder name"
    )


class ComicMovePlanItem(BaseModel):
    """What moving one comic would do"""
    id: int
    name: str
    source: str
    destination: str
    status: Literal["move", "same", "conflict", "missing", "notfound"] = Field(
        description="move: will be moved; same: already in the target folder; conflict: destination taken "
        "(see reason); missing: file not on disk; notfound: no comic with this id"
    )
    crossDevice: bool = Field(
        default=False,
        description="Source and target are on different filesystems: copied then deleted instead of renamed",
    )
    reason: Optional[str] = None


class ComicMovePreview(BaseModel):
    """Response for the move preview"""
    target: str = Field(description="The normalized target folder")
    items: List[ComicMovePlanItem]


class ComicMoveResponse(BaseModel):
    """Response for a queued move"""
    jobId: int
    status: Literal["started", "queued", "already_queued"]
    message: str


class DuplicateGroup(BaseModel):
    """Comics that look like copies of the same work"""
    exact: bool = Field(description="All names reduce to the same title and volume; otherwise only similar")
    keepId: int = Field(description="Suggested copy to keep: favorited, then most pages, then largest")
    items: List[ComicEntity]


class DuplicatesResponse(BaseModel):
    """Response for the duplicate finder"""
    groups: List[DuplicateGroup]


class ComicLibraryStats(BaseModel):
    """Current state of the live library (not archived, file present)"""
    total: int
    totalSize: int = Field(description="Bytes")
    favorited: int
    started: int = Field(description="Opened at least once")
    finished: int = Field(description="Last position reached the last page")
    archived: int = Field(description="Deleted files whose record was kept")


class ComicActivityStats(BaseModel):
    """Activity counted from the event log over one period"""
    added: int
    read: int = Field(description="Distinct comics read")
    readDays: int = Field(description="Comic-days read: one comic read on one day counts once")
    deleted: int
    deletedSize: int = Field(description="Bytes freed by deletes")


class ComicMonthStats(ComicActivityStats):
    month: str = Field(description="YYYY-MM, local time")


class ComicTopRead(BaseModel):
    id: int
    name: str
    readDays: int


class ComicStatsResponse(BaseModel):
    """Response for the stats page"""
    library: ComicLibraryStats
    since: Optional[datetime] = Field(default=None, description="Time of the first logged event; null when none")
    total: ComicActivityStats
    months: List[ComicMonthStats] = Field(description="Oldest first, the current month last; empty months included")
    topRead: List[ComicTopRead] = Field(description="Most read comics by distinct days, existing comics only")
