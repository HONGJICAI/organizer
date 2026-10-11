"""Pydantic models for comic-related requests and responses"""
from pydantic import BaseModel, Field
from typing import List

from model import ComicEntity


class ComicPageDetailResponse(BaseModel):
    """Response for comic page details"""
    name: str


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
