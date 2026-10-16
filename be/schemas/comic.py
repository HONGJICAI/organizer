"""Pydantic models for comic-related requests and responses"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

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
