"""Pydantic models for comic-related requests and responses"""
from pydantic import BaseModel
from typing import List


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
